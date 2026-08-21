from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .release_evidence import ReleaseEvidenceError, build_stage16_release_evidence_matrix


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assemble the Stage 16 release-quality evidence matrix without invoking paid/network providers. "
            "Missing private expert or real-provider UAT evidence remains explicit PENDING unless "
            "--require-complete-evidence is requested."
        )
    )
    parser.add_argument(
        "--repo-root",
        default="..",
        help="Repository root. Default assumes execution from backend/.",
    )
    parser.add_argument(
        "--public-suite",
        default="benchmarks/public/stage16b_evaluation_suite.json",
        help="Pinned Stage 16 public evaluation suite path, relative to repo root by default.",
    )
    parser.add_argument(
        "--expert-report",
        help="Optional sanitized private expert benchmark report. Must stay external or under benchmark_private/.",
    )
    parser.add_argument(
        "--uat-suite",
        help="Optional REAL_PROVIDER_UAT suite containing Stage 16.4 UAT_CAPTURE entries. Must stay external or under benchmark_private/.",
    )
    parser.add_argument(
        "--work-dir",
        help="Optional local scratch directory for deterministic suite execution.",
    )
    parser.add_argument(
        "--output",
        help="Optional sanitized evidence-matrix JSON path. If omitted, print to stdout.",
    )
    parser.add_argument(
        "--require-complete-evidence",
        action="store_true",
        help="Exit non-zero unless public, private-expert and real-provider-UAT evidence are all complete/present.",
    )
    return parser


def _path_or_none(value: str | None) -> Path | None:
    return None if value is None else Path(value)


def _run(args: argparse.Namespace, work_dir: Path):
    return build_stage16_release_evidence_matrix(
        Path(args.repo_root),
        Path(args.public_suite),
        work_dir,
        expert_report_path=_path_or_none(args.expert_report),
        uat_suite_path=_path_or_none(args.uat_suite),
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.work_dir:
            report = _run(args, Path(args.work_dir))
        else:
            with tempfile.TemporaryDirectory(prefix="law-rag-stage16-release-evidence-") as temp_dir:
                report = _run(args, Path(temp_dir))
    except (ReleaseEvidenceError, OSError, ValueError, KeyError) as exc:
        print(f"release evidence error: {exc}")
        return 2

    rendered = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    if args.require_complete_evidence:
        return 0 if report.stage16_evidence_complete else 1
    return 0 if report.engineering_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
