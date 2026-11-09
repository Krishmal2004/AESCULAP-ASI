"""Ingest manually downloaded guidelines / textbooks from a folder.

Files may start with YAML front matter::

    ---
    title: Some guideline
    date: 2024-05-01
    url: https://example.org/guideline
    evidence_level: guideline
    license: CC BY-NC-SA 3.0 IGO
    ---
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

from knowledge.models import Document
from knowledge.sources import Source

_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_EXTENSIONS = {".md", ".txt"}


def parse_front_matter(raw: str) -> tuple[dict[str, Any], str]:
    match = _FRONT.match(raw)
    if not match:
        return {}, raw
    data = yaml.safe_load(match.group(1)) or {}
    return (data if isinstance(data, dict) else {}), raw[match.end() :]


class LocalFilesIngestor:
    def __init__(self, source: Source) -> None:
        self.source = source
        self.root = Path(str(source.params["dir"]))

    def documents(self) -> Iterator[Document]:
        if not self.root.is_dir():
            return
        for path in sorted(self.root.rglob("*")):
            if path.suffix.lower() not in _EXTENSIONS or not path.is_file():
                continue
            meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
            heading = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            title = str(meta.get("title") or (heading.group(1) if heading else path.stem))
            rel = path.relative_to(self.root).as_posix()
            yield Document(
                doc_id=f"{self.source.id}:{rel}",
                source=self.source.id,
                title=title,
                text=body,
                url=str(meta.get("url", "")),
                date=str(meta.get("date", "")),
                evidence_level=str(meta.get("evidence_level", "unspecified")),
                license=str(meta.get("license") or self.source.license),
                metadata={"file": rel},
            )
