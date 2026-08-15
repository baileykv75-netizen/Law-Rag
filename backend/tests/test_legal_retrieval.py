from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app.legal.embeddings import EmbeddingProvider
from app.legal.importer import import_manifest
from app.legal.retrieval import (
    build_retrieval_index,
    get_retrieval_index_summary,
    retrieve_legal_evidence,
)
from app.legal.retrieval_models import RetrievalChannel, RetrievalRequest, RetrievalState
from app.main import app

client = TestClient(app)


class KeywordEmbeddingProvider(EmbeddingProvider):
    provider_name = "test-keyword"
    model_name = "test-keyword-v1"
    dimension = 3

    def encode(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        results = []
        for text in texts:
            if "违约金" in text:
                results.append([1.0, 0.0, 0.0])
            elif "定金" in text:
                results.append([0.0, 1.0, 0.0])
            else:
                results.append([0.0, 0.0, 1.0])
        return results


def _seed(tmp_path: Path, *, semantic: bool = False) -> tuple[Path, Path]:
    repo_root = Path(__file__).resolve().parents[2]
    manifest = repo_root / "legal_data" / "seed" / "manifest.json"
    legal_db = tmp_path / "legal.db"
    index_db = tmp_path / "retrieval.db"
    import_manifest(manifest, legal_db, rebuild=True)
    build_retrieval_index(
        legal_db,
        index_db,
        semantic_provider=KeywordEmbeddingProvider() if semantic else None,
    )
    return legal_db, index_db


def test_fts5_trigram_index_rebuilds_from_canonical_legal_store(tmp_path: Path) -> None:
    legal_db, index_db = _seed(tmp_path)
    summary = get_retrieval_index_summary(index_db, legal_db)
    assert summary.ready is True
    assert summary.lexical_ready is True
    assert summary.lexical_tokenizer == "fts5-trigram"
    assert summary.article_count == 15
    assert summary.semantic_ready is False


def test_exact_article_citation_is_pinned_first(tmp_path: Path) -> None:
    legal_db, index_db = _seed(tmp_path)
    response = retrieve_legal_evidence(
        legal_db,
        index_db,
        RetrievalRequest(
            query="根据民法典第五百八十五条审查违约金约定",
            as_of=date(2026, 8, 15),
            top_k=5,
            use_semantic=False,
        ),
    )
    assert response.candidates
    assert response.candidates[0].legal_evidence_id == "legal:prc-civil-code:effective-2021-01-01:article-585"
    assert response.candidates[0].exact_hit is True
    assert any(item.channel == RetrievalChannel.EXACT for item in response.candidates[0].channels)
    assert response.state == RetrievalState.PARTIAL_COVERAGE


def test_lexical_retrieval_finds_contract_article_without_exact_hint(tmp_path: Path) -> None:
    legal_db, index_db = _seed(tmp_path)
    response = retrieve_legal_evidence(
        legal_db,
        index_db,
        RetrievalRequest(
            query="约定的违约金过分高于造成的损失可以适当减少",
            as_of=date(2026, 8, 15),
            top_k=5,
            use_semantic=False,
        ),
    )
    ids = [item.legal_evidence_id for item in response.candidates]
    assert "legal:prc-civil-code:effective-2021-01-01:article-585" in ids
    target = next(item for item in response.candidates if item.legal_evidence_id.endswith(":article-585"))
    assert any(item.channel == RetrievalChannel.LEXICAL for item in target.channels)


def test_semantic_channel_uses_provider_metadata_and_fuses_candidates(tmp_path: Path) -> None:
    legal_db, index_db = _seed(tmp_path, semantic=True)
    provider = KeywordEmbeddingProvider()
    response = retrieve_legal_evidence(
        legal_db,
        index_db,
        RetrievalRequest(
            query="违约金过高如何调整",
            as_of=date(2026, 8, 15),
            top_k=5,
            use_semantic=True,
        ),
        embedding_provider=provider,
    )
    assert RetrievalChannel.SEMANTIC in response.channels_executed
    assert response.semantic_provider == provider.provider_name
    assert response.semantic_model == provider.model_name
    target = next(item for item in response.candidates if item.legal_evidence_id.endswith(":article-585"))
    assert any(item.channel == RetrievalChannel.SEMANTIC for item in target.channels)


def test_missing_article_in_curated_excerpt_is_not_negative_legal_claim(tmp_path: Path) -> None:
    legal_db, index_db = _seed(tmp_path)
    response = retrieve_legal_evidence(
        legal_db,
        index_db,
        RetrievalRequest(
            query="民法典第九百九十九条",
            as_of=date(2026, 8, 15),
            authority_id_hint="prc-civil-code",
            article_token_hint="第九百九十九条",
            top_k=3,
            use_semantic=False,
        ),
    )
    assert response.state == RetrievalState.INSUFFICIENT_CORPUS
    assert any("partial corpus" in warning.lower() or "CURATED_EXCERPT" in warning for warning in response.warnings)


def test_as_of_before_effective_date_blocks_exact_applicability(tmp_path: Path) -> None:
    legal_db, index_db = _seed(tmp_path)
    response = retrieve_legal_evidence(
        legal_db,
        index_db,
        RetrievalRequest(
            query="民法典第五百八十五条",
            as_of=date(2020, 12, 31),
            authority_id_hint="prc-civil-code",
            article_token_hint="第五百八十五条",
            use_semantic=False,
        ),
    )
    assert response.state == RetrievalState.NO_APPLICABLE_VERSION
    assert not response.candidates
    assert response.authority_resolution[0].state == "NO_APPLICABLE_VERSION"


def test_exact_lookup_still_works_when_retrieval_index_is_absent(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    manifest = repo_root / "legal_data" / "seed" / "manifest.json"
    legal_db = tmp_path / "legal.db"
    import_manifest(manifest, legal_db, rebuild=True)
    response = retrieve_legal_evidence(
        legal_db,
        tmp_path / "missing-retrieval.db",
        RetrievalRequest(
            query="民法典第五百八十五条",
            as_of=date(2026, 8, 15),
            authority_id_hint="prc-civil-code",
            article_token_hint="第五百八十五条",
            use_semantic=False,
        ),
    )
    assert response.candidates[0].exact_hit is True
    assert response.channels_executed == [RetrievalChannel.EXACT]


def test_retrieval_api_summary_and_query(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    repo_root = Path(__file__).resolve().parents[2]
    manifest = repo_root / "legal_data" / "seed" / "manifest.json"
    legal_db = tmp_path / "legal" / "legal.db"
    index_db = tmp_path / "legal" / "retrieval.db"
    import_manifest(manifest, legal_db, rebuild=True)
    build_retrieval_index(legal_db, index_db)

    summary = client.get("/api/legal/retrieval/summary")
    assert summary.status_code == 200
    assert summary.json()["lexical_ready"] is True
    assert summary.json()["article_count"] == 15

    response = client.post(
        "/api/legal/retrieve",
        json={
            "query": "民法典第五百八十五条违约金",
            "as_of": "2026-08-15",
            "top_k": 5,
            "use_semantic": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["candidates"][0]["legal_evidence_id"].endswith(":article-585")
    assert "EXACT" in body["channels_executed"]
