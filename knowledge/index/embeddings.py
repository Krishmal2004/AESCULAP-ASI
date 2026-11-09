"""Embedders.

``HashingEmbedder`` is a dependency-free, deterministic LEXICAL baseline for tests and
offline use. It has no semantic understanding. For real retrieval quality use
``sentence-transformers`` (see knowledge/requirements-optional.txt); the model choice
is a Phase 3 decision and should be benchmarked on medical retrieval.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Any, Protocol

_TOKEN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    name: str

    @property
    def dim(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Signed feature hashing of unigrams and bigrams, L2-normalised."""

    name = "hashing"

    def __init__(self, dim: int = 512) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def _embed_one(self, text: str) -> list[float]:
        tokens = _TOKEN.findall(text.lower())
        features = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        vec = [0.0] * self._dim
        for feat in features:
            h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
            vec[h % self._dim] += 1.0 if (h >> 63) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]


class SentenceTransformerEmbedder:
    name = "sentence-transformers"

    def __init__(self, model_name: str | None = None) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "sentence-transformers not installed; "
                "run: pip install -r knowledge/requirements-optional.txt"
            ) from exc
        self.model_name = model_name or os.environ.get(
            "AESCULAP_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )
        self._model: Any = SentenceTransformer(self.model_name)

    @property
    def dim(self) -> int:
        return int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [[float(x) for x in row] for row in vectors]


def get_embedder(name: str) -> Embedder:
    if name == "hashing":
        return HashingEmbedder()
    if name == "sentence-transformers":
        return SentenceTransformerEmbedder()
    raise ValueError(f"unknown embedder {name!r}")
