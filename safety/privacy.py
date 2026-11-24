"""De-identification for logs and memory (policy section 5).

Best-effort pattern scrubbing. It is NOT a certified de-identification method; real PHI
must not enter the system until legal review is complete.
"""

from __future__ import annotations

import re

_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"(?<!\w)(\+?\d[\d\s().-]{7,}\d)(?!\w)"), "[PHONE]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[ID]"),
    (
        re.compile(
            r"\b(MRN|NHS|patient id|record)\s*(no\.?|number|#)?\s*[:#]?\s*[A-Z0-9-]{4,}\b", re.I
        ),
        "[RECORD-ID]",
    ),
    (re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"), "[DATE]"),
    (
        re.compile(
            r"\b(my name is|i am called|i'm called|name:)\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)?", re.I
        ),
        r"\1 [NAME]",
    ),
    (
        re.compile(r"\b\d{1,5}\s+[A-Z][a-z]+\s+(Street|St|Road|Rd|Avenue|Ave|Lane|Ln)\b"),
        "[ADDRESS]",
    ),
]


def redact(text: str) -> str:
    for pattern, repl in _RULES:
        text = pattern.sub(repl, text)
    return text


def redact_obj(value: object) -> object:
    """Recursively redact strings inside dicts/lists (for audit records)."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_obj(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact_obj(v) for v in value]
    return value
