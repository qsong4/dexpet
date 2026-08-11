"""Launch DexPet backend/desktop in a new session (immune to parent SIGHUP)."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.paths import DEFAULT_HOST, DEFAULT_PORT  # noqa: E402

PY = ROOT / ".venv" / "bin" / "python"
PID_DIR = Path.home() / "Library" / "Application Support" / "DexPet"
LOG_DIR = PID_DIR / "logs"
BACKEND_PORT = DEFAULT_PORT

# Cursor agent seatbelt env markers (Keychain writes fail under seatbelt).
_SANDBOX_ENV_PREFIXES = ("CURSOR_SANDBOX", "__CURSOR_SANDBOX")


def _clean_env() -> dict[str, str]:
    return {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(_SANDBOX_ENV_PREFIXES)
    }


def _stop_pidfile(path: Path) -> None:
    if not path.exists():
        return
    try:
        pid = int(path.read_text().strip())
    except ValueError:
        path.unlink(missing_ok=True)
        return
    subprocess.run(["kill", str(pid)], check=False, capture_output=True)
    time.sleep(0.2)
    subprocess.run(["kill", "-9", str(pid)], check=False, capture_output=True)
    path.unlink(missing_ok=True)


def _pids_listening_on(port: int) -> list[int]:
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def _stop_backend_listeners() -> None:
    """Kill anything still holding the backend port (stale sandboxed processes)."""
    for pid in _pids_listening_on(BACKEND_PORT):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            continue
    time.sleep(0.3)
    for pid in _pids_listening_on(BACKEND_PORT):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def _spawn(module: str, pid_name: str, log_name: str) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    pid_path = PID_DIR / pid_name
    log_path = LOG_DIR / log_name
    _stop_pidfile(pid_path)
    if module == "backend.main":
        _stop_backend_listeners()

    if os.environ.get("CURSOR_SANDBOX"):
        print(
            "warning: launched under CURSOR_SANDBOX; Keychain writes may fail "
            "(API keys fall back to Application Support/DexPet/secrets/)",
            file=sys.stderr,
        )

    log_f = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen(
        [str(PY), "-m", module],
        cwd=str(ROOT),
        stdout=log_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
        env=_clean_env(),
    )
    pid_path.write_text(str(proc.pid))
    return proc.pid


def _wait_health(timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/health", timeout=1
            ) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.25)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    PID_DIR.mkdir(parents=True, exist_ok=True)

    if args.stop:
        _stop_pidfile(PID_DIR / "backend.pid")
        _stop_pidfile(PID_DIR / "desktop.pid")
        _stop_backend_listeners()
        print("stopped")
        return 0

    if not PY.exists():
        print(f"missing {PY}", file=sys.stderr)
        return 1

    bpid = _spawn("backend.main", "backend.pid", "backend.log")
    if not _wait_health():
        print("backend failed to become healthy", file=sys.stderr)
        return 1
    dpid = _spawn("desktop.main", "desktop.pid", "desktop.log")
    time.sleep(2)
    # verify
    alive_b = Path(f"/proc/{bpid}").exists() if sys.platform.startswith("linux") else (
        subprocess.run(["kill", "-0", str(bpid)], capture_output=True).returncode == 0
    )
    alive_d = subprocess.run(["kill", "-0", str(dpid)], capture_output=True).returncode == 0
    print(
        f"port={DEFAULT_PORT} backend={bpid} alive={alive_b} "
        f"desktop={dpid} alive={alive_d}"
    )
    return 0 if alive_b and alive_d else 1


if __name__ == "__main__":
    raise SystemExit(main())
