"""Runtime configuration (env-overridable)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    data_dir: Path = Path("knowledge/data")
    sources_file: Path = Path("knowledge/sources.yaml")
    lexicon_file: Path = Path("knowledge/graph/lexicon.yaml")
    chunk_words: int = 220
    overlap_words: int = 40
    embedder: str = "hashing"  # "hashing" | "sentence-transformers"
    store: str = "memory"  # "memory" | "chroma"
    collection: str = "aesculap"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def manifest_path(self) -> Path:
        return self.data_dir / "manifest.json"

    @property
    def graph_path(self) -> Path:
        return self.data_dir / "graph.json"

    @classmethod
    def from_env(cls) -> Config:
        defaults = cls()
        return cls(
            data_dir=Path(os.environ.get("AESCULAP_DATA_DIR", str(defaults.data_dir))),
            sources_file=Path(os.environ.get("AESCULAP_SOURCES", str(defaults.sources_file))),
            lexicon_file=Path(os.environ.get("AESCULAP_LEXICON", str(defaults.lexicon_file))),
            embedder=os.environ.get("AESCULAP_EMBEDDER", defaults.embedder),
            store=os.environ.get("AESCULAP_STORE", defaults.store),
        )
