from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from pydantic import ValidationError

from .models import (
    ImportState,
    ImportValidationReport,
    LegalImportRecord,
    LegalManifest,
    LegalVersion,
    ManifestImportReport,
    ManifestRecord,
    SourceRole,
    ValidationIssue,
)
from .parser import LegalParseError, normalize_snapshot_text, parse_chinese_articles, sha256_text
from .source_registry import (
    LegalSourceRegistry,
    LegalSourceRegistryError,
    load_source_registry,
    validate_official_source_ref,
)
from .store import connect, initialize_schema

OFFICIAL_HOSTS = {
    "flk.npc.gov.cn",
    "www.npc.gov.cn",
    "npc.gov.cn",
    "www.court.gov.cn",
    "court.gov.cn",
    "gongbao.court.gov.cn",
    "cicc.court.gov.cn",
    "www.gov.cn",
    "gov.cn",
    "www.cac.gov.cn",
    "cac.gov.cn",
}


class LegalImportError(RuntimeError):
    def __init__(self, message: str, report: ManifestImportReport | None = None):
        super().__init__(message)
        self.report = report


@dataclass(frozen=True)
class PreparedRecord:
    manifest: ManifestRecord
    record: LegalImportRecord
    validation: ImportValidationReport


def _source_validation(
    record: ManifestRecord,
    *,
    allow_non_official_sources: bool,
    source_registry: LegalSourceRegistry | None,
) -> tuple[bool, list[ValidationIssue]]:
    if allow_non_official_sources:
        return True, []

    if source_registry is not None:
        issues: list[ValidationIssue] = []
        if not any(source.role == SourceRole.PRIMARY for source in record.source_refs):
            issues.append(
                ValidationIssue(
                    code="MISSING_PRIMARY_OFFICIAL_SOURCE",
                    message="Registry-aware imports require at least one PRIMARY official source reference.",
                    critical=True,
                )
            )
        for source in record.source_refs:
            try:
                validate_official_source_ref(source, source_registry)
            except LegalSourceRegistryError as exc:
                issues.append(
                    ValidationIssue(
                        code="INVALID_OFFICIAL_SOURCE_REF",
                        message=str(exc),
                        critical=True,
                    )
                )
        return not issues, issues

    for source in record.source_refs:
        hostname = (urlparse(str(source.url)).hostname or "").lower()
        if hostname not in OFFICIAL_HOSTS:
            return (
                False,
                [
                    ValidationIssue(
                        code="UNRECOGNIZED_SOURCE_HOST",
                        message="All source references must use the Stage 6 authoritative-source allowlist.",
                        critical=True,
                    )
                ],
            )
    return True, []


def _load_manifest(manifest_path: Path) -> LegalManifest:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        return LegalManifest.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise LegalImportError(f"Malformed legal manifest: {exc}") from exc


def _load_optional_source_registry(path: Path | None) -> LegalSourceRegistry | None:
    if path is None:
        return None
    try:
        return load_source_registry(path.resolve())
    except LegalSourceRegistryError as exc:
        raise LegalImportError(f"Malformed legal source registry: {exc}") from exc


def _snapshot_path(manifest_path: Path, configured: str) -> Path:
    candidate = Path(configured)
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    return candidate.resolve()


def _prepare_record(
    manifest_path: Path,
    record: ManifestRecord,
    *,
    allow_non_official_sources: bool,
    source_registry: LegalSourceRegistry | None,
) -> PreparedRecord:
    recognized, source_issues = _source_validation(
        record,
        allow_non_official_sources=allow_non_official_sources,
        source_registry=source_registry,
    )
    issues: list[ValidationIssue] = list(source_issues)

    source_path = _snapshot_path(manifest_path, record.snapshot_path)
    try:
        normalized = normalize_snapshot_text(source_path.read_text(encoding="utf-8"))
    except OSError as exc:
        normalized = ""
        issues.append(
            ValidationIssue(
                code="SNAPSHOT_READ_FAILED",
                message=f"Source snapshot could not be read: {exc}",
                critical=True,
            )
        )

    actual_hash = sha256_text(normalized) if normalized else "0" * 64
    if normalized and actual_hash != record.expected_source_sha256:
        issues.append(
            ValidationIssue(
                code="SOURCE_HASH_MISMATCH",
                message=(
                    f"Expected source SHA-256 {record.expected_source_sha256} but found {actual_hash}. "
                    "The curated source changed or the manifest is stale."
                ),
                critical=True,
            )
        )

    parsed_articles = []
    preamble_text: str | None = None
    if normalized:
        try:
            parsed = parse_chinese_articles(
                normalized,
                authority_id=record.authority.authority_id,
                version_id=record.version_id,
            )
            parsed_articles = parsed.articles
            preamble_text = parsed.preamble_text
        except LegalParseError as exc:
            issues.append(
                ValidationIssue(
                    code="ARTICLE_PARSE_FAILED",
                    message=str(exc),
                    critical=True,
                )
            )

    tokens = [article.article_token for article in parsed_articles]
    duplicate_tokens = sorted({token for token in tokens if tokens.count(token) > 1})
    if duplicate_tokens:
        issues.append(
            ValidationIssue(
                code="DUPLICATE_ARTICLE_TOKEN",
                message=f"Duplicate article tokens: {', '.join(duplicate_tokens)}",
                critical=True,
            )
        )

    if len(parsed_articles) != record.expected_article_count:
        issues.append(
            ValidationIssue(
                code="ARTICLE_COUNT_MISMATCH",
                message=(
                    f"Expected {record.expected_article_count} articles but parsed {len(parsed_articles)}."
                ),
                critical=True,
            )
        )

    version = LegalVersion(
        authority_id=record.authority.authority_id,
        version_id=record.version_id,
        status=record.status,
        publication_date=record.publication_date,
        effective_date=record.effective_date,
        end_date_exclusive=record.end_date_exclusive,
        repeal_date=record.repeal_date,
        supersedes_version_id=record.supersedes_version_id,
        superseded_by_version_id=record.superseded_by_version_id,
        coverage_type=record.coverage_type,
        coverage_note=record.coverage_note,
        source_refs=record.source_refs,
        source_snapshot_sha256=actual_hash,
        verified_on=record.verified_on,
        verification_note=record.verification_note,
    )
    critical = any(issue.critical for issue in issues)
    validation = ImportValidationReport(
        authority_id=record.authority.authority_id,
        version_id=record.version_id,
        source_recognized=recognized,
        source_sha256=actual_hash,
        expected_source_sha256=record.expected_source_sha256,
        metadata_complete=True,
        parsed_article_count=len(parsed_articles),
        expected_article_count=record.expected_article_count,
        duplicate_article_tokens=duplicate_tokens,
        empty_article_tokens=[],
        state=ImportState.REJECTED if critical else ImportState.IMPORTED,
        issues=issues,
    )
    return PreparedRecord(
        manifest=record,
        record=LegalImportRecord(
            authority=record.authority,
            version=version,
            articles=parsed_articles,
            preamble_text=preamble_text,
        ),
        validation=validation,
    )


def _authority_identity(row: sqlite3.Row) -> tuple[str, str, str, str | None, str]:
    return (
        row["title"],
        row["authority_type"],
        row["issuing_body"],
        row["document_number"],
        row["jurisdiction"],
    )


def _record_authority_identity(record: LegalImportRecord) -> tuple[str, str, str, str | None, str]:
    authority = record.authority
    return (
        authority.title,
        authority.authority_type.value,
        authority.issuing_body,
        authority.document_number,
        authority.jurisdiction,
    )


def _interval_overlap(
    start_a: str,
    end_a: str | None,
    start_b: str,
    end_b: str | None,
) -> bool:
    end_a_cmp = end_a or "9999-12-31"
    end_b_cmp = end_b or "9999-12-31"
    return start_a < end_b_cmp and start_b < end_a_cmp


def _inspect_existing(connection: sqlite3.Connection, prepared: PreparedRecord) -> tuple[bool, list[ValidationIssue]]:
    record = prepared.record
    issues: list[ValidationIssue] = []
    authority_row = connection.execute(
        "SELECT * FROM authorities WHERE authority_id = ?",
        (record.authority.authority_id,),
    ).fetchone()
    if authority_row is not None and _authority_identity(authority_row) != _record_authority_identity(record):
        issues.append(
            ValidationIssue(
                code="AUTHORITY_IDENTITY_CONFLICT",
                message="Existing authority ID maps to different authority metadata.",
                critical=True,
            )
        )

    version_row = connection.execute(
        "SELECT * FROM authority_versions WHERE authority_id = ? AND version_id = ?",
        (record.version.authority_id, record.version.version_id),
    ).fetchone()
    if version_row is not None:
        if version_row["source_snapshot_sha256"] != record.version.source_snapshot_sha256:
            issues.append(
                ValidationIssue(
                    code="SOURCE_VERSION_IDENTITY_CONFLICT",
                    message="The same authority/version ID already exists with a different source hash.",
                    critical=True,
                )
            )
        else:
            existing_articles = connection.execute(
                """
                SELECT article_token, text_sha256 FROM legal_articles
                WHERE authority_id = ? AND version_id = ? ORDER BY article_token
                """,
                (record.version.authority_id, record.version.version_id),
            ).fetchall()
            expected = sorted((article.article_token, article.text_sha256) for article in record.articles)
            actual = sorted((row["article_token"], row["text_sha256"]) for row in existing_articles)
            if expected != actual:
                issues.append(
                    ValidationIssue(
                        code="ARTICLE_IDENTITY_CONFLICT",
                        message="Existing version source hash matches but stored article hashes differ.",
                        critical=True,
                    )
                )
            else:
                return True, issues

    other_versions = connection.execute(
        """
        SELECT version_id, effective_date, end_date_exclusive FROM authority_versions
        WHERE authority_id = ? AND version_id <> ?
        """,
        (record.version.authority_id, record.version.version_id),
    ).fetchall()
    for row in other_versions:
        if _interval_overlap(
            record.version.effective_date.isoformat(),
            record.version.end_date_exclusive.isoformat() if record.version.end_date_exclusive else None,
            row["effective_date"],
            row["end_date_exclusive"],
        ):
            issues.append(
                ValidationIssue(
                    code="VERSION_INTERVAL_OVERLAP",
                    message=f"Version interval overlaps stored version {row['version_id']}; resolver will report ambiguity.",
                    critical=False,
                )
            )
    return False, issues


def _insert_record(connection: sqlite3.Connection, record: LegalImportRecord) -> None:
    authority = record.authority
    version = record.version
    connection.execute(
        """
        INSERT OR IGNORE INTO authorities(
            authority_id, title, authority_type, issuing_body, document_number, jurisdiction
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            authority.authority_id,
            authority.title,
            authority.authority_type.value,
            authority.issuing_body,
            authority.document_number,
            authority.jurisdiction,
        ),
    )
    connection.execute(
        """
        INSERT INTO authority_versions(
            authority_id, version_id, status, publication_date, effective_date,
            end_date_exclusive, repeal_date, supersedes_version_id, superseded_by_version_id,
            coverage_type, coverage_note, source_refs_json, source_snapshot_sha256,
            importer_version, schema_version, verified_on, verification_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version.authority_id,
            version.version_id,
            version.status.value,
            version.publication_date.isoformat() if version.publication_date else None,
            version.effective_date.isoformat(),
            version.end_date_exclusive.isoformat() if version.end_date_exclusive else None,
            version.repeal_date.isoformat() if version.repeal_date else None,
            version.supersedes_version_id,
            version.superseded_by_version_id,
            version.coverage_type.value,
            version.coverage_note,
            json.dumps([item.model_dump(mode="json") for item in version.source_refs], ensure_ascii=False, sort_keys=True),
            version.source_snapshot_sha256,
            version.importer_version,
            version.schema_version,
            version.verified_on.isoformat() if version.verified_on else None,
            version.verification_note,
        ),
    )
    for article in record.articles:
        connection.execute(
            """
            INSERT INTO legal_articles(
                legal_evidence_id, authority_id, version_id, article_id, article_token,
                article_ordinal, article_text, text_sha256, heading_context_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article.legal_evidence_id,
                article.authority_id,
                article.version_id,
                article.article_id,
                article.article_token,
                article.article_ordinal,
                article.text,
                article.text_sha256,
                json.dumps(article.heading_context, ensure_ascii=False),
            ),
        )


def _report(
    manifest_path: Path,
    db_path: Path,
    validations: list[ImportValidationReport],
) -> ManifestImportReport:
    return ManifestImportReport(
        manifest_path=str(manifest_path),
        database_path=str(db_path),
        imported_records=sum(item.state == ImportState.IMPORTED for item in validations),
        rejected_records=sum(item.state == ImportState.REJECTED for item in validations),
        no_change_records=sum(item.state == ImportState.NO_CHANGE for item in validations),
        reports=validations,
    )


def write_import_report(report: ManifestImportReport, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")


def import_manifest(
    manifest_path: Path,
    db_path: Path,
    *,
    rebuild: bool = False,
    allow_non_official_sources: bool = False,
    source_registry_path: Path | None = None,
    report_path: Path | None = None,
) -> ManifestImportReport:
    manifest_path = manifest_path.resolve()
    db_path = db_path.resolve()
    manifest = _load_manifest(manifest_path)
    source_registry = _load_optional_source_registry(source_registry_path)

    identity_pairs = [(item.authority.authority_id, item.version_id) for item in manifest.records]
    duplicate_pairs = sorted({pair for pair in identity_pairs if identity_pairs.count(pair) > 1})
    if duplicate_pairs:
        raise LegalImportError(f"Manifest contains duplicate authority/version identities: {duplicate_pairs}")

    prepared = [
        _prepare_record(
            manifest_path,
            item,
            allow_non_official_sources=allow_non_official_sources,
            source_registry=source_registry,
        )
        for item in manifest.records
    ]
    validations = [item.validation.model_copy(deep=True) for item in prepared]
    if any(any(issue.critical for issue in report.issues) for report in validations):
        report = _report(manifest_path, db_path, validations)
        if report_path:
            write_import_report(report, report_path)
        raise LegalImportError("Legal manifest validation failed; database was not modified.", report)

    target_path = db_path
    working_path = db_path
    if rebuild:
        working_path = db_path.with_name(f".{db_path.name}.rebuild.tmp")
        working_path.unlink(missing_ok=True)

    connection = connect(working_path)
    try:
        initialize_schema(connection)
        connection.commit()
        connection.execute("BEGIN IMMEDIATE")
        for index, item in enumerate(prepared):
            no_change, existing_issues = _inspect_existing(connection, item)
            validations[index].issues.extend(existing_issues)
            if any(issue.critical for issue in existing_issues):
                validations[index].state = ImportState.REJECTED
                raise LegalImportError("Existing legal-store identity conflict detected.")
            validations[index].interval_conflicts.extend(
                issue.message for issue in existing_issues if issue.code == "VERSION_INTERVAL_OVERLAP"
            )
            if no_change:
                validations[index].state = ImportState.NO_CHANGE
                continue
            _insert_record(connection, item.record)
            validations[index].state = ImportState.IMPORTED
        connection.commit()
    except Exception as exc:
        connection.rollback()
        report = _report(manifest_path, target_path, validations)
        if report_path:
            write_import_report(report, report_path)
        if rebuild:
            working_path.unlink(missing_ok=True)
        if isinstance(exc, LegalImportError):
            exc.report = report
            raise
        raise LegalImportError(f"Legal import transaction rolled back: {exc}", report) from exc
    finally:
        connection.close()

    if rebuild:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(working_path, target_path)

    report = _report(manifest_path, target_path, validations)
    if report_path:
        write_import_report(report, report_path)
    return report
