"""
One-command verification.

Starts the API (in-process), starts the web app, runs every test suite, then
shuts both down and prints a summary.

Usage (from the accredraft folder):
    backend\\.venv\\Scripts\\python.exe verify.py

Notes
-----
The API runs inside this process rather than as a detached child, which avoids
orphaned servers holding the port. On Windows two processes can bind the same
port, splitting incoming connections and causing spurious resets, so any stale
listener on the app ports is stopped first.

Exit code is 0 only when all suites pass.
"""
import os
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, "backend")
FRONTEND = os.path.join(ROOT, "frontend")
PY = os.path.join(BACKEND, ".venv", "Scripts", "python.exe")

API_PORT = 8000
WEB_PORT = 3000
API = f"http://127.0.0.1:{API_PORT}"
WEB = f"http://127.0.0.1:{WEB_PORT}"


def up(url, timeout=3.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def free_ports():
    """Stop stale listeners on the app ports (Windows allows duplicate binds)."""
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return
    pids = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[3].upper() == "LISTENING":
            if parts[1].rsplit(":", 1)[-1] in (str(API_PORT), str(WEB_PORT)):
                pids.add(parts[4])
    for pid in pids:
        subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
        print(f"  stopped stale listener (pid {pid})")
    if pids:
        time.sleep(1.5)


def wait_for(url, label, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if up(url):
            print(f"  {label} ready")
            return True
        time.sleep(0.5)
    print(f"  {label} DID NOT START")
    return False


def start_api():
    """Run uvicorn in a background thread of this process."""
    sys.path.insert(0, BACKEND)
    os.chdir(BACKEND)
    import uvicorn
    from app.main import app as fastapi_app

    config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=API_PORT, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True, name="uvicorn").start()
    return server


def main() -> int:
    if not os.path.exists(PY):
        print(f"Missing virtualenv python at {PY}\nRun backend\\run.bat first.")
        return 2

    print("Services")
    free_ports()

    print("  starting API (in-process) ...")
    server = start_api()
    if not wait_for(f"{API}/api/health", "API"):
        return 2

    if not os.path.isdir(os.path.join(FRONTEND, "node_modules")):
        print("  frontend dependencies missing - run: cd frontend && npm install")
        server.should_exit = True
        return 2

    if not os.path.exists(os.path.join(FRONTEND, ".next", "BUILD_ID")):
        print("  building frontend ...")
        if subprocess.run(["npm", "run", "build"], cwd=FRONTEND, shell=True).returncode != 0:
            print("  frontend build failed")
            server.should_exit = True
            return 2

    print("  starting web ...")
    web_log = open(os.path.join(FRONTEND, "web.log"), "ab")
    web = subprocess.Popen(
        ["node", "node_modules/next/dist/bin/next", "start", "-p", str(WEB_PORT)],
        cwd=FRONTEND, stdout=web_log, stderr=subprocess.STDOUT,
    )
    if not wait_for(f"{WEB}/login", "web"):
        web.terminate()
        server.should_exit = True
        return 2

    suites = [
        ("workflow", BACKEND, [PY, "tests/test_e2e.py"]),
        ("docx fidelity", BACKEND, [PY, "tests/test_docx_output.py"]),
        ("full stack", FRONTEND, [PY, os.path.join(FRONTEND, "tests", "verify_stack.py")]),
    ]

    results = []
    try:
        for name, cwd, cmd in suites:
            print(f"\n{'=' * 62}\nSUITE: {name}\n{'=' * 62}", flush=True)
            proc = subprocess.run(cmd, cwd=cwd)
            results.append((name, proc.returncode == 0))
    finally:
        web.terminate()
        try:
            web.wait(timeout=10)
        except subprocess.TimeoutExpired:
            web.kill()
        server.should_exit = True

    print(f"\n{'=' * 62}\nSUMMARY\n{'=' * 62}")
    for name, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} suites passed")
    if failed:
        print("\nCheck backend/server.log and frontend/web.log for service errors.")
    else:
        print("\nAll green. Start the app with backend\\run.bat and frontend\\run.bat")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
