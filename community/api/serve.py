"""Serve the read-API (uvicorn) + dashboard (Streamlit) together — `./cm ui`.

The dashboard talks to the API over HTTP only (CM_API_BASE env); it never
touches the DB. Ctrl-C stops both processes.
"""
from __future__ import annotations

import os
import pathlib
import signal
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def serve_ui(api_port: int = 8400, dash_port: int = 8501) -> None:
    py = sys.executable
    env = {**os.environ, "CM_API_BASE": f"http://127.0.0.1:{api_port}/api/v1",
           "PYTHONPATH": str(ROOT)}
    api = subprocess.Popen(
        [py, "-m", "uvicorn", "community.api.read_api:app",
         "--host", "127.0.0.1", "--port", str(api_port), "--log-level", "warning"],
        cwd=ROOT, env=env)
    dash = subprocess.Popen(
        [py, "-m", "streamlit", "run", str(ROOT / "dashboard" / "app.py"),
         "--server.port", str(dash_port), "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        cwd=ROOT, env=env)
    print(f"read-API  → http://127.0.0.1:{api_port}/api/v1  (docs: /docs)")
    print(f"dashboard → http://127.0.0.1:{dash_port}")

    def _stop(*_):
        for p in (api, dash):
            p.terminate()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    try:
        dash.wait()
    finally:
        _stop()
