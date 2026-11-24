"""Memory: per-session context, and long-term memory ONLY with explicit, revocable consent.

Everything stored is passed through ``safety.privacy.redact`` first.
"""

from __future__ import annotations

import json
import threading
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from safety.privacy import redact, redact_obj

MAX_TURNS = 20


class SessionMemory:
    def __init__(self) -> None:
        self._turns: dict[str, deque[dict[str, str]]] = defaultdict(lambda: deque(maxlen=MAX_TURNS))
        self._context: dict[str, dict[str, Any]] = defaultdict(dict)
        self._lock = threading.Lock()

    def add_turn(self, session_id: str, role: str, text: str) -> None:
        with self._lock:
            self._turns[session_id].append({"role": role, "text": redact(text)})

    def turns(self, session_id: str) -> list[dict[str, str]]:
        return list(self._turns.get(session_id, []))

    def update_context(self, session_id: str, ctx: dict[str, Any] | None) -> dict[str, Any]:
        with self._lock:
            if ctx:
                self._context[session_id].update(ctx)
            return dict(self._context.get(session_id, {}))

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._turns.pop(session_id, None)
            self._context.pop(session_id, None)


class LongTermMemory:
    """JSON file per user. Writes are refused without consent; forget() erases everything."""

    def __init__(self, directory: Path) -> None:
        self.dir = directory

    def _path(self, user_id: str) -> Path:
        safe = "".join(c for c in user_id if c.isalnum() or c in "-_")[:64]
        if not safe:
            raise ValueError("invalid user id")
        return self.dir / f"{safe}.json"

    def remember(self, user_id: str, facts: dict[str, Any], *, consent: bool) -> bool:
        if not consent:
            return False
        path = self._path(user_id)
        data = self.recall(user_id)
        data.update(redact_obj(facts))  # type: ignore[arg-type]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return True

    def recall(self, user_id: str) -> dict[str, Any]:
        path = self._path(user_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def forget(self, user_id: str) -> bool:
        path = self._path(user_id)
        if path.exists():
            path.unlink()
            return True
        return False
