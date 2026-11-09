"""Core data models shared across the pipeline."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Document:
    """One source document (paper abstract, drug label, guideline, ...)."""

    doc_id: str
    source: str
    title: str
    text: str
    url: str = ""
    date: str = ""
    evidence_level: str = "unspecified"
    license: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        """Stable hash of everything that should trigger a re-index when it changes."""
        payload = json.dumps(
            {
                "title": self.title,
                "text": self.text,
                "url": self.url,
                "date": self.date,
                "evidence_level": self.evidence_level,
                "license": self.license,
                "metadata": self.metadata,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Chunk:
    """A retrievable passage. Metadata always carries provenance for citations."""

    chunk_id: str
    doc_id: str
    index: int
    text: str
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "index": self.index,
            "text": self.text,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Chunk:
        return cls(
            chunk_id=data["chunk_id"],
            doc_id=data["doc_id"],
            index=int(data["index"]),
            text=data["text"],
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class Hit:
    """A search result."""

    chunk: Chunk
    score: float
