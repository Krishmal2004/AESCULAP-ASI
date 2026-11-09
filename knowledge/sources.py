"""Source registry with a license gate.

A source may be ingested only if it is enabled, has an implemented ingestor, and a
human has marked its license as ``approved`` (with ``reviewed_by``). This enforces
the Phase 2 step "collect and license-check each source".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

LICENSE_STATUSES = {"approved", "needs_review", "rejected"}


class SourceError(ValueError):
    pass


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    use: str
    license: str
    license_status: str = "needs_review"
    reviewed_by: str = ""
    enabled: bool = False
    ingestor: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    max_age_days: int | None = None
    notes: str = ""

    def blocker(self) -> str | None:
        """Reason this source cannot be ingested, or None if it can."""
        if not self.enabled:
            return "disabled"
        if not self.ingestor:
            return "no ingestor implemented"
        if self.license_status != "approved":
            return f"license_status={self.license_status}"
        if not self.reviewed_by:
            return "approved without reviewed_by"
        return None

    @property
    def ingestible(self) -> bool:
        return self.blocker() is None


def load_sources(path: Path) -> list[Source]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = raw.get("sources", [])
    sources: list[Source] = []
    seen: set[str] = set()
    for item in items:
        try:
            src = Source(
                id=item["id"],
                name=item["name"],
                use=item.get("use", ""),
                license=item.get("license", ""),
                license_status=item.get("license_status", "needs_review"),
                reviewed_by=item.get("reviewed_by", "") or "",
                enabled=bool(item.get("enabled", False)),
                ingestor=item.get("ingestor"),
                params=dict(item.get("params") or {}),
                max_age_days=item.get("max_age_days"),
                notes=item.get("notes", ""),
            )
        except KeyError as exc:
            raise SourceError(f"source entry missing field {exc}: {item!r}") from exc
        if src.license_status not in LICENSE_STATUSES:
            raise SourceError(f"{src.id}: invalid license_status {src.license_status!r}")
        if src.id in seen:
            raise SourceError(f"duplicate source id {src.id!r}")
        seen.add(src.id)
        sources.append(src)
    return sources
