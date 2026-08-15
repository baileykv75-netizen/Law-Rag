from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod


class EmbeddingProviderUnavailable(RuntimeError):
    pass


class EmbeddingProvider(ABC):
    provider_name: str
    model_name: str
    dimension: int

    @abstractmethod
    def encode(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        raise NotImplementedError


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic fake provider for tests only; not a production semantic model."""

    provider_name = "deterministic-test"
    model_name = "sha256-chargram-v1"

    def __init__(self, dimension: int = 32) -> None:
        self.dimension = dimension

    def encode(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimension
            compact = "".join(text.lower().split())
            grams = [compact[i : i + 2] for i in range(max(1, len(compact) - 1))] or [compact]
            for gram in grams:
                digest = hashlib.sha256(gram.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimension
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vector[index] += sign
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            results.append([value / norm for value in vector])
        return results


class BgeSmallZhProvider(EmbeddingProvider):
    provider_name = "sentence-transformers"
    model_name = "BAAI/bge-small-zh-v1.5"
    dimension = 512
    query_instruction = "为这个句子生成表示以用于检索相关文章："

    def __init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingProviderUnavailable(
                "Semantic retrieval dependencies are not installed. Run setup-rag-semantic-cpu.bat first."
            ) from exc
        try:
            self._model = SentenceTransformer(self.model_name, device="cpu")
        except Exception as exc:
            raise EmbeddingProviderUnavailable(f"Unable to load local embedding model {self.model_name}: {exc}") from exc

    def encode(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        prepared = [f"{self.query_instruction}{text}" if is_query else text for text in texts]
        vectors = self._model.encode(prepared, normalize_embeddings=True, show_progress_bar=False)
        return [list(map(float, row)) for row in vectors]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding dimensions do not match.")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
