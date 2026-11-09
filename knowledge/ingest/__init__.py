"""Source ingestors. Each yields Document objects."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from knowledge.ingest.http import Fetcher
from knowledge.models import Document
from knowledge.sources import Source, SourceError


class Ingestor(Protocol):
    def documents(self) -> Iterator[Document]: ...


def get_ingestor(source: Source, fetch: Fetcher | None = None) -> Ingestor:
    # Imported lazily so a broken ingestor cannot break the others.
    if source.ingestor == "openfda":
        from knowledge.ingest.openfda import OpenFDAIngestor

        return OpenFDAIngestor(source, fetch)
    if source.ingestor == "pubmed":
        from knowledge.ingest.pubmed import PubMedIngestor

        return PubMedIngestor(source, fetch)
    if source.ingestor == "local_files":
        from knowledge.ingest.local_files import LocalFilesIngestor

        return LocalFilesIngestor(source)
    raise SourceError(f"{source.id}: unknown ingestor {source.ingestor!r}")
