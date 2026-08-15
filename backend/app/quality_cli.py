from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .quality import QualityError, load_quality_gate_profile, run_public_quality_profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Law-Rag public deterministic quality metrics and CI gates."
    )
    parser.add_argument(
        "--repo-root",
        default="..",
        help="Repository root containing benchmarks/ and legal_data/. Default assumes execution from backend/.",
    )
    parser.add_argument(
        "--profile",
        default="../benchmarks/public/stage11b_quality_gates.json",
        help="Versioned public quality gate profile JSON.",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON report path. If omitted, the report is printed to stdout.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    try:
        profile = load_quality_gate_profile(Path(args.profile).resolve())
        with tempfile.TemporaryDirectory(prefix="law-rag-quality-") as temp_dir:
            report = run_public_quality_profile(repo_root, Path(temp_dir), profile)
    except (QualityError, OSError, ValueError, KeyError) as exc:
        print(f"quality error: {exc}")
        return 2

    rendered = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    return 0 if report.all_gates_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
