from __future__ import annotations

import json
import os
import sys
from pathlib import Path


_INSTALL_MARKER = ".law-rag-installed"
_INSTALLED_DATA_DIRNAME = "Law-Rag"


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None))


def configure_installed_runtime_default() -> dict[str, object]:
    """Select the writable runtime root before importing the release launcher.

    Portable builds intentionally keep the historical adjacent ``runtime``
    default. An installer places ``.law-rag-installed`` beside the executable;
    that explicit marker moves user data to LocalAppData so application
    replacement/uninstall never owns the user's contracts, reports, history,
    or local legal corpus.

    ``LAW_RAG_RUNTIME_DIR`` remains an explicit operator/test override and is
    never replaced by this helper.
    """

    executable_dir = Path(sys.executable).resolve().parent if _frozen() else Path(__file__).resolve().parents[1]
    marker = executable_dir / _INSTALL_MARKER
    installed = bool(_frozen() and marker.is_file())
    explicit_runtime = os.getenv("LAW_RAG_RUNTIME_DIR", "").strip()

    if explicit_runtime:
        runtime_dir = Path(explicit_runtime).expanduser().resolve()
        source = "EXPLICIT_ENVIRONMENT"
    elif installed:
        local_appdata = os.getenv("LOCALAPPDATA", "").strip()
        if not local_appdata:
            raise RuntimeError(
                "Installed Law-Rag requires LOCALAPPDATA so user runtime data can remain separate from application binaries."
            )
        runtime_dir = (Path(local_appdata).expanduser().resolve() / _INSTALLED_DATA_DIRNAME / "runtime").resolve()
        os.environ["LAW_RAG_RUNTIME_DIR"] = str(runtime_dir)
        source = "INSTALLED_MARKER"
    else:
        runtime_dir = (executable_dir / "runtime").resolve()
        source = "PORTABLE_DEFAULT" if _frozen() else "DEVELOPMENT_DEFAULT"

    try:
        user_data_separated = not runtime_dir.is_relative_to(executable_dir)
    except ValueError:
        user_data_separated = True

    return {
        "frozen": _frozen(),
        "installed": installed,
        "marker_path": str(marker),
        "executable_dir": str(executable_dir),
        "runtime_dir": str(runtime_dir),
        "runtime_source": source,
        "user_data_separated_from_app": user_data_separated,
        "network_used": False,
    }


if __name__ == "__main__":
    try:
        installation_layout = configure_installed_runtime_default()
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(9)

    if "--diagnose-installation-layout" in sys.argv[1:]:
        if len(sys.argv) != 2:
            print("[ERROR] --diagnose-installation-layout does not accept additional arguments.")
            raise SystemExit(9)
        print(json.dumps(installation_layout, ensure_ascii=True, indent=2))
        raise SystemExit(0)

    if "--diagnose-report-export-runtime" in sys.argv[1:]:
        if len(sys.argv) != 2:
            print("[ERROR] --diagnose-report-export-runtime does not accept additional arguments.")
            raise SystemExit(8)
        from app.release_stage18_diagnostics import run_packaged_report_renderer_diagnostic

        raise SystemExit(run_packaged_report_renderer_diagnostic())

    # This branch intentionally builds the limited tester distribution. The
    # release entry point sets the requirement itself instead of trusting an
    # external environment value, so a tester cannot disable the gate by
    # launching the packaged EXE with LAW_RAG_TESTER_LICENSE_REQUIRED=0.
    os.environ["LAW_RAG_TESTER_LICENSE_REQUIRED"] = "1"

    import app.main as main_module
    from app.tester_license import TesterLicenseMiddleware

    main_module.app = TesterLicenseMiddleware(main_module.app)

    from app.release_launcher import main

    raise SystemExit(main())
