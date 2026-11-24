"""Fairness controls (policy section 6).

Protected attributes must not steer evidence retrieval. ``neutralise`` strips ethnicity,
gender words and demographic phrasing from the text used for search and evidence ranking.
Clinically relevant facts (age, sex for eGFR, pregnancy) still reach the planner and the
model through structured patient context and the original question.
"""

from __future__ import annotations

import re

_ETHNICITY = (
    r"black|white|caucasian|african(?:[- ]american)?|asian|south asian|east asian|hispanic"
    r"|latino|latina|latinx|arab|middle eastern|indigenous|native american|pacific islander"
    r"|jewish|muslim|christian|hindu"
)
_GENDER = (
    r"man|woman|men|women|male|female|non-binary person|non-binary|nonbinary|transgender"
    r"|trans|gentleman|lady|guy|girl|boy|person"
)
_PATTERNS = [
    re.compile(rf"\b({_ETHNICITY})\b", re.I),
    re.compile(r"\b\d{1,3}[- ]?(year|yr)s?[- ]?old\b", re.I),
    re.compile(r"\bage(d)?\s*\d{1,3}\b", re.I),
    re.compile(rf"\b({_GENDER})\b", re.I),
    re.compile(r"\b(i am|i'm) an?\b\.?", re.I),
]


def neutralise(text: str) -> str:
    out = text
    for pat in _PATTERNS:
        out = pat.sub(" ", out)
    out = re.sub(r"\s+([,.?!])", r"\1", out)
    out = re.sub(r"^[\s,.]+|(?<=[.?!])[\s,.]+(?=[,.])", "", out)
    return " ".join(out.split()) or text
