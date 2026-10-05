"""
Start the Next.js frontend in the background and wait until /login responds.

Usage:
    python scripts/start_web.py          # production (run `npm run build` first)
    python scripts/start_web.py --dev    # development server

Writes output to frontend/web.log.
"""
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "http://127.0.0.1:3000/login"

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def is_ready(timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(URL, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def main() -> int:
    if is_ready():
        print("Frontend already running ->", URL)
        return 0

    os.chdir(ROOT)
    dev = "--dev" in sys.argv
    args = ["node", "node_modules/next/dist/bin/next", "dev" if dev else "start", "-p", "3000"]

    log = open("web.log", "ab")
    proc = subprocess.Popen(
        args,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    print(f"launched web pid={proc.pid} ({'dev' if dev else 'production'})")

    deadline = time.time() + 90
    while time.time() < deadline:
        if is_ready():
            print("Frontend ready -> http://127.0.0.1:3000  (log: frontend/web.log)")
            return 0
        time.sleep(1)

    print("TIMEOUT: frontend did not become ready. See frontend/web.log", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
