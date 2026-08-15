from __future__ import annotations

import argparse
import json

from .runtime_health import inspect_runtime_health


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect Law-Rag local runtime health without mutating data or making provider requests."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full machine-readable RuntimeHealthReport as JSON.",
    )
    return parser


def _text_report() -> str:
    report = inspect_runtime_health()
    lines = [
        "Law-Rag Runtime Health",
        f"base_app_ready: {'YES' if report.base_app_ready else 'NO'}",
        f"action_required: {'YES' if report.action_required else 'NO'}",
        "",
    ]
    for check in report.checks:
        lines.append(f"[{check.state.value}] {check.label}")
        lines.append(f"  {check.detail}")
        if check.action:
            lines.append(f"  action: {check.action}")
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    report = inspect_runtime_health()
    if args.json:
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        print(_text_report())
    return 0 if report.base_app_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
