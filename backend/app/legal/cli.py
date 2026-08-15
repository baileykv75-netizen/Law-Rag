from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.storage import legal_db_path, legal_last_import_report_path

from .importer import LegalImportError, import_manifest
from .store import get_summary

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SEED_MANIFEST = REPO_ROOT / "legal_data" / "seed" / "manifest.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Law-Rag versioned legal knowledge-base tools")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("rebuild", "import"):
        command = sub.add_parser(name)
        command.add_argument("--manifest", type=Path, default=DEFAULT_SEED_MANIFEST)
        command.add_argument("--db", type=Path, default=None)
        command.add_argument(
            "--allow-non-official-sources",
            action="store_true",
            help="Testing only. Allows fictional fixture hosts outside the official-source allowlist.",
        )

    summary = sub.add_parser("summary")
    summary.add_argument("--db", type=Path, default=None)
    return parser


def main() -> int:
    args = _parser().parse_args()
    db = args.db.resolve() if args.db else legal_db_path()

    if args.command == "summary":
        print(get_summary(db).model_dump_json(indent=2))
        return 0

    try:
        report = import_manifest(
            args.manifest,
            db,
            rebuild=args.command == "rebuild",
            allow_non_official_sources=args.allow_non_official_sources,
            report_path=legal_last_import_report_path(),
        )
    except LegalImportError as exc:
        if exc.report is not None:
            print(exc.report.model_dump_json(indent=2))
        else:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
