"""Verify the full stack: frontend pages + API proxy + one live API call."""
import json
import urllib.error
import urllib.request

FRONT = "http://127.0.0.1:3000"
BACK = "http://127.0.0.1:8000"

checks = []


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def check(name, ok, detail=""):
    checks.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail and not ok else ""))


print("\nBackend")
status, body = get(f"{BACK}/api/health")
check("backend health", status == 200 and b"ok" in body, f"{status}")

print("\nFrontend pages")
for path in ["/login", "/", "/templates"]:
    status, body = get(FRONT + path)
    check(f"GET {path}", status == 200 and b"AccreditDraft" in body, f"status={status}")

# The login form must be server-rendered, not an empty shell.
status, login_html = get(f"{FRONT}/login")
check("login renders email input", b'type="email"' in login_html or b'name="email"' in login_html)
check("login renders password input", b'type="password"' in login_html)

# A project detail route must resolve (dynamic segment).
status, _ = get(f"{FRONT}/projects/00000000-0000-0000-0000-000000000000")
check("GET /projects/[id] resolves", status in (200, 404), f"status={status}")

print("\nAPI proxy (frontend -> backend)")
status, body = get(f"{FRONT}/api/health")
check("GET /api/health via proxy", status == 200 and b"ok" in body, f"{status} {body[:80]!r}")

# Login through the proxy, exactly as the browser does.
req = urllib.request.Request(
    f"{FRONT}/api/auth/login",
    data=json.dumps({"email": "admin@example.com", "password": "admin12345"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read())
        status = r.status
except urllib.error.HTTPError as e:
    status, payload = e.code, {}
check("login via proxy", status == 200 and "access_token" in payload, f"{status}")

token = payload.get("access_token")
if token:
    status, body = get(f"{FRONT}/api/templates", {"Authorization": f"Bearer {token}"})
    try:
        templates = json.loads(body)
    except Exception:
        templates = []
    check("authorized API call via proxy", status == 200 and len(templates) > 0, f"{status}")

passed = sum(1 for _, ok, _ in checks if ok)
print(f"\n{'='*50}\nSTACK RESULT: {passed}/{len(checks)} checks passed\n{'='*50}")
for name, ok, detail in checks:
    if not ok:
        print(f"  FAILED: {name} {detail}")
raise SystemExit(0 if passed == len(checks) else 1)
