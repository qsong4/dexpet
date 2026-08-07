"""Unified DexPet entry: start backend, then desktop UI.

Frozen (.app): backend runs in a daemon thread (same process).
Dev mode: backend runs as a subprocess.
"""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from backend.paths import DEFAULT_HOST, DEFAULT_PORT


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _backend_cmd() -> list[str]:
    return [sys.executable, "-m", "backend.main"]


def _wait_health(timeout: float = 20.0) -> bool:
    url = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.25)
    return False


def run_backend() -> None:
    import uvicorn

    from backend.app import create_app

    app = create_app()
    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT, log_level="warning")


def _start_backend_thread() -> threading.Thread:
    thread = threading.Thread(target=run_backend, name="dexpet-backend", daemon=True)
    thread.start()
    return thread


def _start_backend_subprocess() -> subprocess.Popen[bytes]:
    proc = subprocess.Popen(
        _backend_cmd(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    def _cleanup(*_args: object) -> None:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    atexit.register(_cleanup)
    signal.signal(signal.SIGTERM, lambda *_: (_cleanup(), sys.exit(0)))
    return proc


def run_app() -> None:
    if not _wait_health(timeout=0.5):
        if _is_frozen():
            _start_backend_thread()
        else:
            _start_backend_subprocess()
        if not _wait_health():
            print(
                f"DexPet backend failed to start on port {DEFAULT_PORT}",
                file=sys.stderr,
            )
            sys.exit(1)

    from desktop.main import run

    run()


def main() -> None:
    if not _is_frozen():
        root = os.path.dirname(os.path.abspath(__file__))
        if root not in sys.path:
            sys.path.insert(0, root)

    if "--backend" in sys.argv:
        run_backend()
    else:
        run_app()


if __name__ == "__main__":
    main()
