"""Retrieval with citation metadata, shaped for the system prompt's ``retrieved_sources``."""

from __future__ import annotations

from typing import Any

from knowledge.config import Config
from knowledge.index.embeddings import get_embedder
from knowledge.index.vectorstore import make_store
from knowledge.refresh import Manifest, check_embedder_compat


def retrieve(
    query: str,
    k: int = 5,
    config: Config | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    """Top-k passages. Each item has the fields character/system_prompt.md expects.

    ``id`` is ``S1``, ``S2``, ... so the model can cite ``[S1]``.
    """
    config = config or Config.from_env()
    embedder = get_embedder(config.embedder)
    check_embedder_compat(Manifest.load(config.manifest_path), embedder)
    store = make_store(config)
    where = {"source": source} if source else None
    hits = store.query(embedder.embed([query])[0], k=k, where=where)
    return [
        {
            "id": f"S{i}",
            "chunk_id": h.chunk.chunk_id,
            "doc_id": h.chunk.doc_id,
            "source": h.chunk.metadata.get("source", ""),
            "title": h.chunk.metadata.get("title", ""),
            "url": h.chunk.metadata.get("url", ""),
            "date": h.chunk.metadata.get("date", ""),
            "evidence_level": h.chunk.metadata.get("evidence_level", "unspecified"),
            "license": h.chunk.metadata.get("license", ""),
            "score": round(h.score, 4),
            "text": h.chunk.text,
        }
        for i, h in enumerate(hits, start=1)
    ]


def format_for_prompt(results: list[dict[str, Any]]) -> str:
    """Render results as text for the ``{{retrieved_sources}}`` placeholder."""
    blocks = [
        f"[{r['id']}] {r['title']} | source={r['source']} | date={r['date'] or 'n/a'} | "
        f"evidence={r['evidence_level']} | {r['url']}\n{r['text']}"
        for r in results
    ]
    return "\n\n".join(blocks) if blocks else "(no supporting evidence found)"
