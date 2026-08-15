from __future__ import annotations

import hashlib
import importlib.util
import os
import platform
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlparse

from .legal.models import LEGAL_SCHEMA_VERSION
from .legal.retrieval_models import RETRIEVAL_SCHEMA_VERSION
from .runtime_health_models import (
    RuntimeHealthCheck,
    RuntimeHealthReport,
    RuntimeHealthSeverity,
    RuntimeHealthState,
)
from .storage import legal_db_path, legal_retrieval_index_path, runtime_dir

MIN_PYTHON = (3, 11)
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
DEFAULT_KIMI_BASE_URL = "https://api.moonshot.cn/v1"
DEFAULT_KIMI_MODEL = "kimi-k3"

_ACTION_STATES = {
    RuntimeHealthState.MISSING,
    RuntimeHealthState.STALE,
    RuntimeHealthState.CORRUPT,
    RuntimeHealthState.MISCONFIGURED,
    RuntimeHealthState.ACTION_REQUIRED,
}
_ERROR_STATES = {
    RuntimeHealthState.CORRUPT,
    RuntimeHealthState.MISCONFIGURED,
    RuntimeHealthState.UNAVAILABLE,
    RuntimeHealthState.ACTION_REQUIRED,
}


def _readonly_sqlite(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _quick_check(connection: sqlite3.Connection) -> str:
    row = connection.execute("PRAGMA quick_check").fetchone()
    return str(row[0]) if row else "unknown"


def _legal_fingerprint_readonly(path: Path) -> str:
    with _readonly_sqlite(path) as connection:
        rows = connection.execute(
            """
            SELECT a.legal_evidence_id, a.text_sha256, v.source_snapshot_sha256
            FROM legal_articles a
            JOIN authority_versions v
              ON v.authority_id = a.authority_id AND v.version_id = a.version_id
            ORDER BY a.legal_evidence_id
            """
        ).fetchall()
    payload = "\n".join(
        f"{row['legal_evidence_id']}:{row['text_sha256']}:{row['source_snapshot_sha256']}" for row in rows
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _python_check() -> RuntimeHealthCheck:
    version = platform.python_version()
    supported = sys.version_info >= MIN_PYTHON
    return RuntimeHealthCheck(
        check_id="python-runtime",
        label="Python runtime",
        state=RuntimeHealthState.OK if supported else RuntimeHealthState.UNAVAILABLE,
        severity=RuntimeHealthSeverity.INFO if supported else RuntimeHealthSeverity.ERROR,
        required_for_base_app=True,
        detail=(
            f"Python {version} satisfies the supported >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]} runtime."
            if supported
            else f"Python {version} is older than the supported >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]} runtime."
        ),
        action=None if supported else "Install Python 3.11 or newer and recreate the local virtual environment.",
        metadata={"python_version": version},
    )


def _runtime_directory_check(path: Path) -> RuntimeHealthCheck:
    if path.exists():
        if not path.is_dir():
            return RuntimeHealthCheck(
                check_id="runtime-directory",
                label="Runtime directory",
                state=RuntimeHealthState.MISCONFIGURED,
                severity=RuntimeHealthSeverity.ERROR,
                required_for_base_app=True,
                detail=f"Configured runtime path is not a directory: {path}",
                action="Set LAW_RAG_RUNTIME_DIR to a writable directory or remove the conflicting file.",
                metadata={"path": str(path), "exists": True},
            )
        writable = os.access(path, os.W_OK)
        return RuntimeHealthCheck(
            check_id="runtime-directory",
            label="Runtime directory",
            state=RuntimeHealthState.OK if writable else RuntimeHealthState.ACTION_REQUIRED,
            severity=RuntimeHealthSeverity.INFO if writable else RuntimeHealthSeverity.ERROR,
            required_for_base_app=True,
            detail=(
                f"Runtime directory exists and appears writable: {path}"
                if writable
                else f"Runtime directory exists but is not writable by the current process: {path}"
            ),
            action=None if writable else "Grant write access or set LAW_RAG_RUNTIME_DIR to a writable local directory.",
            metadata={"path": str(path), "exists": True, "writable": writable},
        )

    parent = path.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    creatable = parent.exists() and parent.is_dir() and os.access(parent, os.W_OK)
    return RuntimeHealthCheck(
        check_id="runtime-directory",
        label="Runtime directory",
        state=RuntimeHealthState.OK if creatable else RuntimeHealthState.ACTION_REQUIRED,
        severity=RuntimeHealthSeverity.INFO if creatable else RuntimeHealthSeverity.ERROR,
        required_for_base_app=True,
        detail=(
            f"Runtime directory does not exist yet; nearest existing parent appears writable: {parent}"
            if creatable
            else f"Runtime directory does not exist and its nearest existing parent is not writable: {parent}"
        ),
        action=None if creatable else "Create a writable runtime directory or set LAW_RAG_RUNTIME_DIR explicitly.",
        metadata={"path": str(path), "exists": False, "nearest_existing_parent": str(parent)},
    )


def _legal_db_check(path: Path) -> RuntimeHealthCheck:
    if not path.exists():
        return RuntimeHealthCheck(
            check_id="legal-database",
            label="Legal evidence database",
            state=RuntimeHealthState.MISSING,
            severity=RuntimeHealthSeverity.WARNING,
            required_for_base_app=False,
            detail="legal.db has not been built. Local upload/inspection can still start, but legal retrieval/audit is unavailable.",
            action="Run rebuild-legal-seed.bat before legal retrieval or AI audit.",
            metadata={"path": str(path), "exists": False},
        )
    try:
        with _readonly_sqlite(path) as connection:
            quick = _quick_check(connection)
            if quick.lower() != "ok":
                raise sqlite3.DatabaseError(f"PRAGMA quick_check returned {quick}")
            meta = connection.execute(
                "SELECT value FROM legal_meta WHERE key = 'schema_version'"
            ).fetchone()
            article_count = connection.execute("SELECT COUNT(*) FROM legal_articles").fetchone()[0]
        schema = str(meta["value"]) if meta is not None else None
        if schema != LEGAL_SCHEMA_VERSION:
            return RuntimeHealthCheck(
                check_id="legal-database",
                label="Legal evidence database",
                state=RuntimeHealthState.MISCONFIGURED,
                severity=RuntimeHealthSeverity.ERROR,
                required_for_base_app=False,
                detail=f"legal.db schema is {schema!r}; expected {LEGAL_SCHEMA_VERSION!r}.",
                action="Preserve the current database, then explicitly rebuild the verified legal seed.",
                metadata={"path": str(path), "schema_version": schema, "article_count": int(article_count)},
            )
        return RuntimeHealthCheck(
            check_id="legal-database",
            label="Legal evidence database",
            state=RuntimeHealthState.OK,
            severity=RuntimeHealthSeverity.INFO,
            required_for_base_app=False,
            detail=f"legal.db passed SQLite quick_check with {article_count} article records.",
            metadata={"path": str(path), "schema_version": schema, "article_count": int(article_count)},
        )
    except (sqlite3.Error, OSError) as exc:
        return RuntimeHealthCheck(
            check_id="legal-database",
            label="Legal evidence database",
            state=RuntimeHealthState.CORRUPT,
            severity=RuntimeHealthSeverity.ERROR,
            required_for_base_app=False,
            detail=f"legal.db is unreadable or failed integrity inspection: {type(exc).__name__}.",
            action="Do not delete it automatically. Preserve/copy the file, then explicitly rebuild the verified legal seed.",
            metadata={"path": str(path)},
        )


def _retrieval_db_check(index_path: Path, legal_path: Path) -> RuntimeHealthCheck:
    if not index_path.exists():
        return RuntimeHealthCheck(
            check_id="retrieval-database",
            label="Legal retrieval index",
            state=RuntimeHealthState.MISSING,
            severity=RuntimeHealthSeverity.WARNING,
            required_for_base_app=False,
            detail="retrieval.db has not been built. Exact canonical legal evidence remains stored in legal.db, but indexed retrieval is unavailable.",
            action="Run build-retrieval-index.bat after legal.db is healthy.",
            metadata={"path": str(index_path), "exists": False},
        )
    try:
        with _readonly_sqlite(index_path) as connection:
            quick = _quick_check(connection)
            if quick.lower() != "ok":
                raise sqlite3.DatabaseError(f"PRAGMA quick_check returned {quick}")
            meta_rows = connection.execute("SELECT key, value FROM retrieval_meta").fetchall()
            meta = {str(row["key"]): str(row["value"]) for row in meta_rows}
            article_count = int(connection.execute("SELECT COUNT(*) FROM legal_fts").fetchone()[0])
            semantic_count = int(connection.execute("SELECT COUNT(*) FROM semantic_vectors").fetchone()[0])
        if meta.get("schema_version") != RETRIEVAL_SCHEMA_VERSION:
            return RuntimeHealthCheck(
                check_id="retrieval-database",
                label="Legal retrieval index",
                state=RuntimeHealthState.MISCONFIGURED,
                severity=RuntimeHealthSeverity.ERROR,
                required_for_base_app=False,
                detail=f"retrieval.db schema is {meta.get('schema_version')!r}; expected {RETRIEVAL_SCHEMA_VERSION!r}.",
                action="Preserve the current index, then explicitly rebuild retrieval.db.",
                metadata={"path": str(index_path), "article_count": article_count},
            )
        if legal_path.exists():
            try:
                current_fingerprint = _legal_fingerprint_readonly(legal_path)
            except (sqlite3.Error, OSError):
                current_fingerprint = None
            indexed_fingerprint = meta.get("legal_source_fingerprint")
            if current_fingerprint is not None and indexed_fingerprint != current_fingerprint:
                return RuntimeHealthCheck(
                    check_id="retrieval-database",
                    label="Legal retrieval index",
                    state=RuntimeHealthState.STALE,
                    severity=RuntimeHealthSeverity.WARNING,
                    required_for_base_app=False,
                    detail="retrieval.db is readable but its legal-source fingerprint does not match the current legal.db.",
                    action="Preserve both files, then explicitly rebuild the retrieval index from the current legal.db.",
                    metadata={
                        "path": str(index_path),
                        "article_count": article_count,
                        "semantic_vector_count": semantic_count,
                    },
                )
        return RuntimeHealthCheck(
            check_id="retrieval-database",
            label="Legal retrieval index",
            state=RuntimeHealthState.OK,
            severity=RuntimeHealthSeverity.INFO,
            required_for_base_app=False,
            detail=f"retrieval.db passed integrity inspection with {article_count} indexed articles.",
            metadata={
                "path": str(index_path),
                "article_count": article_count,
                "semantic_vector_count": semantic_count,
                "lexical_tokenizer": meta.get("lexical_tokenizer"),
            },
        )
    except (sqlite3.Error, OSError, ValueError) as exc:
        return RuntimeHealthCheck(
            check_id="retrieval-database",
            label="Legal retrieval index",
            state=RuntimeHealthState.CORRUPT,
            severity=RuntimeHealthSeverity.ERROR,
            required_for_base_app=False,
            detail=f"retrieval.db is unreadable or failed integrity inspection: {type(exc).__name__}.",
            action="Do not delete it automatically. Preserve/copy the file, then explicitly rebuild the retrieval index.",
            metadata={"path": str(index_path)},
        )


def _module_check(check_id: str, label: str, modules: tuple[str, ...], action: str) -> RuntimeHealthCheck:
    missing = [name for name in modules if importlib.util.find_spec(name) is None]
    if missing:
        return RuntimeHealthCheck(
            check_id=check_id,
            label=label,
            state=RuntimeHealthState.OPTIONAL_NOT_CONFIGURED,
            severity=RuntimeHealthSeverity.INFO,
            required_for_base_app=False,
            detail=f"Optional runtime is not installed ({', '.join(missing)} missing). Supported fallback paths remain available.",
            action=action,
            metadata={"missing_modules": ",".join(missing)},
        )
    return RuntimeHealthCheck(
        check_id=check_id,
        label=label,
        state=RuntimeHealthState.OK,
        severity=RuntimeHealthSeverity.INFO,
        required_for_base_app=False,
        detail="Optional dependency modules are discoverable. This check did not load model weights or make a network request.",
    )


def _valid_http_base_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _provider_check(
    *,
    check_id: str,
    label: str,
    key_env: str,
    base_env: str,
    model_env: str,
    default_base: str,
    default_model: str,
) -> RuntimeHealthCheck:
    key_present = bool(os.getenv(key_env, "").strip())
    base_url = os.getenv(base_env, default_base).strip().rstrip("/") or default_base
    model = os.getenv(model_env, default_model).strip() or default_model
    if not _valid_http_base_url(base_url):
        return RuntimeHealthCheck(
            check_id=check_id,
            label=label,
            state=RuntimeHealthState.MISCONFIGURED,
            severity=RuntimeHealthSeverity.WARNING,
            required_for_base_app=False,
            detail=f"Provider base URL is not a valid HTTP(S) URL: {base_url}",
            action=f"Correct {base_env}. No network request was attempted.",
            metadata={"configured": key_present, "base_url": base_url, "model": model},
        )
    if not key_present:
        return RuntimeHealthCheck(
            check_id=check_id,
            label=label,
            state=RuntimeHealthState.OPTIONAL_NOT_CONFIGURED,
            severity=RuntimeHealthSeverity.INFO,
            required_for_base_app=False,
            detail=f"{key_env} is not configured. Local non-provider workflows remain available.",
            action=f"Set {key_env} locally before invoking this provider.",
            metadata={"configured": False, "base_url": base_url, "model": model},
        )
    return RuntimeHealthCheck(
        check_id=check_id,
        label=label,
        state=RuntimeHealthState.OK,
        severity=RuntimeHealthSeverity.INFO,
        required_for_base_app=False,
        detail="Provider configuration is present. The secret value is not inspected or returned, and no network request was made.",
        metadata={"configured": True, "base_url": base_url, "model": model},
    )


def inspect_runtime_health() -> RuntimeHealthReport:
    rt = runtime_dir()
    legal = legal_db_path()
    retrieval = legal_retrieval_index_path()
    checks = [
        _python_check(),
        _runtime_directory_check(rt),
        _legal_db_check(legal),
        _retrieval_db_check(retrieval, legal),
        _module_check(
            "ocr-runtime",
            "PaddleOCR local runtime",
            ("paddle", "paddleocr"),
            "Run setup-ocr-cpu.bat only if scanned/image contracts require OCR.",
        ),
        _module_check(
            "semantic-runtime",
            "Local semantic retrieval runtime",
            ("sentence_transformers",),
            "Run setup-rag-semantic-cpu.bat only if semantic retrieval is desired; Exact + BM25 remain supported.",
        ),
        _provider_check(
            check_id="deepseek-provider",
            label="DeepSeek primary provider",
            key_env="DEEPSEEK_API_KEY",
            base_env="DEEPSEEK_BASE_URL",
            model_env="DEEPSEEK_MODEL",
            default_base=DEFAULT_DEEPSEEK_BASE_URL,
            default_model=DEFAULT_DEEPSEEK_MODEL,
        ),
        _provider_check(
            check_id="kimi-provider",
            label="Kimi secondary provider",
            key_env="MOONSHOT_API_KEY",
            base_env="MOONSHOT_BASE_URL",
            model_env="MOONSHOT_MODEL",
            default_base=DEFAULT_KIMI_BASE_URL,
            default_model=DEFAULT_KIMI_MODEL,
        ),
    ]
    base_app_ready = all(
        check.state not in _ERROR_STATES
        for check in checks
        if check.required_for_base_app
    )
    action_required = any(check.state in _ACTION_STATES for check in checks)
    return RuntimeHealthReport(
        base_app_ready=base_app_ready,
        action_required=action_required,
        checks=checks,
        warnings=[
            "Runtime diagnostics are local and non-mutating; os.access writability is a best-effort preflight, not a guarantee against later filesystem errors.",
            "Provider checks inspect configuration presence only and never return API key values or make network requests.",
        ],
    )
