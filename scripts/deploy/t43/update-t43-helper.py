"""Offline validation only: no application import, database access, or network."""
import hashlib
import json
import pathlib
import re
import sys
from urllib.parse import urlsplit

MOUNTS = {
    "/app/var/assets": "asset_inventory_data",
    "/app/var/risk-uploads": "risk_upload_data",
    "/app/var/comprehensive-exports": "comprehensive_export_data",
    "/app/var/adm": "adm_data",
    "/app/var/data-workbench": "data_workbench_data",
    "/app/var/hr-mail": "hr_mail_data",
    "/app/var/risk-verification": "risk_verification_data",
}
PILOT_TARGET = "/app/var/airline-rebates"
PILOT_VOLUME = "airline_rebate_pilot_data"


def require(ok, message):
    if not ok:
        raise SystemExit("ERROR: " + message)


def pip_settings(c):
    args = c["services"]["api"].get("build", {}).get("args", {})
    index = args.get("PIP_INDEX_URL", "https://pypi.tuna.tsinghua.edu.cn/simple")
    require(isinstance(index, str), "pip index must be an HTTPS URL")
    parsed = urlsplit(index)
    require(parsed.scheme == "https" and parsed.hostname
            and not parsed.username and not parsed.password and not parsed.query
            and not parsed.fragment and parsed.path.rstrip("/").endswith("/simple")
            and not any(char.isspace() for char in index),
            "pip index must use HTTPS /simple without credentials, query, or fragment")
    timeout = str(args.get("PIP_TIMEOUT", "60"))
    retries = str(args.get("PIP_RETRIES", "3"))
    require(timeout.isascii() and timeout.isdigit() and 5 <= int(timeout) <= 300,
            "pip timeout must be an integer from 5 to 300")
    require(retries.isascii() and retries.isdigit() and 0 <= int(retries) <= 10,
            "pip retries must be an integer from 0 to 10")
    return index, timeout, retries


def validate(c, runtime=False):
    services = c.get("services", {})
    active = {n for n, s in services.items() if not s.get("profiles")}
    require(active == {"api", "web"}, "Default services must be api/web only")
    if runtime:
        require(set(services) == {"api", "web"}, "Worker found in runtime configuration")
    for name in ("api", "web"):
        s = services[name]
        require(not s.get("privileged"), "Privileged service forbidden")
        require(not s.get("network_mode"), "Custom network mode forbidden")
        require(not s.get("entrypoint"), "Custom entrypoint needs review")
        require(set(s.get("depends_on", {})) <= {"api", "web"}, "Worker dependency forbidden")
        require(set(s.get("networks", {})) == {"default"}, "Unexpected network")
        require(s.get("restart") == "unless-stopped", "Unexpected restart policy")
        require(not s.get("post_start") and not s.get("pre_stop"), "Lifecycle hooks need review")
        health = (["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5160/api/health', timeout=3)"]
                  if name == "api" else ["CMD", "wget", "-q", "-O", "-", "http://127.0.0.1/healthz"])
        require(s.get("healthcheck", {}).get("test") == health
                and not s.get("healthcheck", {}).get("disable"), "Health command needs review")
        ports = s.get("ports", [])
        expected = (5160, "5160") if name == "api" else (80, "1818")
        require(len(ports) == 1 and ports[0].get("target") == expected[0]
                and str(ports[0].get("published")) == expected[1]
                and ports[0].get("protocol", "tcp") == "tcp", "Unexpected port mapping")
        if runtime:
            require(re.fullmatch(r"sha256:[0-9a-f]{64}", s.get("image", "")), "Immutable image ID required")
            require("build" not in s, "Runtime must not build images")
    require(not services["api"].get("command") and not services["web"].get("command"),
            "Custom command needs review")
    env = services["api"].get("environment", {})
    if not runtime:
        pip_settings(c)
    for key in ("HR_MAIL_SEND_ENABLED", "ADM_EXTERNAL_DELIVERY_ENABLED", "AUTH_AUTO_CREATE_TABLES"):
        require(str(env.get(key, "")).lower() == "false", "Unsafe switch: " + key)
    for key in ("AUTH_BOOTSTRAP_ADMIN_USERNAME", "AUTH_BOOTSTRAP_ADMIN_PASSWORD"):
        require(env.get(key) == "", "Bootstrap credentials must be empty")
    require(str(env.get("AUTH_ENABLED", "true")).lower() == "true", "Authentication must remain enabled")
    require(env.get("HIVE_HOST") == "172.16.2.217", "Hive must use reviewed private endpoint")
    mounts = services["api"].get("volumes", [])
    expected = MOUNTS.copy()
    pilot = env.get("AIRLINE_REBATE_PILOT_ROOT") or ""
    require(pilot in ("", PILOT_TARGET), "Unexpected airline rebate pilot root")
    if pilot or (not runtime and any(m.get("target") == PILOT_TARGET for m in mounts)):
        expected[PILOT_TARGET] = PILOT_VOLUME
    require(len(mounts) == len(expected), "Unexpected API mount count")
    require({m.get("target") for m in mounts} == set(expected), "Unexpected API mount targets")
    for mount in mounts:
        key = expected[mount["target"]]
        require(mount.get("type") == "volume" and mount.get("source") == key, "Unexpected mount source")
        require(c.get("volumes", {}).get(key, {}).get("name") == "data_report_" + key, "Unexpected volume name")
        if runtime:
            require(c["volumes"][key].get("external") is True, "Existing external volume required")
    require(not services["web"].get("volumes"), "Unexpected frontend mount")
    if runtime:
        require(c.get("networks", {}).get("default") == {
            "name": "data_report_default", "external": True
        }, "Existing external network required")


def render(c, api_id, web_id):
    # Only retain explicitly needed runtime fields; no candidate build/hooks/extra services.
    for name, image in (("api", api_id), ("web", web_id)):
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", image), "Invalid image ID")
    allowed = {"environment", "ports", "volumes", "restart", "healthcheck", "networks"}
    services = {}
    for name, image in (("api", api_id), ("web", web_id)):
        services[name] = {k: v for k, v in c["services"][name].items() if k in allowed}
        services[name]["image"] = image
    api = services["api"]
    if not (api.get("environment", {}).get("AIRLINE_REBATE_PILOT_ROOT") or ""):
        api["volumes"] = [m for m in api.get("volumes", []) if m.get("target") != PILOT_TARGET]
    volumes = {m["source"]: {"name": "data_report_" + m["source"], "external": True}
               for m in api.get("volumes", [])}
    result = {
        "name": "data_report", "services": services,
        "volumes": volumes,
        "networks": {"default": {"name": "data_report_default", "external": True}},
    }
    validate(result, runtime=True)
    return result


def verify_backend(root, lock):
    files = {}
    backend = root / "backend"
    require(backend.is_dir() and not backend.is_symlink(), "Missing or symlinked backend")
    for path in backend.rglob("*"):
        require(not path.is_symlink(), "Symlink in backend needs review")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = lock["files"]
    changed = sorted(n for n in files.keys() | expected.keys() if files.get(n) != expected.get(n))
    if changed:
        print("Backend differs from reviewed baseline; no application deployment attempted:", file=sys.stderr)
        for name in changed:
            print(name, file=sys.stderr)
        raise SystemExit(1)


def main():
    action = sys.argv[1]
    if action == "verify-backend":
        lock = json.loads(pathlib.Path("/candidate/scripts/deploy/t43/reviewed-backend.json").read_text())
        verify_backend(pathlib.Path("/candidate"), lock)
        print("OK: backend matches reviewed baseline " + lock["commit"])
        return
    c = json.load(sys.stdin)
    if action == "capture-live":
        template = json.loads(pathlib.Path(sys.argv[2]).read_text())
        by_name = {item["Name"].lstrip("/"): item for item in c}
        for name in ("api", "web"):
            live = by_name["data_report-" + name + "-1"]
            template["services"][name]["environment"] = dict(
                value.split("=", 1) for value in live["Config"]["Env"]
            )
            template["services"][name]["image"] = live["Image"]
        validate(template, runtime=True)
        json.dump(template, sys.stdout, ensure_ascii=False, indent=2)
        print()
    elif action == "validate-health":
        require(c.get("success") is True and c.get("data", {}).get("status") == "UP", "Health response is not UP")
        print("OK: frontend/API proxy health")
    elif action in ("validate-source", "validate-runtime"):
        validate(c, runtime=action == "validate-runtime")
        print("OK: configuration validated; secrets not printed")
    elif action == "render":
        json.dump(render(c, sys.argv[2], sys.argv[3]), sys.stdout, ensure_ascii=False, indent=2)
        print()
    elif action == "pilot-volume":
        validate(c)
        print("enabled" if c["services"]["api"]["environment"].get("AIRLINE_REBATE_PILOT_ROOT") else "disabled")
    elif action == "build-mirror":
        value = c["services"]["api"].get("build", {}).get("args", {}).get("DOCKERHUB_MIRROR", "docker.io")
        require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._:/-]+", value), "Invalid mirror name")
        print(value)
    elif action == "build-pip-settings":
        print("\n".join(pip_settings(c)))
    else:
        raise SystemExit("Unknown action")


if __name__ == "__main__":
    main()
