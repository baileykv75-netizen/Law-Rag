from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .corpus_release import (
    CorpusReleaseError,
    build_corpus_release,
    load_corpus_release,
    plan_corpus_update,
    rebuild_legal_store_from_release,
    write_corpus_release,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CORPUS_ROOT = REPO_ROOT / "legal_data"
DEFAULT_SOURCE_REGISTRY = DEFAULT_CORPUS_ROOT / "source_registry.json"


def _as_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build, compare and apply deterministic Stage 15.3 Corpus Releases."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    build.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    build.add_argument("--corpus-id", required=True)
    build.add_argument("--corpus-version", required=True)
    build.add_argument("--released-on", required=True, type=_as_date)
    build.add_argument("--parent-corpus-version")
    build.add_argument(
        "--pack-id",
        action="append",
        dest="pack_ids",
        help="READY Corpus Pack to include. Repeatable. Defaults to all READY packs.",
    )
    build.add_argument("--output", required=True, type=Path)

    plan = sub.add_parser("plan")
    plan.add_argument("--current", required=True, type=Path)
    plan.add_argument("--candidate-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    plan.add_argument("--candidate-version", required=True)
    plan.add_argument("--released-on", required=True, type=_as_date)
    plan.add_argument(
        "--pack-id",
        action="append",
        dest="pack_ids",
        help=(
            "READY Corpus Pack to include in the candidate. Repeatable. "
            "Defaults to the current release's pack set."
        ),
    )
    plan.add_argument("--output", type=Path)

    rebuild = sub.add_parser("rebuild")
    rebuild.add_argument("--release", required=True, type=Path)
    rebuild.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    rebuild.add_argument("--database", required=True, type=Path)
    rebuild.add_argument("--source-registry", type=Path, default=DEFAULT_SOURCE_REGISTRY)
    return parser


def _emit(payload: object, path: Path | None = None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path is None:
        print(text, end="")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "build":
            release = build_corpus_release(
                args.corpus_root,
                corpus_id=args.corpus_id,
                corpus_version=args.corpus_version,
                released_on=args.released_on,
                parent_corpus_version=args.parent_corpus_version,
                pack_ids=args.pack_ids,
            )
            write_corpus_release(release, args.output)
            _emit(release)
            return 0

        if args.command == "plan":
            current = load_corpus_release(args.current)
            selected_packs = args.pack_ids or [
                item["pack_id"] for item in current["packs"]
            ]
            candidate = build_corpus_release(
                args.candidate_root,
                corpus_id=current["corpus_id"],
                corpus_version=args.candidate_version,
                released_on=args.released_on,
                parent_corpus_version=current["corpus_version"],
                pack_ids=selected_packs,
            )
            plan = plan_corpus_update(current, candidate)
            _emit(plan, args.output)
            return 2 if plan["disposition"] == "BLOCKED" else 0

        release = load_corpus_release(args.release)
        result = rebuild_legal_store_from_release(
            release,
            corpus_root=args.corpus_root,
            db_path=args.database,
            source_registry_path=args.source_registry,
        )
        _emit(result)
        return 0
    except CorpusReleaseError as exc:
        _emit({"error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
