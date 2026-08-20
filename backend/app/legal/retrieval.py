from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from array import array
from datetime import date
from pathlib import Path

from .embeddings import (
    BgeSmallZhProvider,
    EmbeddingProvider,
    EmbeddingProviderUnavailable,
    cosine_similarity,
)
from .models import LegalEvidenceRecord, VersionResolutionState
from .parser import chinese_integer
from .retrieval_models import (
    AuthorityResolutionNote,
    ChannelScore,
    RetrievalCandidate,
    RetrievalChannel,
    RetrievalIndexSummary,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalState,
    RETRIEVAL_SCHEMA_VERSION,
)
from .store import connect as connect_legal
from .store import get_evidence, get_summary, list_authorities, resolve_version

LEXICAL_INDEX_VERSION = "fts5-trigram-v1"
RRF_K = 60
CHANNEL_WEIGHTS = {
    RetrievalChannel.EXACT: 4.0,
    RetrievalChannel.LEXICAL: 1.5,
    RetrievalChannel.SEMANTIC: 1.0,
}
ARTICLE_REF_RE = re.compile(r"第([零〇一二三四五六七八九十百千万两\d]+)条")
NON_QUERY_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")


class RetrievalIndexError(RuntimeError):
    pass


INDEX_SCHEMA_SQL = """
CREATE TABLE retrieval_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE semantic_vectors (
    legal_evidence_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    dimension INTEGER NOT NULL,
    vector_blob BLOB NOT NULL
);
"""


def _connect_index(index_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(index_path)
    connection.row_factory = sqlite3.Row
    return connection


def _legal_source_fingerprint(legal_db_path: Path) -> str:
    with connect_legal(legal_db_path) as connection:
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


def _indexed_text(row: sqlite3.Row) -> str:
    context = " ".join(json.loads(row["heading_context_json"]))
    return f"{row['title']} {row['article_token']} {context} {row['article_text']}".strip()


def build_retrieval_index(
    legal_db_path: Path,
    index_path: Path,
    *,
    semantic_provider: EmbeddingProvider | None = None,
) -> RetrievalIndexSummary:
    summary = get_summary(legal_db_path)
    if not summary.ready or summary.article_count == 0:
        raise RetrievalIndexError("Legal database is not ready; build the Stage 6 legal store first.")

    with connect_legal(legal_db_path) as legal_connection:
        rows = legal_connection.execute(
            """
            SELECT a.*, au.title
            FROM legal_articles a
            JOIN authorities au ON au.authority_id = a.authority_id
            ORDER BY a.legal_evidence_id
            """
        ).fetchall()

    index_path.parent.mkdir(parents=True, exist_ok=True)
    working_path = index_path.with_name(f".{index_path.name}.rebuild.tmp")
    working_path.unlink(missing_ok=True)
    connection = _connect_index(working_path)
    try:
        connection.executescript(INDEX_SCHEMA_SQL)
        try:
            connection.execute(
                """
                CREATE VIRTUAL TABLE legal_fts USING fts5(
                    legal_evidence_id UNINDEXED,
                    authority_id UNINDEXED,
                    version_id UNINDEXED,
                    authority_title,
                    article_token,
                    heading_context,
                    article_text,
                    tokenize='trigram'
                )
                """
            )
        except sqlite3.OperationalError as exc:
            raise RetrievalIndexError(
                "SQLite FTS5 trigram tokenizer is unavailable in this Python/SQLite runtime."
            ) from exc

        for row in rows:
            context = " ".join(json.loads(row["heading_context_json"]))
            connection.execute(
                """
                INSERT INTO legal_fts(
                    legal_evidence_id, authority_id, version_id,
                    authority_title, article_token, heading_context, article_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["legal_evidence_id"],
                    row["authority_id"],
                    row["version_id"],
                    row["title"],
                    row["article_token"],
                    context,
                    row["article_text"],
                ),
            )

        fingerprint = _legal_source_fingerprint(legal_db_path)
        metadata = {
            "schema_version": RETRIEVAL_SCHEMA_VERSION,
            "legal_source_fingerprint": fingerprint,
            "lexical_index_version": LEXICAL_INDEX_VERSION,
            "lexical_tokenizer": "fts5-trigram",
            "article_count": str(len(rows)),
        }

        if semantic_provider is not None:
            texts = [_indexed_text(row) for row in rows]
            vectors = semantic_provider.encode(texts, is_query=False)
            if len(vectors) != len(rows):
                raise RetrievalIndexError("Embedding provider returned an unexpected vector count.")
            for row, vector in zip(rows, vectors, strict=True):
                if len(vector) != semantic_provider.dimension:
                    raise RetrievalIndexError("Embedding provider returned an unexpected dimension.")
                blob = array("f", vector).tobytes()
                connection.execute(
                    "INSERT INTO semantic_vectors VALUES (?, ?, ?, ?, ?)",
                    (
                        row["legal_evidence_id"],
                        semantic_provider.provider_name,
                        semantic_provider.model_name,
                        semantic_provider.dimension,
                        blob,
                    ),
                )
            metadata.update(
                {
                    "semantic_provider": semantic_provider.provider_name,
                    "semantic_model": semantic_provider.model_name,
                    "semantic_dimension": str(semantic_provider.dimension),
                }
            )

        connection.executemany(
            "INSERT INTO retrieval_meta(key, value) VALUES (?, ?)", metadata.items()
        )
        connection.commit()
    except Exception:
        connection.rollback()
        working_path.unlink(missing_ok=True)
        raise
    finally:
        connection.close()

    os.replace(working_path, index_path)
    return get_retrieval_index_summary(index_path, legal_db_path)


def get_retrieval_index_summary(index_path: Path, legal_db_path: Path | None = None) -> RetrievalIndexSummary:
    if not index_path.exists():
        return RetrievalIndexSummary(ready=False)
    try:
        with _connect_index(index_path) as connection:
            metadata = {
                row["key"]: row["value"]
                for row in connection.execute("SELECT key, value FROM retrieval_meta").fetchall()
            }
            article_count = connection.execute("SELECT COUNT(*) AS n FROM legal_fts").fetchone()["n"]
            semantic_count = connection.execute("SELECT COUNT(*) AS n FROM semantic_vectors").fetchone()["n"]
    except sqlite3.Error as exc:
        raise RetrievalIndexError(f"Retrieval index is unreadable: {exc}") from exc

    ready = metadata.get("schema_version") == RETRIEVAL_SCHEMA_VERSION
    if legal_db_path is not None and legal_db_path.exists() and ready:
        ready = metadata.get("legal_source_fingerprint") == _legal_source_fingerprint(legal_db_path)
    return RetrievalIndexSummary(
        ready=ready,
        schema_version=metadata.get("schema_version"),
        legal_source_fingerprint=metadata.get("legal_source_fingerprint"),
        lexical_ready=article_count > 0,
        lexical_tokenizer=metadata.get("lexical_tokenizer"),
        article_count=article_count,
        semantic_ready=semantic_count == article_count and article_count > 0,
        semantic_provider=metadata.get("semantic_provider"),
        semantic_model=metadata.get("semantic_model"),
        semantic_dimension=int(metadata["semantic_dimension"]) if metadata.get("semantic_dimension") else None,
    )


def _normalize_title(value: str) -> str:
    return NON_QUERY_RE.sub("", value).removeprefix("中华人民共和国")


def _recognize_authority_id(legal_db_path: Path, request: RetrievalRequest) -> str | None:
    allowed = set(request.authority_ids_allowlist)
    if request.authority_id_hint:
        if allowed and request.authority_id_hint not in allowed:
            return None
        return request.authority_id_hint
    authorities = list_authorities(legal_db_path)
    if allowed:
        authorities = [item for item in authorities if item.authority.authority_id in allowed]
    if request.authority_title_hint:
        hint = _normalize_title(request.authority_title_hint)
        matches = [item.authority.authority_id for item in authorities if _normalize_title(item.authority.title) == hint]
        return matches[0] if len(matches) == 1 else None
    compact_query = _normalize_title(request.query)
    matches = []
    for item in authorities:
        title = _normalize_title(item.authority.title)
        if len(title) >= 3 and title in compact_query:
            matches.append(item.authority.authority_id)
    return matches[0] if len(matches) == 1 else None


def _article_ordinal(value: str | None) -> int | None:
    if not value:
        return None
    match = ARTICLE_REF_RE.search(value)
    return chinese_integer(match.group(1)) if match else None


def _query_article_ordinal(request: RetrievalRequest) -> int | None:
    return _article_ordinal(request.article_token_hint) or _article_ordinal(request.query)


def _article_by_ordinal(
    legal_db_path: Path, authority_id: str, version_id: str, ordinal: int
) -> str | None:
    with connect_legal(legal_db_path) as connection:
        row = connection.execute(
            """
            SELECT legal_evidence_id FROM legal_articles
            WHERE authority_id = ? AND version_id = ? AND article_ordinal = ?
            """,
            (authority_id, version_id, ordinal),
        ).fetchone()
        return row["legal_evidence_id"] if row is not None else None


def _lexical_query_text(query: str) -> str | None:
    compact = NON_QUERY_RE.sub("", query.lower())
    if len(compact) < 3:
        return None
    grams: list[str] = []
    for index in range(len(compact) - 2):
        gram = compact[index : index + 3]
        if gram not in grams:
            grams.append(gram)
        if len(grams) >= 32:
            break
    return " OR ".join(f'"{gram.replace(chr(34), chr(34) * 2)}"' for gram in grams)


def _lexical_hits(
    index_path: Path,
    query: str,
    limit: int,
    authority_ids: set[str] | None = None,
) -> list[tuple[str, float]]:
    fts_query = _lexical_query_text(query)
    if not fts_query:
        return []
    params: list[object] = [fts_query]
    authority_clause = ""
    if authority_ids:
        ordered = sorted(authority_ids)
        placeholders = ", ".join("?" for _ in ordered)
        authority_clause = f" AND authority_id IN ({placeholders})"
        params.extend(ordered)
    params.append(limit)
    with _connect_index(index_path) as connection:
        rows = connection.execute(
            f"""
            SELECT legal_evidence_id,
                   bm25(legal_fts, 0.0, 0.0, 0.0, 4.0, 6.0, 2.0, 1.0) AS score
            FROM legal_fts
            WHERE legal_fts MATCH ?{authority_clause}
            ORDER BY score ASC, legal_evidence_id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [(row["legal_evidence_id"], float(row["score"])) for row in rows]


def _load_vector(blob: bytes) -> list[float]:
    values = array("f")
    values.frombytes(blob)
    return list(values)


def _allowed_evidence_ids(legal_db_path: Path, authority_ids: set[str] | None) -> set[str] | None:
    if not authority_ids:
        return None
    ordered = sorted(authority_ids)
    placeholders = ", ".join("?" for _ in ordered)
    with connect_legal(legal_db_path) as connection:
        rows = connection.execute(
            f"SELECT legal_evidence_id FROM legal_articles WHERE authority_id IN ({placeholders})",
            ordered,
        ).fetchall()
    return {row["legal_evidence_id"] for row in rows}


def _semantic_hits(
    index_path: Path,
    query: str,
    limit: int,
    provider: EmbeddingProvider,
    allowed_evidence_ids: set[str] | None = None,
) -> list[tuple[str, float]]:
    query_vector = provider.encode([query], is_query=True)[0]
    with _connect_index(index_path) as connection:
        rows = connection.execute(
            "SELECT * FROM semantic_vectors WHERE provider = ? AND model = ? AND dimension = ?",
            (provider.provider_name, provider.model_name, provider.dimension),
        ).fetchall()
    scored = [
        (row["legal_evidence_id"], cosine_similarity(query_vector, _load_vector(row["vector_blob"])))
        for row in rows
        if allowed_evidence_ids is None or row["legal_evidence_id"] in allowed_evidence_ids
    ]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored[:limit]


def _resolution_note(legal_db_path: Path, authority_id: str, as_of: date) -> AuthorityResolutionNote:
    resolution = resolve_version(legal_db_path, authority_id, as_of)
    return AuthorityResolutionNote(
        authority_id=authority_id,
        state=resolution.state.value,
        version_id=resolution.version.version_id if resolution.version else None,
        candidate_version_ids=resolution.candidate_version_ids,
        message=resolution.message,
    )


def _applicable(
    legal_db_path: Path,
    evidence: LegalEvidenceRecord,
    as_of: date,
    resolution_cache: dict[str, AuthorityResolutionNote],
) -> bool:
    note = resolution_cache.get(evidence.authority.authority_id)
    if note is None:
        note = _resolution_note(legal_db_path, evidence.authority.authority_id, as_of)
        resolution_cache[evidence.authority.authority_id] = note
    return note.state == VersionResolutionState.RESOLVED.value and note.version_id == evidence.version.version_id


def retrieve_legal_evidence(
    legal_db_path: Path,
    index_path: Path,
    request: RetrievalRequest,
    *,
    embedding_provider: EmbeddingProvider | None = None,
) -> RetrievalResponse:
    legal_summary = get_summary(legal_db_path)
    if not legal_summary.ready:
        raise FileNotFoundError("Legal database has not been built yet.")

    index_summary = get_retrieval_index_summary(index_path, legal_db_path)
    rankings: dict[RetrievalChannel, list[tuple[str, float | None]]] = {}
    warnings: list[str] = []
    resolution_cache: dict[str, AuthorityResolutionNote] = {}
    explicit_target_missing = False
    allowed_authorities = set(request.authority_ids_allowlist) or None
    allowed_evidence_ids = _allowed_evidence_ids(legal_db_path, allowed_authorities)

    exact_ids: list[str] = []
    if request.legal_evidence_id_hint:
        try:
            evidence = get_evidence(legal_db_path, request.legal_evidence_id_hint)
            if allowed_authorities and evidence.authority.authority_id not in allowed_authorities:
                explicit_target_missing = True
                warnings.append("The supplied Legal Evidence ID is outside the eligible Authority scope for this retrieval.")
            elif _applicable(legal_db_path, evidence, request.as_of, resolution_cache):
                exact_ids.append(evidence.article.legal_evidence_id)
        except FileNotFoundError:
            explicit_target_missing = True
            warnings.append("The supplied Legal Evidence ID does not exist in the local corpus.")

    if request.authority_id_hint and allowed_authorities and request.authority_id_hint not in allowed_authorities:
        explicit_target_missing = True
        warnings.append("The supplied Authority hint is outside the eligible Authority scope for this retrieval.")

    authority_id = _recognize_authority_id(legal_db_path, request)
    article_ordinal = _query_article_ordinal(request)
    if authority_id and article_ordinal:
        note = resolution_cache.get(authority_id) or _resolution_note(legal_db_path, authority_id, request.as_of)
        resolution_cache[authority_id] = note
        if note.state == VersionResolutionState.RESOLVED.value and note.version_id:
            exact_id = _article_by_ordinal(legal_db_path, authority_id, note.version_id, article_ordinal)
            if exact_id:
                exact_ids.append(exact_id)
            else:
                explicit_target_missing = True
                warnings.append(
                    "The requested article is not present in the locally stored version; partial corpus coverage may be the cause."
                )
    if exact_ids:
        rankings[RetrievalChannel.EXACT] = [(item, None) for item in dict.fromkeys(exact_ids)]

    if index_summary.ready and index_summary.lexical_ready:
        lexical = _lexical_hits(
            index_path,
            request.query,
            max(request.top_k * 6, 30),
            allowed_authorities,
        )
        rankings[RetrievalChannel.LEXICAL] = [(evidence_id, score) for evidence_id, score in lexical]
    elif not exact_ids:
        warnings.append("Retrieval index is not ready; only deterministic exact lookup is available.")

    semantic_provider_name = None
    semantic_model_name = None
    if request.use_semantic and index_summary.ready and index_summary.semantic_ready:
        try:
            provider = embedding_provider or BgeSmallZhProvider()
            if (
                provider.provider_name != index_summary.semantic_provider
                or provider.model_name != index_summary.semantic_model
                or provider.dimension != index_summary.semantic_dimension
            ):
                warnings.append("Semantic index/provider metadata do not match; semantic channel was skipped.")
            else:
                semantic = _semantic_hits(
                    index_path,
                    request.query,
                    max(request.top_k * 6, 30),
                    provider,
                    allowed_evidence_ids,
                )
                rankings[RetrievalChannel.SEMANTIC] = [(evidence_id, score) for evidence_id, score in semantic]
                semantic_provider_name = provider.provider_name
                semantic_model_name = provider.model_name
        except EmbeddingProviderUnavailable as exc:
            warnings.append(str(exc))
    elif request.use_semantic and index_summary.ready and not index_summary.semantic_ready:
        warnings.append("Semantic index is not built; exact and lexical retrieval remain available.")

    contributions: dict[str, list[ChannelScore]] = {}
    exact_set = {item for item, _ in rankings.get(RetrievalChannel.EXACT, [])}
    for channel, hits in rankings.items():
        weight = CHANNEL_WEIGHTS[channel]
        for rank, (evidence_id, raw_score) in enumerate(hits, start=1):
            contribution = weight / (RRF_K + rank)
            contributions.setdefault(evidence_id, []).append(
                ChannelScore(
                    channel=channel,
                    rank=rank,
                    raw_score=raw_score,
                    contribution=contribution,
                )
            )

    candidates: list[RetrievalCandidate] = []
    for evidence_id, channel_scores in contributions.items():
        try:
            evidence = get_evidence(legal_db_path, evidence_id)
        except FileNotFoundError:
            warnings.append(f"Index references missing legal evidence {evidence_id}; rebuild the retrieval index.")
            continue
        if allowed_authorities and evidence.authority.authority_id not in allowed_authorities:
            continue
        if not _applicable(legal_db_path, evidence, request.as_of, resolution_cache):
            continue
        fused = sum(item.contribution for item in channel_scores)
        text = evidence.article.text
        candidates.append(
            RetrievalCandidate(
                legal_evidence_id=evidence.article.legal_evidence_id,
                authority_id=evidence.authority.authority_id,
                authority_title=evidence.authority.title,
                version_id=evidence.version.version_id,
                article_id=evidence.article.article_id,
                article_token=evidence.article.article_token,
                article_text=text,
                coverage_type=evidence.version.coverage_type.value,
                effective_date=evidence.version.effective_date,
                end_date_exclusive=evidence.version.end_date_exclusive,
                exact_hit=evidence_id in exact_set,
                fused_score=fused,
                channels=sorted(channel_scores, key=lambda item: item.channel.value),
                matched_snippet=text[:260] + ("…" if len(text) > 260 else ""),
            )
        )

    candidates.sort(key=lambda item: (not item.exact_hit, -item.fused_score, item.legal_evidence_id))
    candidates = candidates[: request.top_k]

    resolution_notes = sorted(resolution_cache.values(), key=lambda item: item.authority_id)
    if authority_id:
        hinted = resolution_cache.get(authority_id)
        if hinted and hinted.state == VersionResolutionState.AMBIGUOUS.value:
            state = RetrievalState.VERSION_AMBIGUOUS
        elif hinted and hinted.state == VersionResolutionState.NO_APPLICABLE_VERSION.value:
            state = RetrievalState.NO_APPLICABLE_VERSION
        elif explicit_target_missing:
            state = RetrievalState.INSUFFICIENT_CORPUS
        elif not candidates and legal_summary.excerpt_version_count > 0:
            state = RetrievalState.INSUFFICIENT_CORPUS
        elif candidates and legal_summary.excerpt_version_count > 0:
            state = RetrievalState.PARTIAL_COVERAGE
        elif candidates:
            state = RetrievalState.OK
        else:
            state = RetrievalState.INSUFFICIENT_CORPUS
    elif explicit_target_missing:
        state = RetrievalState.INSUFFICIENT_CORPUS
    elif not candidates and not index_summary.ready:
        state = RetrievalState.INDEX_NOT_READY
    elif not candidates and legal_summary.excerpt_version_count > 0:
        state = RetrievalState.INSUFFICIENT_CORPUS
    elif candidates and legal_summary.excerpt_version_count > 0:
        state = RetrievalState.PARTIAL_COVERAGE
    elif candidates:
        state = RetrievalState.OK
    else:
        state = RetrievalState.INSUFFICIENT_CORPUS

    if legal_summary.excerpt_version_count > 0:
        warnings.append(
            "The local corpus contains CURATED_EXCERPT versions. No-hit results cannot be interpreted as absence of a legal rule."
        )
    if allowed_authorities and not candidates:
        warnings.append("No applicable candidate matched the eligible Authority scope for this retrieval.")

    return RetrievalResponse(
        query=request.query,
        as_of=request.as_of,
        state=state,
        channels_executed=list(rankings.keys()),
        candidates=candidates,
        authority_resolution=resolution_notes,
        warnings=list(dict.fromkeys(warnings)),
        semantic_provider=semantic_provider_name,
        semantic_model=semantic_model_name,
        lexical_index_version=LEXICAL_INDEX_VERSION if index_summary.lexical_ready else None,
    )
