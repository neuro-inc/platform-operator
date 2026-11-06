import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HARBOR_URL = os.environ["HARBOR_URL"].rstrip("/")
API_URL = f"{HARBOR_URL}/api/v2.0"
ADMIN = ("admin", os.environ["HARBOR_ADMIN_PASSWORD"])
PROJECT = os.environ["HARBOR_PROJECT"]
CREDENTIALS_SECRET = os.environ["CREDENTIALS_SECRET"]
S3_SECRET = os.environ["S3_SECRET"]
WAIT_SECONDS = int(os.environ.get("WAIT_SECONDS", "900"))
ROBOT_PREFIX = "robot$"
REQUIRED = {
    "ROBOT_USERNAME": (CREDENTIALS_SECRET, "username"),
    "ROBOT_SECRET": (CREDENTIALS_SECRET, "password"),
    "S3_ACCESS_KEY": (S3_SECRET, "REGISTRY_STORAGE_S3_ACCESSKEY"),
    "S3_SECRET_KEY": (S3_SECRET, "REGISTRY_STORAGE_S3_SECRETKEY"),
}
PERMISSIONS = [
    {"kind": "system", "namespace": "/", "access": [{"resource": "catalog", "action": "read"}]},
    {
        "kind": "project",
        "namespace": PROJECT,
        "access": [{"resource": "repository", "action": action} for action in ("pull", "push", "delete")],
    },
]
DESIRED = {"disable": False, "duration": -1}


def log(message):
    print(message, flush=True)


def fail(message):
    log(message)
    sys.exit(1)


def call(url, method="GET", body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
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


def check_secrets():
    missing = [f"{secret}/{key}" for env, (secret, key) in REQUIRED.items() if not os.environ.get(env)]
    if missing:
        fail(f"missing or empty secret keys: {', '.join(missing)}")
    username = os.environ["ROBOT_USERNAME"]
    if not username.startswith(ROBOT_PREFIX) or username == ROBOT_PREFIX:
        fail(f"{CREDENTIALS_SECRET}/username must be a robot name starting with {ROBOT_PREFIX}, got {username}")
    secret = os.environ["ROBOT_SECRET"]
    if not (8 <= len(secret) <= 128 and any(c.islower() for c in secret) and any(c.isupper() for c in secret) and any(c.isdigit() for c in secret)):
        fail(f"{CREDENTIALS_SECRET}/password must be 8-128 characters with an upper case letter, a lower case letter and a digit")
    log(f"secrets {CREDENTIALS_SECRET} and {S3_SECRET} have the required keys")
    return username[len(ROBOT_PREFIX) :], username, secret


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
    if body["robot_name_prefix"]["value"] != ROBOT_PREFIX:
        fail(f"harbor robot_name_prefix is {body['robot_name_prefix']['value']}, expected {ROBOT_PREFIX}")
    if body["project_creation_restriction"]["value"] != "adminonly":
        status, response = harbor("PUT", "/configurations", {"project_creation_restriction": "adminonly"})
        if status != 200:
            fail(f"restricting project creation failed: {status} {response}")
        log("project creation restricted to admins")


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


def normalized(permissions):
    return sorted(
        (p["kind"], p["namespace"], sorted((a["resource"], a["action"]) for a in p["access"])) for p in permissions
    )


def find_robot(name, username):
    status, body = harbor("GET", f"/robots?q={urllib.parse.quote(f'name={name}')}&page_size=100")
    if status != 200:
        fail(f"listing robots failed: {status} {body}")
    return next((r for r in body if r["name"] == username and r["level"] == "system"), None)


def ensure_robot(name, username, password):
    robot = find_robot(name, username)
    if robot is None:
        status, body = harbor(
            "POST",
            "/robots",
            {
                "name": name,
                "description": "platform-registry upstream",
                "level": "system",
                "permissions": PERMISSIONS,
                **DESIRED,
            },
        )
        if status != 201:
            fail(f"creating robot {username} failed: {status} {body}")
        robot = {"id": body["id"]}
        log(f"robot {username} created")
    elif normalized(robot["permissions"]) != normalized(PERMISSIONS) or any(
        robot.get(k) != v for k, v in DESIRED.items()
    ):
        status, body = harbor("PUT", f"/robots/{robot['id']}", {**robot, "permissions": PERMISSIONS, **DESIRED})
        if status != 200:
            fail(f"updating robot {username} failed: {status} {body}")
        log(f"robot {username} permissions, disable and duration reconciled")
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
        _, current = harbor("GET", f"/robots/{robot['id']}")
        state = {k: current.get(k) for k in ("disable", "duration", "expires_at")} if isinstance(current, dict) else current
        fail(f"credentials of {username} still rejected: {status} {body} {state}")
    log(f"robot {username} secret set")


def main():
    robot = check_secrets()
    wait_for_harbor()
    ensure_configuration()
    ensure_project()
    ensure_robot(*robot)
    log("bootstrap finished")


if __name__ == "__main__":
    main()
