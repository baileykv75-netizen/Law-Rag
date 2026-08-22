from __future__ import annotations

import sys

from app.release_launcher import main


if __name__ == "__main__":
    if "--diagnose-report-export-runtime" in sys.argv[1:]:
        if len(sys.argv) != 2:
            print("[ERROR] --diagnose-report-export-runtime does not accept additional arguments.")
            raise SystemExit(8)
        from app.release_stage18_diagnostics import run_packaged_report_renderer_diagnostic

        raise SystemExit(run_packaged_report_renderer_diagnostic())
    raise SystemExit(main())
