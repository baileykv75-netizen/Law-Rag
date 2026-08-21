from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .public_regression import PublicRegressionError, run_public_regression_profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a deterministic Law-Rag Stage 16 public regression profile. "
            "The runner is repository-safe and never invokes paid/network DeepSeek or Kimi calls."
        )
    )
    parser.add_argument(
        "--repo-root",
        default="..",
        help="Repository root. Default assumes execution from backend/.",
    )
    parser.add_argument("--profile", required=True, help="Path to a public regression profile JSON file.")
    parser.add_argument(
        "--work-dir",
        help="Optional local work directory for generated legal/retrieval scratch databases.",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON report path. If omitted, the report is printed to stdout.",
    )
    return parser


def _run(args: argparse.Namespace, work_dir: Path):
    report, fingerprints = run_public_regression_profile(
        Path(args.repo_root).resolve(),
        Path(args.profile).resolve(),
        work_dir.resolve(),
    )
    payload = report.model_dump(mode="json")
    payload["source_fingerprints"] = fingerprints
    return report, payload


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.work_dir:
            report, payload = _run(args, Path(args.work_dir))
        else:
            with tempfile.TemporaryDirectory(prefix="law-rag-public-regression-") as temp_dir:
                report, payload = _run(args, Path(temp_dir))
    except (PublicRegressionError, OSError, ValueError, KeyError) as exc:
        print(f"public regression error: {exc}")
        return 2

    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    return 0 if report.all_gates_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
