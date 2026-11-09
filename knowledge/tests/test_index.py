from __future__ import annotations

from pathlib import Path

from knowledge.index.embeddings import HashingEmbedder, get_embedder
from knowledge.index.vectorstore import InMemoryStore
from knowledge.models import Chunk


def test_hashing_embedder_is_deterministic_and_normalised() -> None:
    emb = HashingEmbedder(dim=128)
    a1, a2 = emb.embed(["alpha beta gamma"])[0], emb.embed(["alpha beta gamma"])[0]
    assert a1 == a2
    assert abs(sum(x * x for x in a1) - 1.0) < 1e-9
    assert len(a1) == emb.dim == 128


def test_similar_text_scores_higher_than_unrelated() -> None:
    emb = HashingEmbedder()
    q, close, far = emb.embed(
        ["renal dosing adjustment", "adjustment of dosing in renal impairment", "football scores"]
    )
    dot = lambda a, b: sum(x * y for x, y in zip(a, b, strict=True))  # noqa: E731
    assert dot(q, close) > dot(q, far)


def test_unknown_embedder_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        get_embedder("nope")


def _store_with_chunks() -> tuple[InMemoryStore, HashingEmbedder]:
    emb = HashingEmbedder()
    store = InMemoryStore()
    chunks = [
        Chunk("a#0", "a", 0, "kidney function and drug dosing", {"source": "s1"}),
        Chunk("b#0", "b", 0, "football match results", {"source": "s2"}),
    ]
    store.upsert(chunks, emb.embed([c.text for c in chunks]))
    return store, emb


def test_query_ranks_relevant_chunk_first() -> None:
    store, emb = _store_with_chunks()
    hits = store.query(emb.embed(["drug dosing kidney"])[0], k=2)
    assert hits[0].chunk.chunk_id == "a#0"


def test_query_filters_by_metadata() -> None:
    store, emb = _store_with_chunks()
    hits = store.query(emb.embed(["anything"])[0], k=5, where={"source": "s2"})
    assert [h.chunk.chunk_id for h in hits] == ["b#0"]


def test_delete_doc_removes_all_its_chunks() -> None:
    store, _ = _store_with_chunks()
    store.delete_doc("a")
    assert store.count() == 1


def test_persistence_roundtrip(tmp_path: Path) -> None:
    emb = HashingEmbedder()
    store = InMemoryStore(tmp_path)
    chunk = Chunk("a#0", "a", 0, "persisted text", {"source": "s"})
    store.upsert([chunk], emb.embed([chunk.text]))
    store.persist()
    reloaded = InMemoryStore(tmp_path)
    assert reloaded.count() == 1
    assert reloaded.all_chunks()[0].text == "persisted text"
