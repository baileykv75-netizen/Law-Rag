from __future__ import annotations

import argparse
import json
from pathlib import Path

from .benchmark import BenchmarkError, evaluate_benchmark_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate a Law-Rag benchmark dataset against an observation set."
    )
    parser.add_argument("--dataset", required=True, help="Path to a versioned benchmark dataset JSON file.")
    parser.add_argument(
        "--observations",
        required=True,
        help="Path to a versioned benchmark observation JSON file. Private external files are supported.",
    )
    parser.add_argument(
        "--output",
        help="Optional output JSON path. If omitted, the report is printed to stdout.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = evaluate_benchmark_files(Path(args.dataset), Path(args.observations))
    except BenchmarkError as exc:
        print(f"benchmark error: {exc}")
        return 2

    payload = report.model_dump(mode="json")
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    return 0 if report.all_cases_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
