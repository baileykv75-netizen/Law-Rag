from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

from app.legal.corpus_release import (
    CorpusReleaseError,
    _digest,
    build_corpus_release,
    load_corpus_release,
    plan_corpus_update,
    rebuild_legal_store_from_release,
    write_corpus_release,
)
from app.legal.store import get_summary, resolve_version


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _version(
    version_id: str = "effective-2020-01-01",
    *,
    status: str = "EFFECTIVE",
    effective: str = "2020-01-01",
    publication: str = "2019-12-01",
    end: str | None = None,
    repeal: str | None = None,
    supersedes: str | None = None,
    superseded_by: str | None = None,
    source_hash: str = "1" * 64,
) -> dict:
    return {
        "authority_id": "fictional-law",
        "version_id": version_id,
        "authority_fingerprint": "a" * 64,
        "status": status,
        "publication_date": publication,
        "effective_date": effective,
        "end_date_exclusive": end,
        "repeal_date": repeal,
        "supersedes_version_id": supersedes,
        "superseded_by_version_id": superseded_by,
        "coverage_type": "FULL_TEXT",
        "source_snapshot_sha256": source_hash,
        "expected_article_count": 2,
        "manifest_path": f"authorities/fictional-law/{version_id}/manifest.json",
        "pack_ids": ["fictional-pack"],
    }


def _release(
    version: str,
    versions: list[dict],
    *,
    released_on: str = "2026-08-20",
    parent: str | None = None,
) -> dict:
    payload = {
        "release_schema_version": "1.0.0",
        "corpus_id": "fictional-corpus",
        "corpus_version": version,
        "released_on": released_on,
        "parent_corpus_version": parent,
        "packs": [{
            "pack_id": "fictional-pack",
            "pack_version": "0.1.0",
            "domain_tags": ["fictional"],
            "authority_manifest_paths": sorted({item["manifest_path"] for item in versions}),
        }],
        "versions": sorted(versions, key=lambda item: (item["authority_id"], item["version_id"])),
        "summary": {
            "pack_count": 1,
            "authority_count": len({item["authority_id"] for item in versions}),
            "version_count": len(versions),
            "article_count": sum(item["expected_article_count"] for item in versions),
        },
    }
    payload["release_digest"] = _digest(payload)
    return payload


def test_checked_in_ready_corpus_builds_release_and_rebuilds_database(tmp_path: Path) -> None:
    root = _repo_root()
    first = build_corpus_release(
        root / "legal_data",
        corpus_id="three-domain-core",
        corpus_version="1.0.0",
        released_on=date(2026, 8, 20),
    )
    second = build_corpus_release(
        root / "legal_data",
        corpus_id="three-domain-core",
        corpus_version="1.0.0",
        released_on=date(2026, 8, 20),
    )
    assert first == second
    assert first["summary"] == {
        "pack_count": 3,
        "authority_count": 14,
        "version_count": 15,
        "article_count": 1274,
    }
    future = next(
        item for item in first["versions"]
        if item["authority_id"] == "prc-trademark-law"
        and item["version_id"] == "effective-2027-01-01"
    )
    assert future["status"] == "NOT_YET_EFFECTIVE"

    db = tmp_path / "legal.db"
    result = rebuild_legal_store_from_release(
        first,
        corpus_root=root / "legal_data",
        db_path=db,
        source_registry_path=root / "legal_data" / "source_registry.json",
    )
    assert result["corpus_version"] == "1.0.0"
    summary = get_summary(db)
    assert (summary.authority_count, summary.version_count, summary.article_count) == (14, 15, 1274)
    assert resolve_version(db, "prc-trademark-law", date(2026, 12, 31)).version.version_id == "effective-2019-11-01"
    assert resolve_version(db, "prc-trademark-law", date(2027, 1, 1)).version.version_id == "effective-2027-01-01"


def test_release_file_is_idempotent_and_digest_fails_closed(tmp_path: Path) -> None:
    release = _release("1.0.0", [_version()])
    path = tmp_path / "release.json"
    write_corpus_release(release, path)
    write_corpus_release(release, path)
    assert load_corpus_release(path) == release

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["versions"][0]["source_snapshot_sha256"] = "f" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CorpusReleaseError, match="digest mismatch"):
        load_corpus_release(path)


def test_update_plan_detects_amendment_and_preserves_old_version() -> None:
    old = _version()
    current = _release("1.0.0", [old])
    closed = deepcopy(old)
    closed.update({
        "status": "SUPERSEDED",
        "end_date_exclusive": "2028-01-01",
        "superseded_by_version_id": "effective-2028-01-01",
    })
    amended = _version(
        "effective-2028-01-01",
        effective="2028-01-01",
        publication="2027-10-01",
        supersedes=old["version_id"],
        source_hash="2" * 64,
    )
    candidate = _release("1.1.0", [closed, amended], released_on="2028-01-01", parent="1.0.0")
    plan = plan_corpus_update(current, candidate)
    assert plan["disposition"] == "SAFE_FORWARD"
    assert {"SUPERSESSION_RECORDED", "AMENDMENT_VERSION_ADDED"} <= {
        item["kind"] for item in plan["changes"]
    }


def test_update_plan_blocks_snapshot_mutation_and_historical_removal() -> None:
    current = _release("1.0.0", [_version()])
    mutated = deepcopy(current["versions"][0])
    mutated["source_snapshot_sha256"] = "f" * 64
    candidate = _release("1.1.0", [mutated], parent="1.0.0")
    plan = plan_corpus_update(current, candidate)
    assert plan["disposition"] == "BLOCKED"
    assert "SNAPSHOT_MUTATED" in {item["kind"] for item in plan["changes"]}

    old = _version(
        status="SUPERSEDED",
        end="2025-01-01",
        superseded_by="effective-2025-01-01",
    )
    newer = _version(
        "effective-2025-01-01",
        effective="2025-01-01",
        publication="2024-12-01",
        supersedes=old["version_id"],
        source_hash="2" * 64,
    )
    historical = _release("2.0.0", [old, newer])
    missing_old = deepcopy(newer)
    missing_old["supersedes_version_id"] = None
    candidate_without_history = _release("2.1.0", [missing_old], parent="2.0.0")
    removal = plan_corpus_update(historical, candidate_without_history)
    assert removal["disposition"] == "BLOCKED"
    assert "VERSION_REMOVED" in {item["kind"] for item in removal["changes"]}


def test_update_plan_records_repeal_and_future_activation() -> None:
    current_version = _version()
    current = _release("1.0.0", [current_version])
    repealed = deepcopy(current_version)
    repealed.update({
        "status": "REPEALED",
        "end_date_exclusive": "2027-07-01",
        "repeal_date": "2027-07-01",
    })
    candidate = _release("1.1.0", [repealed], released_on="2027-07-01", parent="1.0.0")
    plan = plan_corpus_update(current, candidate)
    assert plan["disposition"] == "SAFE_FORWARD"
    assert "REPEAL_RECORDED" in {item["kind"] for item in plan["changes"]}

    future = _version(
        "effective-2027-01-01",
        status="NOT_YET_EFFECTIVE",
        effective="2027-01-01",
        publication="2026-06-27",
    )
    before = _release("2.0.0", [future])
    activated = deepcopy(future)
    activated["status"] = "EFFECTIVE"
    after = _release("2.1.0", [activated], released_on="2027-01-01", parent="2.0.0")
    activation = plan_corpus_update(before, after)
    assert activation["disposition"] == "SAFE_FORWARD"
    assert "EFFECTIVE_ACTIVATED" in {item["kind"] for item in activation["changes"]}


def test_update_plan_requires_parent_and_monotonic_corpus_version() -> None:
    current = _release("2.0.0", [_version()])
    candidate = _release("1.9.0", [_version()], parent="1.0.0")
    plan = plan_corpus_update(current, candidate)
    assert plan["disposition"] == "BLOCKED"
    assert {"CORPUS_PARENT_MISMATCH", "CORPUS_VERSION_NOT_ADVANCED"} <= {
        item["kind"] for item in plan["changes"]
    }


def test_failed_release_rebuild_never_replaces_existing_database(tmp_path: Path) -> None:
    root = _repo_root()
    release = build_corpus_release(
        root / "legal_data",
        corpus_id="three-domain-core",
        corpus_version="1.0.0",
        released_on=date(2026, 8, 20),
    )
    broken = deepcopy(release)
    broken["versions"][0]["manifest_path"] = "authorities/not-present/manifest.json"
    broken["packs"][0]["authority_manifest_paths"].append("authorities/not-present/manifest.json")
    broken["packs"][0]["authority_manifest_paths"].sort()
    broken["release_digest"] = _digest(broken)

    db = tmp_path / "legal.db"
    db.write_bytes(b"do-not-replace")
    with pytest.raises(CorpusReleaseError):
        rebuild_legal_store_from_release(
            broken,
            corpus_root=root / "legal_data",
            db_path=db,
            source_registry_path=root / "legal_data" / "source_registry.json",
        )
    assert db.read_bytes() == b"do-not-replace"
