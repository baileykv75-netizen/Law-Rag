from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from .models import (
    AuthoritySummary,
    AuthorityType,
    CoverageType,
    LegalArticle,
    LegalAuthority,
    LegalEvidenceRecord,
    LegalStoreSummary,
    LegalVersion,
    OfficialSourceRef,
    SourceRole,
    VersionResolution,
    VersionResolutionState,
    VersionStatus,
    LEGAL_SCHEMA_VERSION,
)


class LegalStoreError(RuntimeError):
    pass


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS legal_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS authorities (
    authority_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authority_type TEXT NOT NULL,
    issuing_body TEXT NOT NULL,
    document_number TEXT,
    jurisdiction TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS authority_versions (
    authority_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    status TEXT NOT NULL,
    publication_date TEXT,
    effective_date TEXT NOT NULL,
    end_date_exclusive TEXT,
    repeal_date TEXT,
    supersedes_version_id TEXT,
    superseded_by_version_id TEXT,
    coverage_type TEXT NOT NULL,
    coverage_note TEXT,
    source_refs_json TEXT NOT NULL,
    source_snapshot_sha256 TEXT NOT NULL,
    importer_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    verified_on TEXT,
    verification_note TEXT,
    PRIMARY KEY (authority_id, version_id),
    FOREIGN KEY (authority_id) REFERENCES authorities(authority_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS legal_articles (
    legal_evidence_id TEXT PRIMARY KEY,
    authority_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    article_id TEXT NOT NULL,
    article_token TEXT NOT NULL,
    article_ordinal INTEGER,
    article_text TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    heading_context_json TEXT NOT NULL,
    UNIQUE (authority_id, version_id, article_id),
    UNIQUE (authority_id, version_id, article_token),
    FOREIGN KEY (authority_id, version_id)
        REFERENCES authority_versions(authority_id, version_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_legal_articles_authority_version
    ON legal_articles(authority_id, version_id);
CREATE INDEX IF NOT EXISTS idx_legal_versions_effective
    ON authority_versions(authority_id, effective_date, end_date_exclusive);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    existing = connection.execute(
        "SELECT value FROM legal_meta WHERE key = 'schema_version'"
    ).fetchone()
    if existing is not None and existing["value"] != LEGAL_SCHEMA_VERSION:
        raise LegalStoreError(
            f"Legal database schema {existing['value']} is incompatible with {LEGAL_SCHEMA_VERSION}."
        )
    connection.execute(
        "INSERT OR REPLACE INTO legal_meta(key, value) VALUES ('schema_version', ?)",
        (LEGAL_SCHEMA_VERSION,),
    )


def _authority_from_row(row: sqlite3.Row) -> LegalAuthority:
    return LegalAuthority(
        authority_id=row["authority_id"],
        title=row["title"],
        authority_type=AuthorityType(row["authority_type"]),
        issuing_body=row["issuing_body"],
        document_number=row["document_number"],
        jurisdiction=row["jurisdiction"],
    )


def _version_from_row(row: sqlite3.Row) -> LegalVersion:
    refs = [OfficialSourceRef.model_validate(item) for item in json.loads(row["source_refs_json"])]
    return LegalVersion(
        authority_id=row["authority_id"],
        version_id=row["version_id"],
        status=VersionStatus(row["status"]),
        publication_date=date.fromisoformat(row["publication_date"]) if row["publication_date"] else None,
        effective_date=date.fromisoformat(row["effective_date"]),
        end_date_exclusive=date.fromisoformat(row["end_date_exclusive"]) if row["end_date_exclusive"] else None,
        repeal_date=date.fromisoformat(row["repeal_date"]) if row["repeal_date"] else None,
        supersedes_version_id=row["supersedes_version_id"],
        superseded_by_version_id=row["superseded_by_version_id"],
        coverage_type=CoverageType(row["coverage_type"]),
        coverage_note=row["coverage_note"],
        source_refs=refs,
        source_snapshot_sha256=row["source_snapshot_sha256"],
        importer_version=row["importer_version"],
        schema_version=row["schema_version"],
        verified_on=date.fromisoformat(row["verified_on"]) if row["verified_on"] else None,
        verification_note=row["verification_note"],
    )


def _article_from_row(row: sqlite3.Row) -> LegalArticle:
    return LegalArticle(
        authority_id=row["authority_id"],
        version_id=row["version_id"],
        article_id=row["article_id"],
        article_token=row["article_token"],
        article_ordinal=row["article_ordinal"],
        text=row["article_text"],
        text_sha256=row["text_sha256"],
        legal_evidence_id=row["legal_evidence_id"],
        heading_context=json.loads(row["heading_context_json"]),
    )


def get_summary(db_path: Path) -> LegalStoreSummary:
    if not db_path.exists():
        return LegalStoreSummary(ready=False)
    with connect(db_path) as connection:
        initialize_schema(connection)
        authority_count = connection.execute("SELECT COUNT(*) AS n FROM authorities").fetchone()["n"]
        version_count = connection.execute("SELECT COUNT(*) AS n FROM authority_versions").fetchone()["n"]
        article_count = connection.execute("SELECT COUNT(*) AS n FROM legal_articles").fetchone()["n"]
        effective_count = connection.execute(
            "SELECT COUNT(*) AS n FROM authority_versions WHERE status = ?",
            (VersionStatus.EFFECTIVE.value,),
        ).fetchone()["n"]
        excerpt_count = connection.execute(
            "SELECT COUNT(*) AS n FROM authority_versions WHERE coverage_type = ?",
            (CoverageType.CURATED_EXCERPT.value,),
        ).fetchone()["n"]
        return LegalStoreSummary(
            ready=True,
            schema_version=LEGAL_SCHEMA_VERSION,
            authority_count=authority_count,
            version_count=version_count,
            article_count=article_count,
            effective_version_count=effective_count,
            excerpt_version_count=excerpt_count,
        )


def list_authorities(db_path: Path) -> list[AuthoritySummary]:
    if not db_path.exists():
        return []
    with connect(db_path) as connection:
        initialize_schema(connection)
        authorities = connection.execute("SELECT * FROM authorities ORDER BY title, authority_id").fetchall()
        results: list[AuthoritySummary] = []
        for authority_row in authorities:
            versions = connection.execute(
                "SELECT * FROM authority_versions WHERE authority_id = ? ORDER BY effective_date, version_id",
                (authority_row["authority_id"],),
            ).fetchall()
            count = connection.execute(
                "SELECT COUNT(*) AS n FROM legal_articles WHERE authority_id = ?",
                (authority_row["authority_id"],),
            ).fetchone()["n"]
            results.append(
                AuthoritySummary(
                    authority=_authority_from_row(authority_row),
                    versions=[_version_from_row(row) for row in versions],
                    article_count=count,
                )
            )
        return results


def get_authority(db_path: Path, authority_id: str) -> AuthoritySummary:
    if not db_path.exists():
        raise FileNotFoundError("Legal database has not been built yet.")
    with connect(db_path) as connection:
        initialize_schema(connection)
        authority_row = connection.execute(
            "SELECT * FROM authorities WHERE authority_id = ?", (authority_id,)
        ).fetchone()
        if authority_row is None:
            raise FileNotFoundError(f"Legal authority {authority_id} was not found.")
        version_rows = connection.execute(
            "SELECT * FROM authority_versions WHERE authority_id = ? ORDER BY effective_date, version_id",
            (authority_id,),
        ).fetchall()
        count = connection.execute(
            "SELECT COUNT(*) AS n FROM legal_articles WHERE authority_id = ?", (authority_id,)
        ).fetchone()["n"]
        return AuthoritySummary(
            authority=_authority_from_row(authority_row),
            versions=[_version_from_row(row) for row in version_rows],
            article_count=count,
        )


def get_evidence(db_path: Path, legal_evidence_id: str) -> LegalEvidenceRecord:
    if not db_path.exists():
        raise FileNotFoundError("Legal database has not been built yet.")
    with connect(db_path) as connection:
        initialize_schema(connection)
        row = connection.execute(
            """
            SELECT a.*, v.*, au.title, au.authority_type, au.issuing_body, au.document_number, au.jurisdiction
            FROM legal_articles a
            JOIN authority_versions v
              ON v.authority_id = a.authority_id AND v.version_id = a.version_id
            JOIN authorities au ON au.authority_id = a.authority_id
            WHERE a.legal_evidence_id = ?
            """,
            (legal_evidence_id,),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Legal evidence {legal_evidence_id} was not found.")
        return LegalEvidenceRecord(
            authority=_authority_from_row(row),
            version=_version_from_row(row),
            article=_article_from_row(row),
        )


def resolve_version(db_path: Path, authority_id: str, as_of: date) -> VersionResolution:
    if not db_path.exists():
        raise FileNotFoundError("Legal database has not been built yet.")
    with connect(db_path) as connection:
        initialize_schema(connection)
        rows = connection.execute(
            """
            SELECT * FROM authority_versions
            WHERE authority_id = ?
              AND effective_date <= ?
              AND (end_date_exclusive IS NULL OR ? < end_date_exclusive)
            ORDER BY effective_date, version_id
            """,
            (authority_id, as_of.isoformat(), as_of.isoformat()),
        ).fetchall()
        if not rows:
            authority_exists = connection.execute(
                "SELECT 1 FROM authorities WHERE authority_id = ?", (authority_id,)
            ).fetchone()
            if authority_exists is None:
                raise FileNotFoundError(f"Legal authority {authority_id} was not found.")
            return VersionResolution(
                authority_id=authority_id,
                as_of=as_of,
                state=VersionResolutionState.NO_APPLICABLE_VERSION,
                message=f"No stored version is applicable on {as_of.isoformat()}.",
            )
        if len(rows) > 1:
            ids = [row["version_id"] for row in rows]
            return VersionResolution(
                authority_id=authority_id,
                as_of=as_of,
                state=VersionResolutionState.AMBIGUOUS,
                candidate_version_ids=ids,
                message="Multiple stored version intervals overlap; human/source review is required.",
            )
        version = _version_from_row(rows[0])
        return VersionResolution(
            authority_id=authority_id,
            as_of=as_of,
            state=VersionResolutionState.RESOLVED,
            version=version,
            candidate_version_ids=[version.version_id],
            message=f"Resolved version {version.version_id} for {as_of.isoformat()}.",
        )


def get_article_for_version(
    db_path: Path, authority_id: str, version_id: str, article_token: str
) -> LegalArticle | None:
    if not db_path.exists():
        raise FileNotFoundError("Legal database has not been built yet.")
    with connect(db_path) as connection:
        initialize_schema(connection)
        row = connection.execute(
            """
            SELECT * FROM legal_articles
            WHERE authority_id = ? AND version_id = ? AND article_token = ?
            """,
            (authority_id, version_id, article_token),
        ).fetchone()
        return _article_from_row(row) if row is not None else None
