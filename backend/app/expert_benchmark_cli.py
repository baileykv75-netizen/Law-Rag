from __future__ import annotations

import argparse
import json
from pathlib import Path

from .expert_benchmark import ExpertBenchmarkError, run_expert_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate an external/ignored professionally labeled Law-Rag benchmark. "
            "Private labels remain outside tracked repository paths."
        )
    )
    parser.add_argument(
        "--repo-root",
        default="..",
        help="Repository root. Default assumes execution from backend/.",
    )
    parser.add_argument(
        "--protocol",
        required=True,
        help="Path to an external or ignored benchmark_private/ expert protocol JSON file.",
    )
    parser.add_argument(
        "--output",
        help="Optional sanitized aggregate report JSON path. Private expected/observed labels are never included.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = run_expert_benchmark(
            Path(args.repo_root).resolve(),
            Path(args.protocol).resolve(),
        )
    except (ExpertBenchmarkError, OSError, ValueError, KeyError) as exc:
        print(f"expert benchmark error: {exc}")
        return 2

    rendered = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
