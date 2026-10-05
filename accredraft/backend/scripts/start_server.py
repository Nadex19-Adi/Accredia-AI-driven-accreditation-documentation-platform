"""
Start the AccreditDraft API in the background and wait until it is healthy.

Usage:
    .venv\\Scripts\\python.exe scripts\\start_server.py [--reload]

Writes output to backend/server.log. Idempotent: if the API is already
answering /api/health, it exits successfully without starting a second one.
"""
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEALTH = "http://127.0.0.1:8000/api/health"

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def is_ready(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(HEALTH, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def main() -> int:
    if is_ready():
        print("API already running (health OK) ->", HEALTH)
        return 0

    os.chdir(ROOT)
    reload_flag = ["--reload"] if "--reload" in sys.argv else []
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    log = open("server.log", "ab")

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", "8000", *reload_flag],
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    print(f"launched API pid={proc.pid}")

    deadline = time.time() + 60
    while time.time() < deadline:
        if is_ready():
            print("API ready -> http://127.0.0.1:8000  (docs: /docs, log: backend/server.log)")
            return 0
        time.sleep(1)

    print("TIMEOUT: API did not become ready. See backend/server.log", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
