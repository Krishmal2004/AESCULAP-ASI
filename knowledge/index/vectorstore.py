"""Vector stores: a pure-Python in-memory store (JSON-persisted) and a Chroma adapter."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Protocol

from knowledge.config import Config
from knowledge.models import Chunk, Hit


class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...

    def query(
        self, embedding: list[float], k: int = 5, where: dict[str, str] | None = None
    ) -> list[Hit]: ...

    def delete_doc(self, doc_id: str) -> None: ...

    def count(self) -> int: ...

    def all_chunks(self) -> list[Chunk]: ...

    def persist(self) -> None: ...


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class InMemoryStore:
    """Brute-force cosine search. Fine for tests and small corpora (<~50k chunks)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._items: dict[str, tuple[Chunk, list[float]]] = {}
        if path is not None and self._file.exists():
            self._load()

    @property
    def _file(self) -> Path:
        assert self.path is not None
        return self.path / "store.jsonl"

    def _load(self) -> None:
        for line in self._file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                chunk = Chunk.from_dict(row["chunk"])
                self._items[chunk.chunk_id] = (chunk, row["embedding"])

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings length mismatch")
        for chunk, emb in zip(chunks, embeddings, strict=True):
            self._items[chunk.chunk_id] = (chunk, emb)

    def query(
        self, embedding: list[float], k: int = 5, where: dict[str, str] | None = None
    ) -> list[Hit]:
        hits = [
            Hit(chunk, _cosine(embedding, emb))
            for chunk, emb in self._items.values()
            if not where or all(chunk.metadata.get(key) == val for key, val in where.items())
        ]
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]

    def delete_doc(self, doc_id: str) -> None:
        for cid in [c for c, (chunk, _) in self._items.items() if chunk.doc_id == doc_id]:
            del self._items[cid]

    def count(self) -> int:
        return len(self._items)

    def all_chunks(self) -> list[Chunk]:
        return [chunk for chunk, _ in self._items.values()]

    def persist(self) -> None:
        if self.path is None:
            return
        self.path.mkdir(parents=True, exist_ok=True)
        lines = (
            json.dumps({"chunk": chunk.to_dict(), "embedding": emb}, ensure_ascii=False)
            for chunk, emb in self._items.values()
        )
        self._file.write_text("\n".join(lines) + "\n", encoding="utf-8")


class ChromaStore:
    """Persistent store backed by Chroma (optional dependency)."""

    def __init__(self, path: Path, collection: str) -> None:
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "chromadb not installed; run: pip install -r knowledge/requirements-optional.txt"
            ) from exc
        path.mkdir(parents=True, exist_ok=True)
        client: Any = chromadb.PersistentClient(path=str(path))
        self._col: Any = client.get_or_create_collection(
            collection, metadata={"hnsw:space": "cosine"}
        )

    @staticmethod
    def _where(where: dict[str, str] | None) -> dict[str, Any] | None:
        if not where:
            return None
        if len(where) == 1:
            return dict(where)
        return {"$and": [{k: v} for k, v in where.items()]}

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        self._col.upsert(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=embeddings,
            metadatas=[{**c.metadata, "doc_id": c.doc_id, "chunk_index": c.index} for c in chunks],
        )

    @staticmethod
    def _to_chunk(cid: str, text: str, meta: dict[str, Any]) -> Chunk:
        meta = dict(meta)
        doc_id = str(meta.pop("doc_id"))
        index = int(meta.pop("chunk_index"))
        return Chunk(cid, doc_id, index, text, {k: str(v) for k, v in meta.items()})

    def query(
        self, embedding: list[float], k: int = 5, where: dict[str, str] | None = None
    ) -> list[Hit]:
        res = self._col.query(query_embeddings=[embedding], n_results=k, where=self._where(where))
        hits: list[Hit] = []
        for cid, text, meta, dist in zip(
            res["ids"][0],
            res["documents"][0],
            res["metadatas"][0],
            res["distances"][0],
            strict=True,
        ):
            hits.append(Hit(self._to_chunk(cid, text, meta), 1.0 - float(dist)))
        return hits

    def delete_doc(self, doc_id: str) -> None:
        self._col.delete(where={"doc_id": doc_id})

    def count(self) -> int:
        return int(self._col.count())

    def all_chunks(self) -> list[Chunk]:
        res = self._col.get()
        return [
            self._to_chunk(cid, text, meta)
            for cid, text, meta in zip(res["ids"], res["documents"], res["metadatas"], strict=True)
        ]

    def persist(self) -> None:  # Chroma persists on write.
        return None


def make_store(config: Config) -> VectorStore:
    if config.store == "memory":
        return InMemoryStore(config.index_dir)
    if config.store == "chroma":
        return ChromaStore(config.index_dir / "chroma", config.collection)
    raise ValueError(f"unknown store {config.store!r}")
