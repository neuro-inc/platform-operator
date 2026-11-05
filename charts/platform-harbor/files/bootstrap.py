import base64
import json
import os
import secrets
import ssl
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HARBOR_URL = os.environ["HARBOR_URL"].rstrip("/")
API_URL = f"{HARBOR_URL}/api/v2.0"
ADMIN = ("admin", os.environ["HARBOR_ADMIN_PASSWORD"])
PROJECT = os.environ["HARBOR_PROJECT"]
ROBOT = os.environ["HARBOR_ROBOT"]
SECRET_NAME = os.environ["SECRET_NAME"]
WAIT_SECONDS = int(os.environ.get("WAIT_SECONDS", "900"))
SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
K8S_URL = "https://kubernetes.default.svc"
PERMISSIONS = [
    {"kind": "system", "namespace": "/", "access": [{"resource": "catalog", "action": "read"}]},
    {
        "kind": "project",
        "namespace": PROJECT,
        "access": [
            {"resource": "repository", "action": action}
            for action in ("list", "pull", "push", "delete")
        ]
        + [{"resource": "artifact", "action": action} for action in ("read", "list", "delete")]
        + [{"resource": "tag", "action": action} for action in ("list", "create", "delete")],
    },
]


def log(message):
    print(message, flush=True)


def fail(message):
    log(message)
    sys.exit(1)


def call(url, method="GET", body=None, headers=None, context=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            status, payload = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, payload = error.code, error.read()
    try:
        return status, json.loads(payload) if payload else None
    except ValueError:
        return status, payload.decode(errors="replace")


def basic(username, password):
    return {"Authorization": "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()}


def harbor(method, path, body=None):
    return call(f"{API_URL}{path}", method, body, basic(*ADMIN))


def kube(method, path, body=None):
    with open(f"{SA_DIR}/token") as f:
        token = f.read().strip()
    context = ssl.create_default_context(cafile=f"{SA_DIR}/ca.crt")
    return call(f"{K8S_URL}{path}", method, body, {"Authorization": f"Bearer {token}"}, context)


def wait_for_harbor():
    deadline = time.monotonic() + WAIT_SECONDS
    while True:
        try:
            status, body = harbor("GET", "/health")
            if status == 200 and isinstance(body, dict) and body.get("status") == "healthy":
                log("harbor is healthy")
                return
            log(f"harbor is not healthy yet: {status} {body}")
        except OSError as error:
            log(f"harbor is not reachable yet: {error}")
        if time.monotonic() > deadline:
            fail(f"harbor did not become healthy in {WAIT_SECONDS}s")
        time.sleep(10)


def ensure_configuration():
    status, body = harbor("GET", "/configurations")
    if status != 200:
        fail(f"reading configurations failed: {status} {body}")
    if body["project_creation_restriction"]["value"] != "adminonly":
        status, response = harbor("PUT", "/configurations", {"project_creation_restriction": "adminonly"})
        if status != 200:
            fail(f"restricting project creation failed: {status} {response}")
        log("project creation restricted to admins")
    return body["robot_name_prefix"]["value"]


def ensure_project():
    status, _ = harbor("HEAD", f"/projects?project_name={urllib.parse.quote(PROJECT)}")
    if status == 200:
        log(f"project {PROJECT} exists")
        return
    if status != 404:
        fail(f"checking project {PROJECT} failed: {status}")
    status, body = harbor("POST", "/projects", {"project_name": PROJECT, "metadata": {"public": "false"}})
    if status not in (201, 409):
        fail(f"creating project {PROJECT} failed: {status} {body}")
    log(f"project {PROJECT} created")


def new_password():
    alphabet = string.ascii_letters + string.digits
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(32))
        if any(c.islower() for c in password) and any(c.isupper() for c in password) and any(c.isdigit() for c in password):
            return password


def ensure_secret(username):
    with open(f"{SA_DIR}/namespace") as f:
        path = f"/api/v1/namespaces/{f.read().strip()}/secrets"
    status, body = kube("GET", f"{path}/{SECRET_NAME}")
    if status == 200:
        data = body.get("data") or {}
        if data.get("password") and base64.b64decode(data.get("username", "")).decode() == username:
            log(f"secret {SECRET_NAME} exists")
            return base64.b64decode(data["password"]).decode()
    elif status != 404:
        fail(f"reading secret {SECRET_NAME} failed: {status} {body}")
    password = new_password()
    secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": SECRET_NAME},
        "type": "Opaque",
        "stringData": {"username": username, "password": password},
    }
    if status == 200:
        status, body = kube("PUT", f"{path}/{SECRET_NAME}", secret)
    else:
        status, body = kube("POST", path, secret)
    if status not in (200, 201):
        fail(f"writing secret {SECRET_NAME} failed: {status} {body}")
    log(f"secret {SECRET_NAME} written")
    return password


def normalized(permissions):
    return sorted(
        (p["kind"], p["namespace"], sorted((a["resource"], a["action"]) for a in p["access"])) for p in permissions
    )


def find_robot(username):
    status, body = harbor("GET", f"/robots?q={urllib.parse.quote(f'name={ROBOT}')}&page_size=100")
    if status != 200:
        fail(f"listing robots failed: {status} {body}")
    return next((r for r in body if r["name"] == username and r["level"] == "system"), None)


def ensure_robot(username, password):
    robot = find_robot(username)
    if robot is None:
        status, body = harbor(
            "POST",
            "/robots",
            {
                "name": ROBOT,
                "description": "platform-registry upstream",
                "level": "system",
                "duration": -1,
                "disable": False,
                "permissions": PERMISSIONS,
            },
        )
        if status != 201:
            fail(f"creating robot {username} failed: {status} {body}")
        robot = find_robot(username)
        log(f"robot {username} created")
    elif normalized(robot["permissions"]) != normalized(PERMISSIONS):
        status, body = harbor("PUT", f"/robots/{robot['id']}", {**robot, "permissions": PERMISSIONS})
        if status != 200:
            fail(f"updating permissions of {username} failed: {status} {body}")
        log(f"robot {username} permissions updated")
    else:
        log(f"robot {username} exists")
    status, body = call(f"{HARBOR_URL}/v2/", headers=basic(username, password))
    if status == 200:
        return
    if status != 401:
        fail(f"checking credentials of {username} failed: {status} {body}")
    status, body = harbor("PATCH", f"/robots/{robot['id']}", {"secret": password})
    if status != 200:
        fail(f"setting secret of {username} failed: {status} {body}")
    status, body = call(f"{HARBOR_URL}/v2/", headers=basic(username, password))
    if status != 200:
        fail(f"credentials of {username} still rejected: {status} {body}")
    log(f"robot {username} secret set")


def main():
    wait_for_harbor()
    username = ensure_configuration() + ROBOT
    ensure_project()
    ensure_robot(username, ensure_secret(username))
    log("bootstrap finished")


if __name__ == "__main__":
    main()
