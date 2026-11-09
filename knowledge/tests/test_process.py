from __future__ import annotations

import pytest

from knowledge.models import Document
from knowledge.process.chunk import chunk_document, split_text
from knowledge.process.clean import clean_document, clean_text


def test_clean_strips_html_and_normalises_whitespace() -> None:
    assert clean_text("<p>Hello&nbsp;  <b>world</b></p>\n\n\n\nNext") == "Hello world\n\nNext"


def test_clean_preserves_comparison_signs_and_numbers() -> None:
    text = "Significant at p<0.05; dose <5 mg and BP >140/90."
    assert clean_text(text) == text


def test_clean_removes_control_characters() -> None:
    assert clean_text("a\x00b\x07c") == "abc"


def test_clean_document_keeps_metadata() -> None:
    doc = Document("d1", "s", " <i>T</i> ", "<p>x</p>", date="2024")
    cleaned = clean_document(doc)
    assert (cleaned.title, cleaned.text, cleaned.date) == ("T", "x", "2024")


def test_content_hash_changes_with_text() -> None:
    a = Document("d", "s", "t", "one")
    b = Document("d", "s", "t", "two")
    assert a.content_hash != b.content_hash
    assert a.content_hash == Document("d", "s", "t", "one").content_hash


def test_short_text_is_single_chunk() -> None:
    assert split_text("One short paragraph.", 50, 10) == ["One short paragraph."]


def test_chunks_respect_max_words_and_cover_all_text() -> None:
    sentences = [f"Sentence number {i} has exactly seven words." for i in range(40)]
    chunks = split_text(" ".join(sentences), max_words=30, overlap_words=8)
    assert len(chunks) > 1
    assert all(len(c.split()) <= 30 for c in chunks)
    joined = " ".join(chunks)
    assert all(s in joined for s in sentences)


def test_overlap_repeats_trailing_sentence() -> None:
    sentences = [f"Sentence number {i} has exactly seven words." for i in range(10)]
    chunks = split_text(" ".join(sentences), max_words=30, overlap_words=8)
    last_of_first = chunks[0].split(". ")[-1].rstrip(".")
    assert last_of_first in chunks[1]


def test_oversized_sentence_is_hard_split() -> None:
    chunks = split_text(" ".join(["word"] * 100), max_words=30, overlap_words=0)
    assert all(len(c.split()) <= 30 for c in chunks)
    assert sum(len(c.split()) for c in chunks) == 100


def test_heading_stays_with_following_paragraph() -> None:
    text = "## Contraindications\nDo not use if allergic.\n\n## Warnings\nSee label."
    chunks = split_text(text, 50, 0)
    assert chunks == [text.replace("\n\n", "\n\n")]
    assert chunks[0].index("## Warnings") > chunks[0].index("Do not use")


def test_invalid_overlap_rejected() -> None:
    with pytest.raises(ValueError):
        split_text("x", max_words=10, overlap_words=10)


def test_chunk_document_carries_provenance() -> None:
    doc = Document(
        "src:1",
        "src",
        "Title",
        "Body text.",
        url="https://x",
        date="2024-01",
        evidence_level="rct",
        license="L",
        metadata={"pmid": "1"},
    )
    (chunk,) = chunk_document(doc)
    assert chunk.chunk_id == "src:1#0000"
    assert chunk.metadata["source"] == "src"
    assert chunk.metadata["evidence_level"] == "rct"
    assert chunk.metadata["url"] == "https://x"
    assert chunk.metadata["pmid"] == "1"
