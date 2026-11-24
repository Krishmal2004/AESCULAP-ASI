"""Human-in-the-loop review queue for high-risk outputs (policy section 4)."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ReviewQueue:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        if path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    item = json.loads(line)
                    self._items[item["id"]] = item

    def _persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            "".join(json.dumps(i, ensure_ascii=False) + "\n" for i in self._items.values()),
            encoding="utf-8",
        )

    def submit(self, trace_id: str, question: str, answer: str, meta: dict[str, Any]) -> str:
        rid = uuid.uuid4().hex[:12]
        with self._lock:
            self._items[rid] = {
                "id": rid,
                "trace_id": trace_id,
                "question": question,
                "answer": answer,
                "meta": meta,
                "status": "pending",
                "created": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            self._persist()
        return rid

    def pending(self) -> list[dict[str, Any]]:
        return [i for i in self._items.values() if i["status"] == "pending"]

    def get(self, rid: str) -> dict[str, Any] | None:
        return self._items.get(rid)

    def decide(self, rid: str, approve: bool, reviewer: str, note: str = "") -> dict[str, Any]:
        with self._lock:
            item = self._items[rid]
            if item["status"] != "pending":
                raise ValueError(f"review {rid} already {item['status']}")
            item.update(
                status="approved" if approve else "rejected",
                reviewer=reviewer,
                note=note,
                decided=datetime.now(UTC).isoformat(timespec="seconds"),
            )
            self._persist()
            return dict(item)
