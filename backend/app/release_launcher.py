from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Sequence


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None))


def release_executable_dir() -> Path:
    if _frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def release_asset_root() -> Path:
    configured = os.getenv("LAW_RAG_RELEASE_ASSET_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root).resolve()
    return release_executable_dir()


def configure_release_environment() -> dict[str, str]:
    """Set release defaults without replacing explicit user/operator overrides."""

    executable_dir = release_executable_dir()
    asset_root = release_asset_root()
    defaults = {
        "LAW_RAG_RUNTIME_DIR": str(executable_dir / "runtime"),
        "LAW_RAG_LEGAL_DB": str(asset_root / "public-assets" / "legal" / "legal.db"),
        "LAW_RAG_RETRIEVAL_DB": str(asset_root / "public-assets" / "legal" / "retrieval.db"),
        "LAW_RAG_FRONTEND_DIST": str(asset_root / "frontend-dist"),
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)
    return {key: os.environ[key] for key in defaults}


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _print_health(report) -> None:
    print("Law-Rag Runtime Health")
    print(f"base_app_ready: {'YES' if report.base_app_ready else 'NO'}")
    print(f"action_required: {'YES' if report.action_required else 'NO'}")
    for check in report.checks:
        print(f"[{check.state.value}] {check.label}: {check.detail}")
        if check.action:
            print(f"  action: {check.action}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Law-Rag local Windows release launcher")
    parser.add_argument("--diagnose", action="store_true", help="Run non-mutating diagnostics and exit.")
    parser.add_argument("--json", action="store_true", help="With --diagnose, print machine-readable JSON.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the local workstation in a browser.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    configure_release_environment()

    # Import diagnostics only after release paths are configured. The diagnostic
    # service is provider-free and does not rebuild/download/mutate runtime data.
    from .startup_diagnostics import inspect_startup_health

    report = inspect_startup_health()
    if args.diagnose:
        if args.json:
            print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
        else:
            _print_health(report)
        return 0 if report.base_app_ready else 2

    if not report.base_app_ready:
        _print_health(report)
        print("[ERROR] Base runtime is not ready. No server was started and no recovery action was run automatically.")
        return 2

    if args.host not in {"127.0.0.1", "localhost"}:
        print("[ERROR] The release launcher only permits loopback binding.")
        return 2
    host = "127.0.0.1"
    if not 1 <= args.port <= 65535:
        print("[ERROR] Port must be between 1 and 65535.")
        return 2
    if not _port_available(host, args.port):
        print(f"[ERROR] http://{host}:{args.port} is already in use. Law-Rag was not started twice.")
        return 2

    url = f"http://{host}:{args.port}/"
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    from .main import app
    import uvicorn

    print(f"[Law-Rag] Local workstation: {url}")
    print("[Law-Rag] Contract/runtime data remains local except explicit DeepSeek/Kimi calls initiated by the user.")
    uvicorn.run(app, host=host, port=args.port, log_level="info", access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
