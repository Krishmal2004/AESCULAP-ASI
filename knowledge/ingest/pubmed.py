"""PubMed abstract ingestor (NCBI E-utilities)."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from typing import Any

from defusedxml import ElementTree as ET

from knowledge.ingest.http import Fetcher, http_get
from knowledge.models import Document
from knowledge.sources import Source

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
BATCH = 100

# Highest-priority publication type wins.
_EVIDENCE_ORDER: list[tuple[str, str]] = [
    ("Meta-Analysis", "meta-analysis"),
    ("Systematic Review", "systematic-review"),
    ("Practice Guideline", "guideline"),
    ("Guideline", "guideline"),
    ("Randomized Controlled Trial", "rct"),
    ("Clinical Trial", "clinical-trial"),
    ("Observational Study", "observational"),
    ("Case Reports", "case-report"),
    ("Review", "review"),
]


def evidence_from_pubtypes(pub_types: list[str]) -> str:
    present = set(pub_types)
    for pub_type, level in _EVIDENCE_ORDER:
        if pub_type in present:
            return level
    return "unspecified"


def _text(elem: Any) -> str:
    return "".join(elem.itertext()).strip() if elem is not None else ""


def _pub_date(article: Any) -> str:
    pub = article.find(".//Journal/JournalIssue/PubDate")
    if pub is None:
        return ""
    year = _text(pub.find("Year"))
    month = _text(pub.find("Month"))
    if year:
        months = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        if month in months:
            return f"{year}-{months.index(month) + 1:02d}"
        return f"{year}-{month.zfill(2)}" if month.isdigit() else year
    match = re.search(r"\d{4}", _text(pub.find("MedlineDate")))
    return match.group(0) if match else ""


def parse_pubmed_xml(xml: str, source: Source) -> list[Document]:
    """Parse an efetch PubmedArticleSet. Articles without an abstract are skipped."""
    root = ET.fromstring(xml)
    docs: list[Document] = []
    for art in root.findall(".//PubmedArticle"):
        pmid = _text(art.find(".//MedlineCitation/PMID"))
        if not pmid:
            continue
        parts: list[str] = []
        for node in art.findall(".//Abstract/AbstractText"):
            label = node.get("Label")
            body = _text(node)
            if body:
                parts.append(f"{label}: {body}" if label else body)
        if not parts:
            continue
        pub_types = [_text(n) for n in art.findall(".//PublicationTypeList/PublicationType")]
        docs.append(
            Document(
                doc_id=f"{source.id}:{pmid}",
                source=source.id,
                title=_text(art.find(".//Article/ArticleTitle")),
                text="\n\n".join(parts),
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                date=_pub_date(art),
                evidence_level=evidence_from_pubtypes(pub_types),
                license=source.license,
                metadata={
                    "pmid": pmid,
                    "journal": _text(art.find(".//Journal/Title")),
                    "publication_types": "; ".join(pub_types),
                },
            )
        )
    return docs


class PubMedIngestor:
    def __init__(self, source: Source, fetch: Fetcher | None = None) -> None:
        self.source = source
        self.fetch = fetch or http_get

    def _common(self) -> dict[str, str]:
        params = {"tool": "aesculap-asi"}
        if email := os.environ.get("NCBI_EMAIL"):
            params["email"] = email
        if key := os.environ.get("NCBI_API_KEY"):
            params["api_key"] = key
        return params

    def documents(self) -> Iterator[Document]:
        query = str(self.source.params["query"])
        max_results = int(self.source.params.get("max_results", 200))
        search = {
            **self._common(),
            "db": "pubmed",
            "term": query,
            "retmax": str(max_results),
            "retmode": "json",
        }
        ids = json.loads(self.fetch(f"{EUTILS}/esearch.fcgi", search))["esearchresult"]["idlist"]
        for start in range(0, len(ids), BATCH):
            batch = ids[start : start + BATCH]
            xml = self.fetch(
                f"{EUTILS}/efetch.fcgi",
                {**self._common(), "db": "pubmed", "id": ",".join(batch), "retmode": "xml"},
            )
            yield from parse_pubmed_xml(xml, self.source)
