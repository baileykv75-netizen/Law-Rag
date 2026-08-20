from __future__ import annotations

from datetime import date
from pathlib import Path

from app.legal.corpus_release import build_corpus_release, load_corpus_release


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_checked_in_three_domain_release_matches_live_ready_corpus_exactly() -> None:
    root = _repo_root()
    checked_in = load_corpus_release(
        root / "legal_data" / "releases" / "three-domain-core" / "1.0.0" / "release.json"
    )
    rebuilt = build_corpus_release(
        root / "legal_data",
        corpus_id="three-domain-core",
        corpus_version="1.0.0",
        released_on=date(2026, 8, 20),
        pack_ids=[
            "cn-enterprise-compliance-core",
            "cn-intellectual-property-core",
            "cn-labor-dispute-core",
        ],
    )

    assert rebuilt == checked_in
    assert checked_in["release_digest"] == (
        "4009c06967cd2281089e85bdfda64388dd4ac8fc3b86125d971bfa1c0f642b4f"
    )
    assert checked_in["summary"] == {
        "pack_count": 3,
        "authority_count": 14,
        "version_count": 15,
        "article_count": 1274,
    }
