# Stage 7 Legal Retrieval

Law-Rag Stage 7 retrieves versioned Legal Evidence IDs without asking a generative model to judge contract risk.

## Runtime flow

```text
query + explicit as_of
  -> resolve applicable legal versions
  -> deterministic exact citation lookup
  -> SQLite FTS5 trigram / BM25 lexical retrieval
  -> optional local BGE semantic retrieval
  -> weighted reciprocal-rank fusion
  -> Legal Evidence IDs + channel provenance + coverage warnings
```

Exact citation hits remain pinned ahead of probabilistic retrieval candidates. Version ambiguity and no-applicable-version states are not hidden by ranking.

## Build the local index

First build the Stage 6 legal database:

```text
rebuild-legal-seed.bat
```

Then build exact/lexical retrieval:

```text
build-retrieval-index.bat
```

This creates the ignored derivative index:

```text
runtime/legal/retrieval.db
```

The lexical index uses SQLite FTS5 with the trigram tokenizer and `bm25()` ranking. The index records a fingerprint of canonical Stage 6 legal evidence; if `legal.db` changes, the UI/API reports the retrieval index as stale until rebuilt.

## Optional local semantic retrieval

Install the optional CPU semantic runtime:

```text
setup-rag-semantic-cpu.bat
```

Then build vectors:

```text
build-retrieval-index-semantic.bat
```

Current initial local model:

```text
BAAI/bge-small-zh-v1.5
```

The embedding provider is replaceable. Model/provider/version/dimension are stored in index metadata, and semantic retrieval is skipped rather than silently mixing incompatible vectors.

Exact and lexical retrieval do not require sentence-transformers or the BGE model.

## Real semantic smoke test

After installing the optional semantic runtime, run:

```bat
cd backend
set PYTHONPATH=.
set LAW_RAG_RAG_SEMANTIC_SMOKE=1
..\.venv\Scripts\python.exe -m pytest -q -m rag_semantic_smoke
```

The smoke test imports the verified public seed, builds real BGE vectors locally, runs a Chinese liquidated-damages query, and verifies that semantic retrieval returns the expected Civil Code evidence among the top candidates.

GitHub Actions also has an opt-in Windows job triggered only by a push commit message containing `verify RAG semantic`; normal CI does not repeatedly download the semantic model.

## Retrieval API

```text
GET  /api/legal/retrieval/summary
POST /api/legal/retrieve
```

Example request:

```json
{
  "query": "民法典第五百八十五条违约金",
  "as_of": "2026-08-15",
  "top_k": 8,
  "use_semantic": false
}
```

Each result keeps:

- Legal Evidence ID;
- authority/version/article identity;
- effective interval and coverage type;
- exact-hit state;
- per-channel rank/raw score/fusion contribution;
- final fused score;
- source text/snippet;
- visible retrieval warnings.

## Coverage semantics

The current checked-in seed uses `CURATED_EXCERPT` coverage. Therefore:

- a hit may be shown as evidence from the stored excerpt;
- a no-hit is not proof that no legal rule exists;
- an explicitly requested but un-stored article returns `INSUFFICIENT_CORPUS` even if lexical search finds nearby similar articles;
- retrieval state is not a legal conclusion.

## Public benchmark

The small deterministic benchmark lives at:

```text
legal_data/fixtures/retrieval_benchmark.json
```

Standard backend CI rebuilds the legal store/index and requires the lexical baseline to meet:

```text
Recall@5 >= 0.90
MRR      >= 0.80
```

This fixture measures retrieval mechanics only over the tiny public seed. It is not a claim about production legal-corpus recall; a later private expert benchmark must test realistic contracts and a much broader corpus.
