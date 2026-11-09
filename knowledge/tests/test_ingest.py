from __future__ import annotations

import json
import urllib.error
from collections.abc import Mapping
from pathlib import Path

import pytest

from knowledge.ingest.local_files import LocalFilesIngestor, parse_front_matter
from knowledge.ingest.openfda import OpenFDAIngestor, parse_label
from knowledge.ingest.pubmed import PubMedIngestor, evidence_from_pubtypes, parse_pubmed_xml
from knowledge.sources import Source, SourceError, load_sources

SRC = Source(
    id="s",
    name="S",
    use="",
    license="L",
    license_status="approved",
    reviewed_by="t",
    enabled=True,
    ingestor="x",
    params={},
)

PUBMED_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>111</PMID>
      <Article>
        <Journal><Title>Journal of Tests</Title>
          <JournalIssue><PubDate><Year>2023</Year><Month>Mar</Month></PubDate></JournalIssue>
        </Journal>
        <ArticleTitle>A <i>synthetic</i> trial</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Background text.</AbstractText>
          <AbstractText Label="RESULTS">Results text.</AbstractText>
        </Abstract>
        <PublicationTypeList>
          <PublicationType>Journal Article</PublicationType>
          <PublicationType>Randomized Controlled Trial</PublicationType>
        </PublicationTypeList>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>222</PMID>
      <Article><ArticleTitle>No abstract</ArticleTitle></Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>"""


def test_parse_pubmed_xml() -> None:
    docs = parse_pubmed_xml(PUBMED_XML, SRC)
    assert len(docs) == 1  # article without abstract skipped
    doc = docs[0]
    assert doc.doc_id == "s:111"
    assert doc.title == "A synthetic trial"
    assert doc.text == "BACKGROUND: Background text.\n\nRESULTS: Results text."
    assert doc.date == "2023-03"
    assert doc.evidence_level == "rct"
    assert doc.url == "https://pubmed.ncbi.nlm.nih.gov/111/"


def test_pubmed_xml_rejects_entity_bombs() -> None:
    bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>'
    with pytest.raises(Exception):  # noqa: B017 - defusedxml raises EntitiesForbidden
        parse_pubmed_xml(bomb, SRC)


def test_evidence_priority() -> None:
    assert evidence_from_pubtypes(["Review", "Meta-Analysis"]) == "meta-analysis"
    assert evidence_from_pubtypes(["Journal Article"]) == "unspecified"


def test_pubmed_ingestor_batches_requests() -> None:
    calls: list[str] = []

    def fake(url: str, params: Mapping[str, str]) -> str:
        calls.append(url.rsplit("/", 1)[-1])
        if url.endswith("esearch.fcgi"):
            return json.dumps({"esearchresult": {"idlist": ["111"]}})
        return PUBMED_XML

    src = Source(**{**SRC.__dict__, "params": {"query": "q"}})
    docs = list(PubMedIngestor(src, fake).documents())
    assert [d.doc_id for d in docs] == ["s:111"]
    assert calls == ["esearch.fcgi", "efetch.fcgi"]


LABEL = {
    "set_id": "abc-123",
    "effective_time": "20240131",
    "version": "4",
    "openfda": {"generic_name": ["testdrug"], "brand_name": ["Testbrand"]},
    "indications_and_usage": ["For testing."],
    "contraindications": ["None known."],
}


def test_parse_label() -> None:
    doc = parse_label(LABEL, SRC)
    assert doc is not None
    assert doc.doc_id == "s:abc-123"
    assert doc.title == "testdrug / Testbrand"
    assert doc.date == "2024-01-31"
    assert doc.evidence_level == "regulatory-label"
    assert "## Indications and usage\nFor testing." in doc.text
    assert "## Contraindications" in doc.text


def test_parse_label_without_text_or_id_is_skipped() -> None:
    assert parse_label({"set_id": "x", "openfda": {}}, SRC) is None
    assert parse_label({"indications_and_usage": ["x"]}, SRC) is None


def test_openfda_ingestor_paginates_and_stops() -> None:
    pages = {"0": [LABEL], "1": [{**LABEL, "set_id": "def-456"}]}

    def fake(url: str, params: Mapping[str, str]) -> str:
        skip = params["skip"]
        return json.dumps({"meta": {"results": {"total": 2}}, "results": pages.get(skip, [])})

    src = Source(**{**SRC.__dict__, "params": {"max_results": 500}})
    # PAGE_SIZE is 100, so the fake returns 1 per page; ingestor advances by len(results).
    docs = list(OpenFDAIngestor(src, fake).documents())
    assert [d.doc_id for d in docs] == ["s:abc-123", "s:def-456"]


def test_openfda_404_means_no_results() -> None:
    def fake(url: str, params: Mapping[str, str]) -> str:
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]

    assert list(OpenFDAIngestor(SRC, fake).documents()) == []


def test_front_matter_parsing() -> None:
    meta, body = parse_front_matter("---\ntitle: T\ndate: 2024-05-01\n---\nBody")
    assert meta["title"] == "T"
    assert body == "Body"
    assert parse_front_matter("No front matter") == ({}, "No front matter")


def test_local_files_ingestor(inbox: Path) -> None:
    (inbox / "a.md").write_text(
        "---\ntitle: Doc A\nevidence_level: guideline\n---\nText A", encoding="utf-8"
    )
    (inbox / "b.txt").write_text("# Heading B\nText B", encoding="utf-8")
    (inbox / "skip.pdf").write_text("ignored", encoding="utf-8")
    src = Source(**{**SRC.__dict__, "params": {"dir": str(inbox)}})
    docs = {d.doc_id: d for d in LocalFilesIngestor(src).documents()}
    assert set(docs) == {"s:a.md", "s:b.txt"}
    assert docs["s:a.md"].title == "Doc A"
    assert docs["s:a.md"].evidence_level == "guideline"
    assert docs["s:b.txt"].title == "Heading B"
    assert docs["s:b.txt"].license == "L"


def test_missing_inbox_yields_nothing(tmp_path: Path) -> None:
    src = Source(**{**SRC.__dict__, "params": {"dir": str(tmp_path / "nope")}})
    assert list(LocalFilesIngestor(src).documents()) == []


def test_real_sources_file_is_valid_and_license_gated() -> None:
    sources = {s.id: s for s in load_sources(Path("knowledge/sources.yaml"))}
    assert sources["openfda_labels"].ingestible
    for sid in ("pubmed", "who_guidelines", "nice_guidelines", "drugbank", "snomed_ct"):
        assert not sources[sid].ingestible, f"{sid} must stay blocked until a human approves it"


def test_blockers() -> None:
    base = dict(SRC.__dict__)
    assert Source(**{**base, "enabled": False}).blocker() == "disabled"
    assert Source(**{**base, "ingestor": None}).blocker() == "no ingestor implemented"
    assert Source(**{**base, "license_status": "rejected"}).blocker() == "license_status=rejected"
    assert Source(**{**base, "reviewed_by": ""}).blocker() == "approved without reviewed_by"
    assert SRC.blocker() is None


def test_invalid_license_status_rejected(tmp_path: Path) -> None:
    f = tmp_path / "s.yaml"
    f.write_text("sources:\n  - {id: a, name: A, license_status: maybe}\n", encoding="utf-8")
    with pytest.raises(SourceError):
        load_sources(f)
