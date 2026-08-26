from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import webbrowser
from datetime import date
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


def configure_release_environment(*, use_packaged_legal: bool = False) -> dict[str, str]:
    """Set release defaults without replacing explicit user/operator overrides.

    Normal execution uses a writable runtime legal directory. Non-mutating
    diagnostics may point directly at the immutable packaged baseline instead.
    """

    executable_dir = release_executable_dir()
    asset_root = release_asset_root()
    runtime_root = Path(os.getenv("LAW_RAG_RUNTIME_DIR", str(executable_dir / "runtime"))).expanduser().resolve()
    if use_packaged_legal:
        default_legal = asset_root / "public-assets" / "legal" / "legal.db"
        default_retrieval = asset_root / "public-assets" / "legal" / "retrieval.db"
    else:
        default_legal = runtime_root / "legal" / "legal.db"
        default_retrieval = runtime_root / "legal" / "retrieval.db"

    defaults = {
        "LAW_RAG_RUNTIME_DIR": str(runtime_root),
        "LAW_RAG_FRONTEND_DIST": str(asset_root / "frontend-dist"),
        "LAW_RAG_OCR_MODEL_ROOT": str(asset_root / "ocr-models"),
        "LAW_RAG_OCR_MODEL_MANIFEST": str(asset_root / "release" / "ocr-models-manifest.json"),
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)
    for key, value, marker in (
        ("LAW_RAG_LEGAL_DB", str(default_legal), "LAW_RAG_LEGAL_DB_DEFAULT_RUNTIME"),
        ("LAW_RAG_RETRIEVAL_DB", str(default_retrieval), "LAW_RAG_RETRIEVAL_DB_DEFAULT_RUNTIME"),
    ):
        current = os.getenv(key, "").strip()
        marker_value = os.getenv(marker, "").strip()
        stale_implicit_default = False
        if current and marker_value and Path(marker_value).expanduser().resolve() != runtime_root:
            old_default = Path(marker_value).expanduser().resolve() / "legal" / Path(value).name
            stale_implicit_default = Path(current).expanduser().resolve() == old_default
        if not current or stale_implicit_default:
            os.environ[key] = value
            os.environ[marker] = str(runtime_root)
    configured_keys = (*defaults.keys(), "LAW_RAG_LEGAL_DB", "LAW_RAG_RETRIEVAL_DB")
    return {key: os.environ[key] for key in configured_keys}


def _format_exception_chain(exc: BaseException) -> str:
    """Render chained runtime failures without losing the provider root cause."""

    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        detail = str(current).strip()
        parts.append(f"{type(current).__name__}: {detail}" if detail else type(current).__name__)
        if current.__cause__ is not None:
            current = current.__cause__
        elif not current.__suppress_context__:
            current = current.__context__
        else:
            current = None
    return " <- ".join(parts)


def _diagnostic_json(payload: object) -> str:
    """Render machine-readable diagnostics safely on legacy Windows code pages."""

    return json.dumps(payload, ensure_ascii=True, indent=2)


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _select_launch_port(host: str, requested_port: int | None, *, span: int = 100) -> tuple[int, bool]:
    """Choose a loopback port, falling forward for the default desktop launch."""

    start = requested_port if requested_port is not None else 8000
    if requested_port is not None:
        if _port_available(host, start):
            return start, False
        raise RuntimeError(f"http://{host}:{start} is already in use. Law-Rag was not started twice.")

    for port in range(start, min(65535, start + span - 1) + 1):
        if _port_available(host, port):
            return port, port != start
    raise RuntimeError(f"No available loopback port was found in {host}:{start}-{start + span - 1}.")


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


def _corpus_diagnostic() -> tuple[bool, dict[str, object]]:
    from .legal.retrieval import get_retrieval_index_summary, retrieve_legal_evidence
    from .legal.retrieval_models import RetrievalRequest, RetrievalState
    from .legal.store import get_summary
    from .storage import legal_db_path, legal_retrieval_index_path

    legal_path = legal_db_path()
    retrieval_path = legal_retrieval_index_path()
    legal = get_summary(legal_path)
    retrieval = get_retrieval_index_summary(retrieval_path, legal_path)
    request = RetrievalRequest(
        query="劳动合同法第四十七条 经济补偿",
        as_of=date(2026, 8, 21),
        top_k=5,
        authority_id_hint="prc-labor-contract-law",
        article_token_hint="第四十七条",
        use_semantic=False,
    )
    try:
        response = retrieve_legal_evidence(legal_path, retrieval_path, request)
    except Exception as exc:
        response = None
        retrieval_error = _format_exception_chain(exc)
    else:
        retrieval_error = None

    exact_candidate = None
    if response is not None:
        exact_candidate = next(
            (
                candidate
                for candidate in response.candidates
                if candidate.authority_id == "prc-labor-contract-law" and candidate.exact_hit
            ),
            None,
        )
    baseline_authority_count = 18
    baseline_version_count = 19
    baseline_article_count = 1507
    ready = bool(
        legal.ready
        and legal.authority_count >= baseline_authority_count
        and legal.version_count >= baseline_version_count
        and legal.article_count >= baseline_article_count
        and retrieval.ready
        and retrieval.lexical_ready
        and retrieval.article_count == legal.article_count
        and response is not None
        and response.state in {RetrievalState.OK, RetrievalState.PARTIAL_COVERAGE}
        and exact_candidate is not None
    )
    payload: dict[str, object] = {
        "ready": ready,
        "legal": {
            "authority_count": legal.authority_count,
            "version_count": legal.version_count,
            "article_count": legal.article_count,
            "excerpt_version_count": legal.excerpt_version_count,
        },
        "retrieval": {
            "ready": retrieval.ready,
            "lexical_ready": retrieval.lexical_ready,
            "semantic_ready": retrieval.semantic_ready,
            "article_count": retrieval.article_count,
        },
        "smoke_query": {
            "state": response.state.value if response else None,
            "authority_id": exact_candidate.authority_id if exact_candidate else None,
            "version_id": exact_candidate.version_id if exact_candidate else None,
            "article_token": exact_candidate.article_token if exact_candidate else None,
            "exact_hit": bool(exact_candidate and exact_candidate.exact_hit),
            "error": retrieval_error,
            "warnings": response.warnings if response else [],
        },
        "baseline_minimum": {
            "authority_count": baseline_authority_count,
            "version_count": baseline_version_count,
            "article_count": baseline_article_count,
        },
    }
    return ready, payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Law-Rag local Windows release launcher")
    parser.add_argument("--diagnose", action="store_true", help="Run non-mutating diagnostics and exit.")
    parser.add_argument(
        "--diagnose-corpus",
        action="store_true",
        help="Verify the packaged/runtime legal baseline and run one offline exact-citation retrieval smoke without modifying runtime data.",
    )
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
    parser.add_argument(
        "--diagnose-desktop-lifecycle",
        action="store_true",
        help="Verify whether the Windows system-tray runtime dependency is available without starting the local server.",
    )
    parser.add_argument(
        "--diagnose-runtime-encryption",
        action="store_true",
        help="Inspect Law-Rag managed runtime-encryption policy/state without enabling or disabling encryption.",
    )
    parser.add_argument("--json", action="store_true", help="With a diagnostic mode, print machine-readable JSON.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the local workstation in a browser.")
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="Disable the Windows tray icon and use the plain local-server lifecycle (automation/debug only).",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    explicit_legal_paths = bool(
        os.getenv("LAW_RAG_LEGAL_DB", "").strip() or os.getenv("LAW_RAG_RETRIEVAL_DB", "").strip()
    )
    use_packaged_legal = (args.diagnose or args.diagnose_corpus) and not explicit_legal_paths
    configure_release_environment(use_packaged_legal=use_packaged_legal)

    if args.diagnose_desktop_lifecycle:
        from .desktop_lifecycle import probe_desktop_lifecycle

        probe = probe_desktop_lifecycle()
        payload = {
            "platform": probe.platform,
            "tray_supported": probe.tray_supported,
            "pystray_available": probe.pystray_available,
            "detail": probe.detail,
        }
        if args.json:
            print(_diagnostic_json(payload))
        else:
            print("Law-Rag Desktop Lifecycle")
            print(_diagnostic_json(payload))
        if os.name == "nt":
            return 0 if probe.pystray_available else 6
        return 0

    if args.diagnose_runtime_encryption:
        from .runtime_encryption import RuntimeEncryptionError, runtime_encryption_overview

        try:
            overview = runtime_encryption_overview()
        except RuntimeEncryptionError as exc:
            print(f"[ERROR] Runtime encryption state could not be inspected: {_format_exception_chain(exc)}")
            return 7
        payload = overview.model_dump(mode="json")
        if args.json:
            print(_diagnostic_json(payload))
        else:
            print("Law-Rag Runtime Encryption")
            print(_diagnostic_json(payload))
        return 0

    if args.diagnose_ocr_runtime:
        from .ocr_runtime import probe_ocr_runtime

        probe = probe_ocr_runtime(import_modules=True, run_native_check=True)
        if args.json:
            print(_diagnostic_json(probe.model_dump()))
        else:
            _print_ocr_probe(probe)
        return 0 if probe.ready else 3

    if args.diagnose_ocr_models:
        from .ocr_models import probe_ocr_models

        probe = probe_ocr_models()
        if args.json:
            print(_diagnostic_json(probe.model_dump()))
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
            print(f"[ERROR] Offline OCR inference failed: {_format_exception_chain(exc)}")
            return 4
        payload = {
            "ready": bool(blocks),
            "block_count": len(blocks),
            "texts": [block.text for block in blocks],
            "confidences": [block.confidence for block in blocks],
        }
        if args.json:
            print(_diagnostic_json(payload))
        else:
            print("Law-Rag Offline OCR Inference")
            print(f"block_count: {len(blocks)}")
            for block in blocks:
                print(block.text)
        return 0 if blocks else 4

    if args.diagnose_corpus:
        try:
            ready, payload = _corpus_diagnostic()
        except Exception as exc:
            ready = False
            payload = {"ready": False, "error": _format_exception_chain(exc)}
        if args.json:
            print(_diagnostic_json(payload))
        else:
            print("Law-Rag Offline Legal Corpus")
            print(f"ready: {'YES' if ready else 'NO'}")
            print(_diagnostic_json(payload))
        return 0 if ready else 5

    from .startup_diagnostics import inspect_startup_health

    if args.diagnose:
        report = inspect_startup_health()
        if args.json:
            print(_diagnostic_json(report.model_dump(mode="json")))
        else:
            _print_health(report)
        return 0 if report.base_app_ready else 2

    if args.host not in {"127.0.0.1", "localhost"}:
        print("[ERROR] The release launcher only permits loopback binding.")
        return 2
    host = "127.0.0.1"
    if args.port is not None and not 1 <= args.port <= 65535:
        print("[ERROR] Port must be between 1 and 65535.")
        return 2

    if not explicit_legal_paths:
        try:
            from .release_corpus import install_packaged_baseline
            from .storage import runtime_dir

            install_packaged_baseline(release_asset_root(), runtime_dir())
        except Exception as exc:
            print(f"[ERROR] Packaged legal baseline could not be installed safely: {_format_exception_chain(exc)}")
            return 2

    from .runtime_encryption import (
        RuntimeEncryptionRequiredError,
        ensure_runtime_encryption_on_startup,
    )

    try:
        encryption = ensure_runtime_encryption_on_startup()
    except RuntimeEncryptionRequiredError as exc:
        print(f"[ERROR] Required runtime encryption is unavailable: {_format_exception_chain(exc)}")
        return 7
    if encryption.state.value == "ENCRYPTED":
        print("[Law-Rag] Job-private runtime roots are protected by Windows EFS; shared legal corpus remains unmanaged by this feature.")
    elif encryption.mode.value != "OFF":
        print(f"[Law-Rag] Runtime encryption state: {encryption.state.value}. {encryption.detail}")
        for warning in encryption.warnings:
            print(f"[Law-Rag] Runtime encryption warning: {warning}")

    report = inspect_startup_health()
    if not report.base_app_ready:
        _print_health(report)
        print("[ERROR] Base runtime is not ready. No server was started and no recovery action was run automatically.")
        return 2

    try:
        launch_port, port_changed = _select_launch_port(host, args.port)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 2

    from .pipeline_recovery import reconcile_interrupted_pipelines

    recovered = reconcile_interrupted_pipelines()
    if recovered:
        print(f"[Law-Rag] Marked {recovered} interrupted Job(s) as retry-required after restart.")

    url = f"http://{host}:{launch_port}/"
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    from .desktop_lifecycle import run_server_with_desktop_lifecycle
    from .main import app
    import uvicorn

    print(f"[Law-Rag] Local workstation: {url}")
    if port_changed:
        print("[Law-Rag] Default port 8000 was busy, so Law-Rag selected the next available local port.")
    print("[Law-Rag] Contract/runtime data remains local except explicit DeepSeek/Kimi calls initiated by the user.")
    if os.name == "nt" and not args.no_tray:
        print("[Law-Rag] System tray: use 'Open Law-Rag' to reopen the workstation or 'Quit Law-Rag' for graceful shutdown.")

    config = uvicorn.Config(app, host=host, port=launch_port, log_level="info", access_log=False)
    server = uvicorn.Server(config)
    try:
        run_server_with_desktop_lifecycle(
            server,
            url,
            enable_tray=bool(os.name == "nt" and not args.no_tray),
        )
    except RuntimeError as exc:
        print(f"[ERROR] Desktop lifecycle could not start safely: {_format_exception_chain(exc)}")
        return 6
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
