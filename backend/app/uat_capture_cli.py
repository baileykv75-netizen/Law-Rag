from __future__ import annotations

import argparse
from pathlib import Path
from uuid import UUID

from .uat_capture import UATCaptureError, capture_issue_v1_uat
from .uat_capture_models import UATCaptureMode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture provenance from an already-executed Law-Rag ISSUE_V1 job. "
            "This command never calls DeepSeek, Kimi, OCR, or another provider."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=Path(".."))
    parser.add_argument("--job-id", type=UUID, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=[item.value for item in UATCaptureMode],
        default=UATCaptureMode.TEST_DOUBLE.value,
    )
    parser.add_argument(
        "--confirm-real-provider-uat",
        action="store_true",
        help=(
            "Required with --mode REAL_PROVIDER. This labels already-persisted provider artifacts as explicit real-provider UAT evidence; "
            "it does not itself send a network request."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        _, report = capture_issue_v1_uat(
            args.repo_root,
            args.job_id,
            args.output,
            capture_mode=UATCaptureMode(args.mode),
            confirm_real_provider_uat=args.confirm_real_provider_uat,
        )
    except (UATCaptureError, FileNotFoundError) as exc:
        print(f"UAT capture failed: {exc}")
        return 2
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
