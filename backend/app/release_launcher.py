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
        "LAW_RAG_OCR_MODEL_ROOT": str(asset_root / "ocr-models"),
        "LAW_RAG_OCR_MODEL_MANIFEST": str(asset_root / "release" / "ocr-models-manifest.json"),
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


def _print_ocr_probe(probe) -> None:
    print("Law-Rag OCR Runtime")
    print(f"ready: {'YES' if probe.ready else 'NO'}")
    print(f"state: {probe.state}")
    print(f"paddlepaddle: {probe.paddle_version or 'missing'}")
    print(f"paddleocr: {probe.paddleocr_version or 'missing'}")
    print(f"modules_imported: {'YES' if probe.modules_imported else 'NO'}")
    print(f"native_check_run: {'YES' if probe.native_check_run else 'NO'}")
    print(probe.detail)


def _print_ocr_model_probe(probe) -> None:
    print("Law-Rag OCR Models")
    print(f"ready: {'YES' if probe.ready else 'NO'}")
    print(f"state: {probe.state}")
    print(f"model_root: {probe.model_root or 'missing'}")
    print(f"detection: {probe.detection_model or 'missing'}")
    print(f"recognition: {probe.recognition_model or 'missing'}")
    print(probe.detail)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Law-Rag local Windows release launcher")
    parser.add_argument("--diagnose", action="store_true", help="Run non-mutating diagnostics and exit.")
    parser.add_argument(
        "--diagnose-ocr-runtime",
        action="store_true",
        help="Import the pinned PaddlePaddle/PaddleOCR runtime, run Paddle's local native self-check, and exit without initializing OCR models.",
    )
    parser.add_argument(
        "--diagnose-ocr-models",
        action="store_true",
        help="Verify the packaged PP-OCR model file set and SHA-256 values without initializing inference.",
    )
    parser.add_argument(
        "--diagnose-ocr-inference",
        type=Path,
        metavar="IMAGE",
        help="Run the production PaddleOCR adapter on one local image using only verified packaged model directories.",
    )
    parser.add_argument("--json", action="store_true", help="With a diagnostic mode, print machine-readable JSON.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the local workstation in a browser.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    configure_release_environment()

    if args.diagnose_ocr_runtime:
        from .ocr_runtime import probe_ocr_runtime

        probe = probe_ocr_runtime(import_modules=True, run_native_check=True)
        if args.json:
            print(json.dumps(probe.model_dump(), ensure_ascii=False, indent=2))
        else:
            _print_ocr_probe(probe)
        return 0 if probe.ready else 3

    if args.diagnose_ocr_models:
        from .ocr_models import probe_ocr_models

        probe = probe_ocr_models()
        if args.json:
            print(json.dumps(probe.model_dump(), ensure_ascii=False, indent=2))
        else:
            _print_ocr_model_probe(probe)
        return 0 if probe.ready else 4

    if args.diagnose_ocr_inference is not None:
        image_path = args.diagnose_ocr_inference.expanduser().resolve()
        if not image_path.is_file():
            print(f"[ERROR] OCR diagnostic image does not exist: {image_path}")
            return 4
        try:
            from .ocr import PaddleOcrProvider

            blocks = PaddleOcrProvider().recognize(image_path, page_number=1)
        except Exception as exc:
            print(f"[ERROR] Offline OCR inference failed: {type(exc).__name__}: {exc}")
            return 4
        payload = {
            "ready": bool(blocks),
            "block_count": len(blocks),
            "texts": [block.text for block in blocks],
            "confidences": [block.confidence for block in blocks],
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("Law-Rag Offline OCR Inference")
            print(f"block_count: {len(blocks)}")
            for block in blocks:
                print(block.text)
        return 0 if blocks else 4

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

    from .pipeline_recovery import reconcile_interrupted_pipelines

    recovered = reconcile_interrupted_pipelines()
    if recovered:
        print(f"[Law-Rag] Marked {recovered} interrupted Job(s) as retry-required after restart.")

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
