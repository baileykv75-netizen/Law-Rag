from __future__ import annotations

from datetime import date
from pathlib import Path

from app.legal.importer import import_manifest
from app.legal.store import get_evidence, get_summary, resolve_version


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _manifest_paths(root: Path) -> list[Path]:
    return [
        root / "legal_data" / "authorities" / "prc-patent-law" / "effective-2021-06-01" / "manifest.json",
        root / "legal_data" / "authorities" / "prc-copyright-law" / "effective-2021-06-01" / "manifest.json",
        root / "legal_data" / "authorities" / "prc-trademark-law" / "effective-2019-11-01" / "manifest.json",
        root / "legal_data" / "authorities" / "prc-trademark-law" / "effective-2027-01-01" / "manifest.json",
        root
        / "legal_data"
        / "authorities"
        / "prc-anti-unfair-competition-law"
        / "effective-2025-10-15"
        / "manifest.json",
    ]


def test_ip_frozen_corpus_imports_deterministically_without_identity_duplication(tmp_path: Path) -> None:
    root = _repo_root()
    registry = root / "legal_data" / "source_registry.json"
    manifests = _manifest_paths(root)
    db = tmp_path / "legal.db"

    first_reports = []
    for index, manifest in enumerate(manifests):
        first_reports.append(
            import_manifest(
                manifest,
                db,
                rebuild=index == 0,
                source_registry_path=registry,
            )
        )

    assert all(report.rejected_records == 0 for report in first_reports)
    summary = get_summary(db)
    assert summary.authority_count == 4
    assert summary.version_count == 5
    assert summary.article_count == 350
    assert summary.effective_version_count == 4
    assert summary.excerpt_version_count == 0

    current = resolve_version(db, "prc-trademark-law", date(2026, 8, 20))
    assert current.state.value == "RESOLVED"
    assert current.version is not None
    assert current.version.version_id == "effective-2019-11-01"

    transition = resolve_version(db, "prc-trademark-law", date(2027, 1, 1))
    assert transition.state.value == "RESOLVED"
    assert transition.version is not None
    assert transition.version.version_id == "effective-2027-01-01"
    assert transition.version.status.value == "NOT_YET_EFFECTIVE"

    patent = get_evidence(db, "legal:prc-patent-law:effective-2021-06-01:article-82")
    assert patent.article.article_token == "第八十二条"
    anti_unfair = get_evidence(
        db,
        "legal:prc-anti-unfair-competition-law:effective-2025-10-15:article-41",
    )
    assert anti_unfair.article.article_token == "第四十一条"

    second_reports = [
        import_manifest(
            manifest,
            db,
            source_registry_path=registry,
        )
        for manifest in manifests
    ]
    assert all(report.rejected_records == 0 for report in second_reports)
    assert all(report.no_change_records == 1 for report in second_reports)

    repeated = get_summary(db)
    assert repeated.authority_count == 4
    assert repeated.version_count == 5
    assert repeated.article_count == 350


def test_shared_anti_unfair_manifest_is_one_canonical_file_for_both_pack_targets() -> None:
    root = _repo_root()
    shared_manifest = (
        root
        / "legal_data"
        / "authorities"
        / "prc-anti-unfair-competition-law"
        / "effective-2025-10-15"
        / "manifest.json"
    )
    assert shared_manifest.is_file()

    import json

    ip = json.loads(
        (root / "legal_data" / "catalog" / "cn-intellectual-property-core.snapshot-targets.json").read_text(
            encoding="utf-8"
        )
    )
    enterprise = json.loads(
        (root / "legal_data" / "catalog" / "cn-enterprise-compliance-core.snapshot-targets.json").read_text(
            encoding="utf-8"
        )
    )

    def shared_target(payload: dict) -> dict:
        return next(
            item
            for item in payload["targets"]
            if item["authority_id"] == "prc-anti-unfair-competition-law"
        )

    ip_target = shared_target(ip)
    enterprise_target = shared_target(enterprise)
    assert ip_target["version_id"] == enterprise_target["version_id"] == "effective-2025-10-15"
    assert ip_target["snapshot_source_url"] == enterprise_target["snapshot_source_url"]
    assert ip_target["expected_article_count"] == enterprise_target["expected_article_count"] == 41
