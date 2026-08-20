from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import date
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from .corpus_packs import CorpusPackStatus, discover_corpus_packs
from .importer import LegalImportError, import_manifest
from .models import LegalManifest, ManifestRecord, VersionStatus
from .parser import LegalParseError, normalize_snapshot_text, parse_chinese_articles, sha256_text
from .store import get_summary

RELEASE_SCHEMA_VERSION = "1.0.0"
PLANNER_VERSION = "stage15.3-1.0.0"


class CorpusReleaseError(RuntimeError):
    pass


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(payload: dict) -> str:
    data = deepcopy(payload)
    data.pop("release_digest", None)
    return hashlib.sha256(_canonical(data).encode("utf-8")).hexdigest()


def _safe(root: Path, configured: str) -> Path:
    if not configured or "\\" in configured:
        raise CorpusReleaseError(f"Unsafe corpus path: {configured!r}")
    posix = PurePosixPath(configured)
    if posix.is_absolute() or ".." in posix.parts or "." in posix.parts:
        raise CorpusReleaseError(f"Unsafe corpus path: {configured}")
    root = root.resolve()
    path = root.joinpath(*posix.parts).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise CorpusReleaseError(f"Corpus path escapes root: {configured}") from exc
    return path


def _load_manifest(path: Path) -> LegalManifest:
    try:
        return LegalManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise CorpusReleaseError(f"Invalid authority manifest {path}: {exc}") from exc


def _authority_fingerprint(record: ManifestRecord) -> str:
    return hashlib.sha256(
        _canonical(record.authority.model_dump(mode="json")).encode("utf-8")
    ).hexdigest()


def _validate_snapshot(root: Path, manifest_path: Path, record: ManifestRecord) -> None:
    snapshot = (manifest_path.parent / record.snapshot_path).resolve()
    try:
        snapshot.relative_to(root.resolve())
        normalized = normalize_snapshot_text(snapshot.read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeDecodeError) as exc:
        raise CorpusReleaseError(f"Invalid snapshot for {record.authority.authority_id}:{record.version_id}") from exc
    actual = sha256_text(normalized)
    if actual != record.expected_source_sha256:
        raise CorpusReleaseError(
            f"Snapshot hash mismatch for {record.authority.authority_id}:{record.version_id}: "
            f"expected {record.expected_source_sha256}, found {actual}"
        )
    try:
        parsed = parse_chinese_articles(
            normalized,
            authority_id=record.authority.authority_id,
            version_id=record.version_id,
        )
    except LegalParseError as exc:
        raise CorpusReleaseError(f"Snapshot parse failed: {exc}") from exc
    if [item.article_ordinal for item in parsed.articles] != list(
        range(1, record.expected_article_count + 1)
    ):
        raise CorpusReleaseError(
            f"Non-contiguous articles for {record.authority.authority_id}:{record.version_id}"
        )


def _validate_release(payload: dict) -> None:
    if payload.get("release_schema_version") != RELEASE_SCHEMA_VERSION:
        raise CorpusReleaseError("Unsupported Corpus Release schema.")
    required = {
        "corpus_id", "corpus_version", "released_on", "packs", "versions", "summary", "release_digest"
    }
    if not required.issubset(payload):
        raise CorpusReleaseError("Corpus Release is missing required fields.")
    if not str(payload["corpus_version"]).replace(".", "").isdigit():
        raise CorpusReleaseError("corpus_version must be numeric dotted form.")
    released_on = date.fromisoformat(payload["released_on"])
    packs = payload["packs"]
    versions = payload["versions"]
    if [p["pack_id"] for p in packs] != sorted(p["pack_id"] for p in packs):
        raise CorpusReleaseError("Release packs must be sorted.")
    identities = [(v["authority_id"], v["version_id"]) for v in versions]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise CorpusReleaseError("Release versions must be unique and sorted.")
    known_packs = {p["pack_id"] for p in packs}
    fingerprints: dict[str, str] = {}
    by_authority: dict[str, list[dict]] = {}
    for item in versions:
        if item["pack_ids"] != sorted(item["pack_ids"]) or not set(item["pack_ids"]).issubset(known_packs):
            raise CorpusReleaseError("Invalid release pack membership.")
        old = fingerprints.setdefault(item["authority_id"], item["authority_fingerprint"])
        if old != item["authority_fingerprint"]:
            raise CorpusReleaseError(f"Authority metadata drift: {item['authority_id']}")
        effective = date.fromisoformat(item["effective_date"])
        end = date.fromisoformat(item["end_date_exclusive"]) if item["end_date_exclusive"] else None
        repeal = date.fromisoformat(item["repeal_date"]) if item["repeal_date"] else None
        status = item["status"]
        if status == VersionStatus.NOT_YET_EFFECTIVE.value and effective <= released_on:
            raise CorpusReleaseError("NOT_YET_EFFECTIVE version is already effective.")
        if status == VersionStatus.EFFECTIVE.value and (effective > released_on or (end and end <= released_on)):
            raise CorpusReleaseError("EFFECTIVE version is outside its release-date interval.")
        if status == VersionStatus.REPEALED.value and (repeal is None or end != repeal):
            raise CorpusReleaseError("REPEALED version requires end_date_exclusive == repeal_date.")
        by_authority.setdefault(item["authority_id"], []).append(item)

    for authority_id, items in by_authority.items():
        ordered = sorted(items, key=lambda x: (x["effective_date"], x["version_id"]))
        by_id = {x["version_id"]: x for x in ordered}
        for previous, current in zip(ordered, ordered[1:]):
            if previous["end_date_exclusive"] is None:
                raise CorpusReleaseError(f"{authority_id} historical version has no end date.")
            if previous["end_date_exclusive"] > current["effective_date"]:
                raise CorpusReleaseError(f"{authority_id} has overlapping version intervals.")
        for item in ordered:
            nxt = item["superseded_by_version_id"]
            if nxt:
                following = by_id.get(nxt)
                if (
                    following is None
                    or item["end_date_exclusive"] != following["effective_date"]
                    or following["supersedes_version_id"] != item["version_id"]
                ):
                    raise CorpusReleaseError(f"{authority_id} has invalid supersession links.")
            prev = item["supersedes_version_id"]
            if prev:
                previous = by_id.get(prev)
                if previous is None or previous["superseded_by_version_id"] != item["version_id"]:
                    raise CorpusReleaseError(f"{authority_id} has invalid supersedes link.")

    summary = payload["summary"]
    expected_summary = {
        "pack_count": len(packs),
        "authority_count": len({v["authority_id"] for v in versions}),
        "version_count": len(versions),
        "article_count": sum(v["expected_article_count"] for v in versions),
    }
    if summary != expected_summary:
        raise CorpusReleaseError(f"Release summary mismatch: expected {expected_summary}, found {summary}")
    if payload["release_digest"] != _digest(payload):
        raise CorpusReleaseError("Corpus Release digest mismatch.")


def build_corpus_release(
    corpus_root: Path,
    *,
    corpus_id: str,
    corpus_version: str,
    released_on: date,
    parent_corpus_version: str | None = None,
) -> dict:
    root = corpus_root.resolve()
    discovered = sorted(discover_corpus_packs(root), key=lambda item: item.manifest.pack_id)
    if not discovered or any(item.manifest.status != CorpusPackStatus.READY for item in discovered):
        raise CorpusReleaseError("Corpus Release requires all discovered packs to be READY.")

    packs = []
    identities: dict[tuple[str, str], tuple[ManifestRecord, str]] = {}
    memberships: dict[tuple[str, str], set[str]] = {}
    for loaded in discovered:
        pack = loaded.manifest
        paths = sorted(pack.authority_manifest_paths)
        packs.append({
            "pack_id": pack.pack_id,
            "pack_version": pack.pack_version,
            "domain_tags": sorted(pack.domain_tags),
            "authority_manifest_paths": paths,
        })
        for configured in paths:
            manifest_path = _safe(root, configured)
            manifest = _load_manifest(manifest_path)
            for record in manifest.records:
                identity = (record.authority.authority_id, record.version_id)
                previous = identities.get(identity)
                if previous and previous[1] != configured:
                    raise CorpusReleaseError(
                        f"Shared identity {identity} uses two manifest paths: {previous[1]}, {configured}"
                    )
                if not previous:
                    _validate_snapshot(root, manifest_path, record)
                    identities[identity] = (record, configured)
                memberships.setdefault(identity, set()).add(pack.pack_id)

    versions = []
    for identity, (record, configured) in sorted(identities.items()):
        versions.append({
            "authority_id": identity[0],
            "version_id": identity[1],
            "authority_fingerprint": _authority_fingerprint(record),
            "status": record.status.value,
            "publication_date": record.publication_date.isoformat() if record.publication_date else None,
            "effective_date": record.effective_date.isoformat(),
            "end_date_exclusive": record.end_date_exclusive.isoformat() if record.end_date_exclusive else None,
            "repeal_date": record.repeal_date.isoformat() if record.repeal_date else None,
            "supersedes_version_id": record.supersedes_version_id,
            "superseded_by_version_id": record.superseded_by_version_id,
            "coverage_type": record.coverage_type.value,
            "source_snapshot_sha256": record.expected_source_sha256,
            "expected_article_count": record.expected_article_count,
            "manifest_path": configured,
            "pack_ids": sorted(memberships[identity]),
        })
    payload = {
        "release_schema_version": RELEASE_SCHEMA_VERSION,
        "corpus_id": corpus_id,
        "corpus_version": corpus_version,
        "released_on": released_on.isoformat(),
        "parent_corpus_version": parent_corpus_version,
        "packs": packs,
        "versions": versions,
        "summary": {
            "pack_count": len(packs),
            "authority_count": len({v["authority_id"] for v in versions}),
            "version_count": len(versions),
            "article_count": sum(v["expected_article_count"] for v in versions),
        },
    }
    payload["release_digest"] = _digest(payload)
    _validate_release(payload)
    return payload


def write_corpus_release(release: dict, path: Path) -> None:
    _validate_release(release)
    text = json.dumps(release, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise CorpusReleaseError(f"Refusing to overwrite different Corpus Release: {path}")
        return
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def load_corpus_release(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusReleaseError(f"Unable to load Corpus Release {path}: {exc}") from exc
    _validate_release(payload)
    return payload


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _add(changes: list[dict], kind: str, message: str, *, blocking: bool = False, **ids) -> None:
    changes.append({"kind": kind, **ids, "message": message, "blocking": blocking})


def plan_corpus_update(current: dict, candidate: dict) -> dict:
    _validate_release(current)
    _validate_release(candidate)
    if current["corpus_id"] != candidate["corpus_id"]:
        raise CorpusReleaseError("Cannot compare different corpus_id values.")
    if current["release_digest"] == candidate["release_digest"]:
        return {
            "planner_version": PLANNER_VERSION,
            "corpus_id": current["corpus_id"],
            "from_corpus_version": current["corpus_version"],
            "to_corpus_version": candidate["corpus_version"],
            "disposition": "NO_CHANGE",
            "changes": [],
            "blocking_reasons": [],
        }

    changes: list[dict] = []
    if candidate.get("parent_corpus_version") != current["corpus_version"]:
        _add(changes, "CORPUS_PARENT_MISMATCH", "Candidate parent_corpus_version is not current.", blocking=True)
    if _version_tuple(candidate["corpus_version"]) <= _version_tuple(current["corpus_version"]):
        _add(changes, "CORPUS_VERSION_NOT_ADVANCED", "Candidate corpus_version must advance.", blocking=True)

    old_packs = {p["pack_id"] for p in current["packs"]}
    new_packs = {p["pack_id"] for p in candidate["packs"]}
    for pack_id in sorted(old_packs - new_packs):
        _add(changes, "PACK_REMOVED", "Previously released pack was removed.", blocking=True, pack_id=pack_id)
    for pack_id in sorted(new_packs - old_packs):
        _add(changes, "PACK_ADDED", "New READY pack added.", pack_id=pack_id)

    old = {(v["authority_id"], v["version_id"]): v for v in current["versions"]}
    new = {(v["authority_id"], v["version_id"]): v for v in candidate["versions"]}
    old_authorities = {key[0] for key in old}
    for key in sorted(old.keys() - new.keys()):
        _add(changes, "VERSION_REMOVED", "Historical Authority/Version may not disappear.",
             blocking=True, authority_id=key[0], version_id=key[1])

    immutable = ("publication_date", "effective_date", "coverage_type", "expected_article_count", "manifest_path")
    lifecycle = ("end_date_exclusive", "repeal_date", "supersedes_version_id", "superseded_by_version_id")
    allowed = {
        "NOT_YET_EFFECTIVE": {"EFFECTIVE"},
        "EFFECTIVE": {"SUPERSEDED", "AMENDED", "REPEALED"},
    }
    for key in sorted(old.keys() & new.keys()):
        before, after = old[key], new[key]
        ids = {"authority_id": key[0], "version_id": key[1]}
        if before["source_snapshot_sha256"] != after["source_snapshot_sha256"]:
            _add(changes, "SNAPSHOT_MUTATED",
                 "Existing version source hash changed; legal text changes require a new version_id.",
                 blocking=True, **ids)
        if before["authority_fingerprint"] != after["authority_fingerprint"]:
            _add(changes, "AUTHORITY_METADATA_MUTATED",
                 "Canonical Authority metadata changed under an existing authority_id.",
                 blocking=True, **ids)
        mutated = [field for field in immutable if before[field] != after[field]]
        if mutated:
            _add(changes, "VERSION_IDENTITY_MUTATED",
                 "Immutable version fields changed: " + ", ".join(mutated), blocking=True, **ids)

        rewritten = [f for f in lifecycle if before[f] is not None and before[f] != after[f]]
        status_ok = before["status"] == after["status"] or after["status"] in allowed.get(before["status"], set())
        if rewritten or not status_ok:
            _add(changes, "VERSION_IDENTITY_MUTATED",
                 "Lifecycle provenance was rewritten or status regressed.", blocking=True, **ids)
        elif before["status"] != after["status"] or any(before[f] != after[f] for f in lifecycle):
            if before["status"] == "NOT_YET_EFFECTIVE" and after["status"] == "EFFECTIVE":
                kind = "EFFECTIVE_ACTIVATED"
            elif after["status"] == "REPEALED":
                kind = "REPEAL_RECORDED"
            elif after["status"] in {"SUPERSEDED", "AMENDED"}:
                kind = "SUPERSESSION_RECORDED"
            else:
                kind = "VERSION_LIFECYCLE_UPDATED"
            _add(changes, kind, "Version lifecycle metadata advanced.", **ids)
        if before["pack_ids"] != after["pack_ids"]:
            _add(changes, "PACK_MEMBERSHIP_UPDATED", "Version pack membership changed.", **ids)

    for key in sorted(new.keys() - old.keys()):
        kind = "AUTHORITY_ADDED" if key[0] not in old_authorities else "AMENDMENT_VERSION_ADDED"
        _add(changes, kind, "New Authority/Version introduced while preserving release history.",
             authority_id=key[0], version_id=key[1])

    blocking = [item["message"] for item in changes if item["blocking"]]
    return {
        "planner_version": PLANNER_VERSION,
        "corpus_id": current["corpus_id"],
        "from_corpus_version": current["corpus_version"],
        "to_corpus_version": candidate["corpus_version"],
        "disposition": "BLOCKED" if blocking else "SAFE_FORWARD",
        "changes": changes,
        "blocking_reasons": blocking,
    }


def rebuild_legal_store_from_release(
    release: dict,
    *,
    corpus_root: Path,
    db_path: Path,
    source_registry_path: Path,
) -> dict:
    _validate_release(release)
    root = corpus_root.resolve()
    db_path = db_path.resolve()
    staged = db_path.with_name(f".{db_path.name}.corpus-release.tmp")
    staged.unlink(missing_ok=True)
    paths = sorted({v["manifest_path"] for v in release["versions"]})
    try:
        for index, configured in enumerate(paths):
            import_manifest(
                _safe(root, configured),
                staged,
                rebuild=index == 0,
                source_registry_path=source_registry_path,
            )
        summary = get_summary(staged)
        actual = (summary.authority_count, summary.version_count, summary.article_count)
        expected = release["summary"]
        wanted = (expected["authority_count"], expected["version_count"], expected["article_count"])
        if actual != wanted:
            raise CorpusReleaseError(f"Release rebuild summary mismatch: expected {wanted}, found {actual}.")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged, db_path)
    except Exception as exc:
        staged.unlink(missing_ok=True)
        if isinstance(exc, CorpusReleaseError):
            raise
        if isinstance(exc, LegalImportError):
            raise CorpusReleaseError(f"Release database rebuild failed: {exc}") from exc
        raise
    return {
        "corpus_id": release["corpus_id"],
        "corpus_version": release["corpus_version"],
        **release["summary"],
    }
