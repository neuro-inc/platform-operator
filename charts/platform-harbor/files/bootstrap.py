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
RETENTION = json.loads(os.environ.get("RETENTION") or "{}")
GC = json.loads(os.environ.get("GC") or "{}")
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
MAX_DAYS = 36500


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


def retention_rule(rule):
    return {
        "disabled": False,
        "action": "retain",
        "template": rule["template"],
        "params": {rule["template"]: rule["value"]} if "value" in rule else {},
        "tag_selectors": [
            {
                "kind": "doublestar",
                "decoration": "matches",
                "pattern": rule.get("tags", "**"),
                "extras": json.dumps({"untagged": rule.get("untagged", False)}),
            }
        ],
        "scope_selectors": {
            "repository": [
                {
                    "kind": "doublestar",
                    "decoration": rule["repositories"].get("decoration", "repoMatches"),
                    "pattern": rule["repositories"]["pattern"],
                }
            ]
        },
    }


def retention_trigger(cron):
    return {"kind": "Schedule" if cron else "", "settings": {"cron": cron}, "references": {}}


def retention_state(policy):
    trigger = policy.get("trigger") or {}
    return {
        "algorithm": policy.get("algorithm"),
        "trigger": (trigger.get("kind") or "", (trigger.get("settings") or {}).get("cron") or ""),
        "rules": [
            (
                r["template"],
                r["action"],
                r.get("disabled", False),
                r.get("params") or {},
                [(s["kind"], s["decoration"], s["pattern"], json.loads(s.get("extras") or "{}")) for s in r["tag_selectors"]],
                [(s["kind"], s["decoration"], s["pattern"]) for s in r["scope_selectors"]["repository"]],
            )
            for r in policy.get("rules") or []
        ],
    }


def check_retention_rules(rules):
    status, metadata = harbor("GET", "/retentions/metadatas")
    if status != 200:
        fail(f"reading retention metadata failed: {status} {metadata}")
    templates = {t["rule_template"]: t.get("params") or [] for t in metadata["templates"]}
    decorations = {d for s in metadata["scope_selectors"] for d in s["decorations"]}
    for n, rule in enumerate(rules):
        if rule.get("template") not in templates:
            fail(f"retention rule {n}: template {rule.get('template')} is not one of {', '.join(sorted(templates))}")
        if not (rule.get("repositories") or {}).get("pattern"):
            fail(f"retention rule {n}: repositories.pattern is required")
        decoration = rule["repositories"].get("decoration", "repoMatches")
        if decoration not in decorations:
            fail(f"retention rule {n}: decoration {decoration} is not one of {', '.join(sorted(decorations))}")
        params = templates[rule["template"]]
        value = rule.get("value")
        if params and not (isinstance(value, int) and not isinstance(value, bool) and value > 0):
            fail(f"retention rule {n}: template {rule['template']} needs a positive integer value, got {value!r}")
        if not params and value is not None:
            fail(f"retention rule {n}: template {rule['template']} takes no value, got {value!r}")
        if any(str(p.get("unit")).lower() == "days" for p in params) and value > MAX_DAYS:
            fail(f"retention rule {n}: template {rule['template']} allows at most {MAX_DAYS} days, got {value}")


def retention_schedules():
    schedules, page = {}, 1
    while True:
        status, body = harbor("GET", f"/schedules?page={page}&page_size=100")
        if status != 200:
            fail(f"listing schedules failed: {status} {body}")
        for schedule in body:
            if schedule.get("vendor_type") == "RETENTION":
                schedules.setdefault(schedule["vendor_id"], []).append(schedule["cron"])
        if len(body) < 100:
            return schedules
        page += 1


def armed(policy):
    kind, cron = retention_state(policy)["trigger"]
    return kind == "Schedule" and bool(cron)


def scoped_to(policy_id, project_id):
    status, policy = harbor("GET", f"/retentions/{policy_id}")
    return status == 200 and (policy.get("scope") or {}).get("ref") == project_id


def read_retention(policy_id):
    status, policy = harbor("GET", f"/retentions/{policy_id}")
    if status != 200:
        fail(f"reading retention policy {policy_id} failed: {status} {policy}")
    return policy


def put_retention(policy_id, policy):
    status, body = harbor("PUT", f"/retentions/{policy_id}", {**policy, "id": policy_id})
    if status != 200:
        fail(f"updating retention policy {policy_id} failed: {status} {body}")


def delete_retention(policy_id):
    status, body = harbor("DELETE", f"/retentions/{policy_id}")
    if status != 200:
        fail(f"deleting retention policy {policy_id} failed: {status} {body}")


def create_retention(desired):
    status, body = harbor("POST", "/retentions", desired)
    if status != 201:
        fail(f"creating retention policy for {PROJECT} failed: {status} {body}")
    status, project = harbor("GET", f"/projects/{urllib.parse.quote(PROJECT)}")
    policy_id = int((project.get("metadata") or {}).get("retention_id") or 0) if status == 200 else 0
    if not policy_id:
        fail(f"retention policy for {PROJECT} created but not linked to the project: {status} {project}")
    return policy_id


def ensure_retention():
    if not RETENTION.get("enabled"):
        log("retention is not managed")
        return
    if not RETENTION.get("rules"):
        fail("retention is enabled without rules")
    check_retention_rules(RETENTION["rules"])
    status, project = harbor("GET", f"/projects/{urllib.parse.quote(PROJECT)}")
    if status != 200:
        fail(f"reading project {PROJECT} failed: {status} {project}")
    cron = RETENTION.get("schedule") or ""
    expected = [cron] if cron else []
    desired = {
        "algorithm": "or",
        "rules": [retention_rule(r) for r in RETENTION["rules"]],
        "trigger": retention_trigger(cron),
        "scope": {"level": "project", "ref": project["project_id"]},
    }
    policy_id = int((project.get("metadata") or {}).get("retention_id") or 0) or None
    if policy_id and not scoped_to(policy_id, project["project_id"]):
        fail(f"project {PROJECT} links retention policy {policy_id}, which is missing or belongs to another project")
    schedules = retention_schedules()
    unlinked = [v for v in schedules if v != policy_id and scoped_to(v, project["project_id"])]
    current = read_retention(policy_id) if policy_id else None
    stray = bool(current) and not armed(current) and bool(schedules.get(policy_id))
    if unlinked or stray:
        deleted = unlinked + ([policy_id] if policy_id else [])
        for vendor_id in deleted:
            delete_retention(vendor_id)
        log(f"retention policies {deleted} had schedules outside the values and were deleted")
        policy_id = None
    if policy_id is None:
        policy_id = create_retention(desired)
        log(f"retention policy {policy_id} for {PROJECT} created")
    elif retention_state(current) != retention_state(desired) or sorted(schedules.get(policy_id, [])) != expected:
        if cron:
            put_retention(policy_id, {**desired, "trigger": retention_trigger("")})
        put_retention(policy_id, desired)
        log(f"retention policy {policy_id} updated")
    else:
        log(f"retention policy {policy_id} is up to date")
    current = read_retention(policy_id)
    actual = sorted(retention_schedules().get(policy_id, []))
    if retention_state(current) != retention_state(desired) or actual != expected:
        fail(f"retention policy {policy_id} does not match the values: {current}, schedules {actual}, expected {expected}")


def gc_state(schedule):
    if not schedule or not schedule.get("schedule"):
        return None
    parameters = json.loads(schedule.get("job_parameters") or "{}")
    return {
        "type": schedule["schedule"].get("type"),
        "cron": schedule["schedule"].get("cron"),
        **{k: parameters.get(k) for k in ("delete_untagged", "workers")},
    }


def read_gc():
    status, current = harbor("GET", "/system/gc/schedule")
    if status != 200:
        fail(f"reading garbage collection schedule failed: {status} {current}")
    return gc_state(current)


def ensure_gc():
    if not GC.get("enabled"):
        log("garbage collection is not managed")
        return
    current = read_gc()
    if not GC.get("schedule"):
        if current is None:
            log("garbage collection is not scheduled")
            return
        status, body = harbor("PUT", "/system/gc/schedule", {"schedule": {"type": "None"}})
        if status != 200 or read_gc() is not None:
            fail(f"removing garbage collection schedule failed: {status} {body}")
        log("garbage collection schedule removed")
        return
    parameters = {"delete_untagged": GC.get("deleteUntagged", True), "workers": GC.get("workers", 1)}
    desired = {"schedule": {"type": "Custom", "cron": GC["schedule"]}, "parameters": parameters}
    if current == {"type": "Custom", "cron": GC["schedule"], **parameters}:
        log("garbage collection schedule is up to date")
        return
    method, expected = ("POST", 201) if current is None else ("PUT", 200)
    status, body = harbor(method, "/system/gc/schedule", desired)
    if status != expected or read_gc() != {"type": "Custom", "cron": GC["schedule"], **parameters}:
        fail(f"scheduling garbage collection failed: {status} {body}")
    log(f"garbage collection scheduled at {GC['schedule']}")


def main():
    robot = check_secrets()
    wait_for_harbor()
    ensure_configuration()
    ensure_project()
    ensure_robot(*robot)
    ensure_retention()
    ensure_gc()
    log("bootstrap finished")


if __name__ == "__main__":
    main()
