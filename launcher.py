"""Aegis 2 launcher.

Boots the FastAPI server, opens the default browser, and keeps the process alive.
Designed to be packaged by PyInstaller into a single portable .exe.
"""
from __future__ import annotations

import os
import sys
import time
import socket
import threading
import traceback
import webbrowser
from pathlib import Path


def get_app_root() -> Path:
    """Return the folder containing the launcher binary (or source file).

    When bundled with PyInstaller (``sys.frozen``), use the executable directory
    so that every relative path resolves to the USB-portable folder layout.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def find_free_port(preferred: int = 8765) -> int:
    """Return ``preferred`` if it is free, else an arbitrary free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(host: str, port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            try:
                s.connect((host, port))
                return True
            except OSError:
                time.sleep(0.2)
    return False


def main() -> None:
    root = get_app_root()
    os.environ["MATHCORE_ROOT"] = str(root)
    os.environ["MATHCORE_DATA_DIR"] = str(root / "data")
    os.environ["MATHCORE_STATIC_DIR"] = str(root / "static")

    (root / "data").mkdir(parents=True, exist_ok=True)

    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(root))

    from backend.main import create_app
    import uvicorn

    port = find_free_port(8765)
    host = "127.0.0.1"
    url = f"http://{host}:{port}"

    app = create_app()

    def open_browser() -> None:
        if wait_for_server(host, port):
            webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    print(f"Aegis 2 running at {url}")
    print("Close this window to exit the application.")
    server.run()


def _hold_console_on_error() -> None:
    """Keep the console window open after an error so the user can read it.

    Always attempts ``input()``: under PyInstaller ``console=True`` the
    isatty() check can return False even when the user really did
    double-click the .exe, which silently swallowed earlier crashes.
    """
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    try:
        input("\nPress Enter to close...")
    except (EOFError, OSError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except ModuleNotFoundError as exc:
        print()
        print("=" * 60)
        print("Aegis 2 failed to start: a Python dependency is missing.")
        print(f"  {exc}")
        print()
        print("If you are running from source, activate the virtualenv first:")
        print("    venv\\Scripts\\activate")
        print("    python launcher.py")
        print("Or use launch_dev.bat which does that for you.")
        print("=" * 60)
        _hold_console_on_error()
        sys.exit(1)
    except Exception:
        print()
        print("=" * 60)
        print("Aegis 2 crashed during startup. Full traceback below.")
        print("=" * 60)
        traceback.print_exc()
        print("=" * 60)
        _hold_console_on_error()
        sys.exit(1)
