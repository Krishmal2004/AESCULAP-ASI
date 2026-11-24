"""Hallucination check: medical claims must trace to a retrieved source (policy 2.5, 3.4).

Heuristic sentence-level check. A sentence is a "medical claim" if it contains clinical
vocabulary and makes an assertion (not a question, not a next-step or safety-net line).
A claim is grounded if it carries a valid ``[S#]`` citation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from safety.disclaimer import DISCLAIMER_MARKER

_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_CITE = re.compile(r"\[(S\d+)\]")
_CLINICAL = re.compile(
    r"\b(mg|dose|dosing|drug|medication|medicine|tablet|treat|treatment|therapy|contraindicat"
    r"|interact|side effect|adverse|risk|cause[sd]?|associated|indicated|symptom|diagnos"
    r"|infection|disease|syndrome|condition|blood|kidney|renal|liver|hepatic|heart|cardiac"
    r"|pressure|glucose|insulin|antibiotic|inflammation|warning|bleeding|level|study|trial"
    r"|guideline|recommend)\w*",
    re.IGNORECASE,
)
_EXEMPT = re.compile(
    r"^\s*(\*\*)?(next step|sources?|confidence|when to seek|what to do"
    r"|suggested next steps?|tool results?|calculated values?)\b"
    r"|^\s*(\*\*)?(summary|differential|red flags?|evidence)[^:]*:\**\s*$"
    r"|\(calculated\)"
    r"|couldn'?t find supporting evidence|i'?m not sure|not covered by|please (call|contact|see|speak)"
    r"|see a (clinician|doctor|pharmacist)|speak (to|with) (a|your) (clinician|doctor|pharmacist)"
    r"|seek (urgent|emergency|medical) (care|help)|call .{0,30}emergency|can'?t (examine|assess)"
    r"|cannot (examine|assess)|ask your (doctor|clinician|pharmacist)|\?\s*$",
    re.IGNORECASE,
)


@dataclass
class GroundingReport:
    claims: int = 0
    grounded: int = 0
    ungrounded: list[str] = field(default_factory=list)

    @property
    def faithfulness(self) -> float:
        return 1.0 if self.claims == 0 else self.grounded / self.claims


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text) if s and s.strip()]


_TRAILING_CITE = re.compile(r"(\[S\d+\]\s*)+[.!?]?\s*$")


def _units(text: str) -> list[str]:
    """A line ending in a citation is one unit (the citation covers the line); other lines are
    split into sentences so each sentence must carry its own citation."""
    units: list[str] = []
    for line in text.splitlines():
        if _TRAILING_CITE.search(line):
            units.append(line.strip())
        else:
            units.extend(split_sentences(line))
    return [u for u in units if u]


def check_grounding(text: str, valid_ids: set[str]) -> GroundingReport:
    report = GroundingReport()
    for sent in _units(text):
        clean = sent.strip("*_> -").strip()
        if not clean or DISCLAIMER_MARKER in clean.lower() or clean.startswith("[S"):
            continue
        if _EXEMPT.search(clean) or not _CLINICAL.search(clean):
            continue
        report.claims += 1
        ids = set(_CITE.findall(clean))
        if ids and ids <= valid_ids:
            report.grounded += 1
        else:
            report.ungrounded.append(clean)
    return report
