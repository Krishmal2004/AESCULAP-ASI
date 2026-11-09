"""Shared fixtures. All text here is SYNTHETIC test data, not medical guidance."""

from __future__ import annotations

from pathlib import Path

import pytest

from knowledge.config import Config

SOURCES_YAML = """
sources:
  - id: inbox
    name: Test inbox
    license: test-license
    license_status: approved
    reviewed_by: tester
    enabled: true
    ingestor: local_files
    max_age_days: 7
    params:
      dir: {inbox}
  - id: unreviewed
    name: Unreviewed
    license: unknown
    license_status: needs_review
    enabled: true
    ingestor: local_files
    params:
      dir: {inbox}
  - id: planned
    name: Planned
    license: unknown
    license_status: approved
    reviewed_by: tester
    enabled: true
    ingestor: null
"""

LEXICON_YAML = """
entities:
  - {id: "drug:testdrug", name: testdrug, type: drug}
  - {id: "disease:testitis", name: testitis, type: disease, synonyms: ["test inflammation"]}
  - {id: "symptom:testache", name: testache, type: symptom}
"""


@pytest.fixture
def config(tmp_path: Path) -> Config:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    sources = tmp_path / "sources.yaml"
    sources.write_text(SOURCES_YAML.format(inbox=inbox.as_posix()), encoding="utf-8")
    lexicon = tmp_path / "lexicon.yaml"
    lexicon.write_text(LEXICON_YAML, encoding="utf-8")
    return Config(
        data_dir=tmp_path / "data",
        sources_file=sources,
        lexicon_file=lexicon,
        chunk_words=60,
        overlap_words=10,
    )


@pytest.fixture
def inbox(tmp_path: Path) -> Path:
    path = tmp_path / "inbox"
    path.mkdir(exist_ok=True)
    return path
