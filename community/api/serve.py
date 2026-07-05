"""Serve the read-API (uvicorn) + the Next.js webapp together — `./cm ui`.

The webapp talks to the API over HTTP only (CORS-allowed on :3000); it never
touches the DB. Ctrl-C stops both processes.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import signal
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
WEBAPP = ROOT / "webapp"


def serve_ui(api_port: int = 8400, dash_port: int = 3000) -> None:
    py = sys.executable
    env = {**os.environ, "PYTHONPATH": str(ROOT),
           "NEXT_PUBLIC_API_BASE": f"http://127.0.0.1:{api_port}/api/v1"}
    procs: list[subprocess.Popen] = []
    specs: list[tuple[list[str], object]] = []   # (args, cwd) for respawn
    api = subprocess.Popen(
        [py, "-m", "uvicorn", "community.api.read_api:app",
         "--host", "127.0.0.1", "--port", str(api_port), "--log-level", "warning"],
        cwd=ROOT, env=env)
    procs.append(api)
    specs.append((api.args, ROOT))
    print(f"read-API → http://127.0.0.1:{api_port}/api/v1  (docs: /docs)")

    npm = shutil.which("npm")
    if not WEBAPP.is_dir():
        print("webapp/ not found — the Next.js frontend hasn't been created yet. "
              "API is serving; create webapp/ (or pull it) and rerun ./cm ui.")
    elif npm is None:
        print("npm not found on PATH — install Node (brew install node), then rerun ./cm ui.")
    elif not (WEBAPP / "node_modules").is_dir():
        print("webapp/node_modules missing — run: cd webapp && npm install  — then rerun ./cm ui.")
    else:
        dash = subprocess.Popen(
            [npm, "run", "dev", "--", "-p", str(dash_port)], cwd=WEBAPP, env=env)
        procs.append(dash)
        specs.append((dash.args, WEBAPP))
        print(f"webapp   → http://127.0.0.1:{dash_port}")

    def _stop(*_):
        for p in procs:
            p.terminate()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    try:
        # Supervise BOTH children: if either dies (e.g. someone pkills the
        # frontend), restart it instead of letting the survivor orphan/exit —
        # a dead API behind a live frontend renders every page blank.
        import time
        while True:
            for i, p_ in enumerate(list(procs)):
                if p_.poll() is not None:
                    args, cwd = specs[i]
                    print(f"child exited (pid {p_.pid}) — restarting it")
                    procs[i] = subprocess.Popen(args, cwd=cwd, env=env)
            time.sleep(2)
    finally:
        _stop()
