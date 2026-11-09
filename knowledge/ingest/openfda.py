"""openFDA drug label ingestor."""

from __future__ import annotations

import json
import os
import urllib.error
from collections.abc import Iterator
from typing import Any

from knowledge.ingest.http import Fetcher, http_get
from knowledge.models import Document
from knowledge.sources import Source

ENDPOINT = "https://api.fda.gov/drug/label.json"
PAGE_SIZE = 100

# (label field, heading). Order = order in the document text.
SECTIONS: list[tuple[str, str]] = [
    ("boxed_warning", "Boxed warning"),
    ("indications_and_usage", "Indications and usage"),
    ("dosage_and_administration", "Dosage and administration"),
    ("contraindications", "Contraindications"),
    ("warnings", "Warnings"),
    ("warnings_and_cautions", "Warnings and precautions"),
    ("drug_interactions", "Drug interactions"),
    ("adverse_reactions", "Adverse reactions"),
    ("use_in_specific_populations", "Use in specific populations"),
    ("pregnancy", "Pregnancy"),
]


def _first(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    return value if isinstance(value, str) else ""


def _iso_date(yyyymmdd: str) -> str:
    if len(yyyymmdd) == 8 and yyyymmdd.isdigit():
        return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
    return yyyymmdd


def parse_label(label: dict[str, Any], source: Source) -> Document | None:
    """Convert one openFDA label record into a Document (None if it has no text)."""
    sections: list[str] = []
    for field_name, heading in SECTIONS:
        parts = label.get(field_name)
        if isinstance(parts, str):
            parts = [parts]
        if not parts:
            continue
        body = "\n".join(str(p) for p in parts).strip()
        if body:
            sections.append(f"## {heading}\n{body}")
    if not sections:
        return None

    openfda = label.get("openfda") or {}
    generic = _first(openfda.get("generic_name"))
    brand = _first(openfda.get("brand_name"))
    label_id = str(label.get("set_id") or label.get("id") or "")
    if not label_id:
        return None
    title = " / ".join(x for x in (generic, brand) if x) or f"Drug label {label_id}"
    return Document(
        doc_id=f"{source.id}:{label_id}",
        source=source.id,
        title=title,
        text="\n\n".join(sections),
        url=f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={label_id}",
        date=_iso_date(str(label.get("effective_time", ""))),
        evidence_level="regulatory-label",
        license=source.license,
        metadata={
            "generic_name": generic,
            "brand_name": brand,
            "label_version": str(label.get("version", "")),
        },
    )


class OpenFDAIngestor:
    def __init__(self, source: Source, fetch: Fetcher | None = None) -> None:
        self.source = source
        self.fetch = fetch or http_get

    def documents(self) -> Iterator[Document]:
        search = str(self.source.params.get("search", "_exists_:openfda.generic_name"))
        max_results = int(self.source.params.get("max_results", 100))
        api_key = os.environ.get("OPENFDA_API_KEY")
        skip = 0
        while skip < max_results:
            params = {
                "search": search,
                "limit": str(min(PAGE_SIZE, max_results - skip)),
                "skip": str(skip),
            }
            if api_key:
                params["api_key"] = api_key
            try:
                data = json.loads(self.fetch(ENDPOINT, params))
            except urllib.error.HTTPError as exc:
                if exc.code == 404:  # openFDA returns 404 for "no results"
                    return
                raise
            results = data.get("results") or []
            if not results:
                return
            for label in results:
                doc = parse_label(label, self.source)
                if doc is not None:
                    yield doc
            skip += len(results)
            total = ((data.get("meta") or {}).get("results") or {}).get("total")
            if isinstance(total, int) and skip >= total:
                return
