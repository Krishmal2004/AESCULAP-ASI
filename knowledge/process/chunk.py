"""Sentence/paragraph-aware chunking that preserves provenance metadata."""

from __future__ import annotations

import re

from knowledge.models import Chunk, Document

_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")
_HEADING = re.compile(r"^#{1,6}\s+\S.*$")

# (text, starts_new_paragraph)
Unit = tuple[str, bool]


def _words(text: str) -> int:
    return len(text.split())


def _hard_split(text: str, max_words: int) -> list[str]:
    words = text.split()
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]


def _units(text: str, max_words: int) -> list[Unit]:
    units: list[Unit] = []
    pending_heading: str | None = None
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        if "\n" not in block and _HEADING.match(block):
            pending_heading = block
            continue
        if pending_heading:
            block = f"{pending_heading}\n{block}"
            pending_heading = None
        if _words(block) <= max_words:
            units.append((block, True))
            continue
        first = True
        for sentence in _SENTENCE.split(block):
            pieces = (
                _hard_split(sentence, max_words) if _words(sentence) > max_words else [sentence]
            )
            for piece in pieces:
                units.append((piece, first))
                first = False
    if pending_heading:
        units.append((pending_heading, True))
    return units


def _join(units: list[Unit]) -> str:
    out = ""
    for text, new_para in units:
        out += ("\n\n" if new_para else " ") + text if out else text
    return out


def split_text(text: str, max_words: int = 220, overlap_words: int = 40) -> list[str]:
    """Pack units into chunks of at most ~max_words, carrying a small overlap."""
    if max_words < 1:
        raise ValueError("max_words must be >= 1")
    if not 0 <= overlap_words < max_words:
        raise ValueError("overlap_words must be in [0, max_words)")

    chunks: list[str] = []
    current: list[Unit] = []
    current_words = 0
    new_units = 0
    for unit in _units(text, max_words):
        words = _words(unit[0])
        if current and current_words + words > max_words:
            if new_units:
                chunks.append(_join(current))
            tail: list[Unit] = []
            carried = 0
            for prev in reversed(current):
                if carried + _words(prev[0]) > overlap_words:
                    break
                tail.insert(0, prev)
                carried += _words(prev[0])
            if carried + words > max_words:
                tail, carried = [], 0
            current, current_words, new_units = tail, carried, 0
        current.append(unit)
        current_words += words
        new_units += 1
    if current and new_units:
        chunks.append(_join(current))
    return chunks


def chunk_document(doc: Document, max_words: int = 220, overlap_words: int = 40) -> list[Chunk]:
    base = {
        "source": doc.source,
        "title": doc.title,
        "url": doc.url,
        "date": doc.date,
        "evidence_level": doc.evidence_level,
        "license": doc.license,
    }
    extra = {k: v for k, v in doc.metadata.items() if k not in base}
    return [
        Chunk(
            chunk_id=f"{doc.doc_id}#{i:04d}",
            doc_id=doc.doc_id,
            index=i,
            text=text,
            metadata={**extra, **base},
        )
        for i, text in enumerate(split_text(doc.text, max_words, overlap_words))
    ]
