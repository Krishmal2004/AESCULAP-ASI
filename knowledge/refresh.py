"""Incremental ingest/refresh pipeline.

fetch -> clean -> hash -> (re)chunk -> embed -> upsert -> manifest -> graph.
Unchanged documents are skipped, changed ones are re-indexed, and sources whose last
successful run is older than ``max_age_days`` are reported as stale.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from knowledge.config import Config
from knowledge.graph.builder import build_graph, load_lexicon, save_graph
from knowledge.index.embeddings import Embedder, get_embedder
from knowledge.index.vectorstore import VectorStore, make_store
from knowledge.ingest import get_ingestor
from knowledge.ingest.http import Fetcher
from knowledge.process.chunk import chunk_document
from knowledge.process.clean import clean_document
from knowledge.sources import Source, load_sources


@dataclass
class Manifest:
    embedder: str = ""
    dim: int = 0
    docs: dict[str, dict[str, Any]] = field(default_factory=dict)
    sources: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Manifest:
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            raw.get("embedder", ""), raw.get("dim", 0), raw.get("docs", {}), raw.get("sources", {})
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "embedder": self.embedder,
            "dim": self.dim,
            "docs": self.docs,
            "sources": self.sources,
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


@dataclass
class RefreshReport:
    source_id: str
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_empty: int = 0
    errors: list[str] = field(default_factory=list)
    blocked: str | None = None

    def summary(self) -> str:
        if self.blocked:
            return f"{self.source_id}: SKIPPED ({self.blocked})"
        text = (
            f"{self.source_id}: new={self.new} updated={self.updated} "
            f"unchanged={self.unchanged} empty={self.skipped_empty}"
        )
        return text + (f" ERRORS={len(self.errors)}" if self.errors else "")


def check_embedder_compat(manifest: Manifest, embedder: Embedder) -> None:
    if manifest.docs and (manifest.embedder, manifest.dim) != (embedder.name, embedder.dim):
        raise RuntimeError(
            f"index was built with embedder={manifest.embedder!r} dim={manifest.dim}, "
            f"but current is {embedder.name!r} dim={embedder.dim}. "
            "Delete the index (knowledge/data) and re-ingest to switch embedders."
        )


def refresh_source(
    source: Source,
    *,
    config: Config,
    store: VectorStore,
    embedder: Embedder,
    manifest: Manifest,
    fetch: Fetcher | None = None,
    now: datetime | None = None,
) -> RefreshReport:
    now = now or datetime.now(UTC)
    report = RefreshReport(source.id)
    if (reason := source.blocker()) is not None:
        report.blocked = reason
        return report
    try:
        for raw_doc in get_ingestor(source, fetch).documents():
            doc = clean_document(raw_doc)
            if not doc.text:
                report.skipped_empty += 1
                continue
            entry = manifest.docs.get(doc.doc_id)
            if entry and entry["hash"] == doc.content_hash:
                report.unchanged += 1
                continue
            chunks = chunk_document(doc, config.chunk_words, config.overlap_words)
            if entry:
                store.delete_doc(doc.doc_id)
            store.upsert(chunks, embedder.embed([c.text for c in chunks]))
            manifest.docs[doc.doc_id] = {
                "hash": doc.content_hash,
                "source": source.id,
                "chunks": len(chunks),
                "indexed_at": now.isoformat(),
            }
            if entry:
                report.updated += 1
            else:
                report.new += 1
    except Exception as exc:  # network/parse failure must not abort other sources
        report.errors.append(f"{type(exc).__name__}: {exc}")
    else:
        manifest.sources[source.id] = {"last_run": now.isoformat()}
    return report


def rebuild_graph(store: VectorStore, config: Config) -> int:
    """Rebuild the co-mention graph from all indexed chunks. Returns the edge count."""
    graph = build_graph(load_lexicon(config.lexicon_file), store.all_chunks())
    save_graph(graph, config.graph_path)
    return int(graph.number_of_edges())


def run(
    config: Config,
    source_ids: list[str] | None = None,
    *,
    fetch: Fetcher | None = None,
    now: datetime | None = None,
    with_graph: bool = True,
) -> list[RefreshReport]:
    """Ingest the requested sources, or every ingestible source when none are named."""
    sources = load_sources(config.sources_file)
    by_id = {s.id: s for s in sources}
    if source_ids:
        unknown = [i for i in source_ids if i not in by_id]
        if unknown:
            raise KeyError(f"unknown source(s): {', '.join(unknown)}")
        selected = [by_id[i] for i in source_ids]
    else:
        selected = [s for s in sources if s.ingestible]

    embedder = get_embedder(config.embedder)
    manifest = Manifest.load(config.manifest_path)
    check_embedder_compat(manifest, embedder)
    manifest.embedder, manifest.dim = embedder.name, embedder.dim
    store = make_store(config)

    reports = [
        refresh_source(
            s,
            config=config,
            store=store,
            embedder=embedder,
            manifest=manifest,
            fetch=fetch,
            now=now,
        )
        for s in selected
    ]
    store.persist()
    manifest.save(config.manifest_path)
    if with_graph and store.count():
        rebuild_graph(store, config)
    return reports


def stale_sources(config: Config, now: datetime | None = None) -> list[str]:
    """Ingestible sources never run, or last run longer ago than max_age_days."""
    now = now or datetime.now(UTC)
    manifest = Manifest.load(config.manifest_path)
    stale: list[str] = []
    for src in load_sources(config.sources_file):
        if not src.ingestible or src.max_age_days is None:
            continue
        last = manifest.sources.get(src.id, {}).get("last_run")
        if last is None or now - datetime.fromisoformat(last) > timedelta(days=src.max_age_days):
            stale.append(src.id)
    return stale
