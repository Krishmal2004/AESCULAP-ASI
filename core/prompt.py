"""Builds the model prompt from character/system_prompt.md."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from knowledge.search import format_for_prompt

PROMPT_FILE = Path(__file__).resolve().parent.parent / "character" / "system_prompt.md"
_BEGIN = "<!-- BEGIN SYSTEM PROMPT -->"
_END = "<!-- END SYSTEM PROMPT -->"
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
MODES = ("clinician", "patient")


@lru_cache(maxsize=4)
def load_template(path: Path = PROMPT_FILE) -> str:
    raw = path.read_text(encoding="utf-8")
    start, end = raw.find(_BEGIN), raw.find(_END)
    if start < 0 or end < 0:
        raise ValueError(f"{path}: system prompt markers not found")
    return raw[start + len(_BEGIN) : end].strip()


def normalise_mode(mode: str | None) -> str:
    """Unknown or missing mode defaults to patient (the safer assumption)."""
    return mode if mode in MODES else "patient"


def render_system_prompt(
    *,
    mode: str | None,
    evidence: list[dict[str, Any]],
    patient_context: dict[str, Any] | str | None = None,
    locale: str | None = None,
) -> str:
    if isinstance(patient_context, dict):
        ctx = json.dumps(patient_context, ensure_ascii=False, sort_keys=True) or "(none)"
    else:
        ctx = patient_context or "(none)"
    values = {
        "mode": normalise_mode(mode),
        "retrieved_sources": "\n\n" + format_for_prompt(evidence) + "\n",
        "patient_context": ctx,
        "locale": locale or "your local",
    }
    # Unfilled placeholders are stripped (system_prompt.md maintenance notes).
    return _PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), "")), load_template())
