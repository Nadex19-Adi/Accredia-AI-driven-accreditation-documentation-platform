"""
Stop the AccreditDraft API and web app.

Usage (from the accredraft folder):
    backend\\.venv\\Scripts\\python.exe stop.py

Stops whatever is listening on the app ports (8000 and 3000). Useful because
Windows allows two processes to bind the same port, and a leftover server
splits incoming connections and causes unrelated-looking failures.
"""
import os
import subprocess
import sys

PORTS = {8000: "API", 3000: "web"}


def listeners():
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception as exc:
        print(f"could not read netstat: {exc}")
        return {}
    found = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[3].upper() == "LISTENING":
            try:
                port = int(parts[1].rsplit(":", 1)[1])
            except ValueError:
                continue
            if port in PORTS:
                found.setdefault(port, set()).add(parts[4])
    return found


def main() -> int:
    found = listeners()
    if not found:
        print("Nothing listening on 8000 or 3000.")
        return 0

    stopped = 0
    for port, pids in sorted(found.items()):
        for pid in pids:
            result = subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
            if result.returncode == 0:
                print(f"stopped {PORTS[port]} on :{port} (pid {pid})")
                stopped += 1
            else:
                print(f"could not stop pid {pid} on :{port} "
                      f"(try running as administrator)")
    print(f"\n{stopped} process(es) stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
