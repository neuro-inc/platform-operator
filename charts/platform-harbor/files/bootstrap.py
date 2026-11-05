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

HARBOR_URL = os.environ["HARBOR_URL"].rstrip("/") + "/api/v2.0"
ADMIN = ("admin", os.environ["HARBOR_ADMIN_PASSWORD"])
PROJECT = os.environ["HARBOR_PROJECT"]
USERNAME = os.environ["HARBOR_USERNAME"]
EMAIL = os.environ["HARBOR_USER_EMAIL"]
SECRET_NAME = os.environ["SECRET_NAME"]
WAIT_SECONDS = int(os.environ.get("WAIT_SECONDS", "900"))
SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
K8S_URL = "https://kubernetes.default.svc"


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


def harbor(method, path, body=None, auth=ADMIN):
    token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
    return call(f"{HARBOR_URL}{path}", method, body, {"Authorization": f"Basic {token}"})


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


def ensure_secret():
    with open(f"{SA_DIR}/namespace") as f:
        path = f"/api/v1/namespaces/{f.read().strip()}/secrets"
    status, body = kube("GET", f"{path}/{SECRET_NAME}")
    if status == 200:
        data = body.get("data") or {}
        if data.get("password") and base64.b64decode(data.get("username", "")).decode() == USERNAME:
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
        "stringData": {"username": USERNAME, "password": password},
    }
    if status == 200:
        status, body = kube("PUT", f"{path}/{SECRET_NAME}", secret)
    else:
        status, body = kube("POST", path, secret)
    if status not in (200, 201):
        fail(f"writing secret {SECRET_NAME} failed: {status} {body}")
    log(f"secret {SECRET_NAME} written")
    return password


def find_user():
    status, body = harbor("GET", f"/users/search?username={urllib.parse.quote(USERNAME)}&page_size=100")
    if status != 200:
        fail(f"searching user {USERNAME} failed: {status} {body}")
    return next((u["user_id"] for u in body if u["username"] == USERNAME), None)


def ensure_user(password):
    user_id = find_user()
    if user_id is None:
        status, body = harbor(
            "POST",
            "/users",
            {"username": USERNAME, "email": EMAIL, "realname": USERNAME, "password": password},
        )
        if status != 201:
            fail(f"creating user {USERNAME} failed: {status} {body}")
        user_id = find_user()
        log(f"user {USERNAME} created")
    elif harbor("GET", "/users/current", auth=(USERNAME, password))[0] == 200:
        log(f"user {USERNAME} exists")
    else:
        status, body = harbor("PUT", f"/users/{user_id}/password", {"new_password": password})
        if status != 200:
            fail(f"resetting password of {USERNAME} failed: {status} {body}")
        log(f"user {USERNAME} password reset")
    status, body = harbor("GET", f"/users/{user_id}")
    if status != 200:
        fail(f"reading user {USERNAME} failed: {status} {body}")
    if body.get("sysadmin_flag"):
        return
    status, body = harbor("PUT", f"/users/{user_id}/sysadmin", {"sysadmin_flag": True})
    if status != 200:
        fail(f"granting sysadmin to {USERNAME} failed: {status} {body}")
    log(f"user {USERNAME} granted sysadmin")


def main():
    wait_for_harbor()
    ensure_project()
    ensure_user(ensure_secret())
    log("bootstrap finished")


if __name__ == "__main__":
    main()
