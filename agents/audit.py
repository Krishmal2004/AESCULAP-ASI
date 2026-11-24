"""Audit log (policy 3.7): inputs, sources, tool calls, critic findings, gate decisions.

Append-only JSONL, redacted before writing. Without a path, records stay in memory.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from safety.privacy import redact_obj


class AuditLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.records: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def log(self, trace_id: str, step: str, data: dict[str, Any]) -> None:
        record = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "trace_id": trace_id,
            "step": step,
            "data": redact_obj(data),
        }
        with self._lock:
            self.records.append(record)
            if len(self.records) > 5000:
                del self.records[:1000]
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def trace(self, trace_id: str) -> list[dict[str, Any]]:
        return [r for r in self.records if r["trace_id"] == trace_id]
