from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .evaluation_suite import EvaluationSuiteError, run_evaluation_suite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a versioned Law-Rag Stage 16 evaluation suite. The evaluator consumes existing "
            "observations and never invokes paid/network model providers."
        )
    )
    parser.add_argument(
        "--repo-root",
        default="..",
        help="Repository root. Default assumes execution from backend/.",
    )
    parser.add_argument("--suite", required=True, help="Path to an EvaluationSuiteManifest JSON file.")
    parser.add_argument(
        "--work-dir",
        help="Optional local work directory for deterministic quality-run scratch data.",
    )
    parser.add_argument(
        "--output",
        help="Optional sanitized suite-report JSON path. If omitted, the report is printed to stdout.",
    )
    return parser


def _run(args: argparse.Namespace, work_dir: Path):
    return run_evaluation_suite(
        Path(args.repo_root).resolve(),
        Path(args.suite).resolve(),
        work_dir.resolve(),
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.work_dir:
            report = _run(args, Path(args.work_dir))
        else:
            with tempfile.TemporaryDirectory(prefix="law-rag-evaluation-suite-") as temp_dir:
                report = _run(args, Path(temp_dir))
    except (EvaluationSuiteError, OSError, ValueError, KeyError) as exc:
        print(f"evaluation suite error: {exc}")
        return 2

    rendered = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    return 0 if report.all_entries_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
