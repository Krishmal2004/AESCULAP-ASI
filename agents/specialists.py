"""Specialist agents coordinated by the orchestrator.

Each specialist widens retrieval with focused queries and adds its own checks. They share
the same reasoner, safety gate and citation rules as the generalist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Specialist:
    name: str
    pattern: re.Pattern[str]
    query_templates: tuple[str, ...]
    focus: str

    def matches(self, text: str) -> bool:
        return bool(self.pattern.search(text))

    def queries(self, question: str) -> list[str]:
        return [t.format(q=question) for t in self.query_templates]


SPECIALISTS: tuple[Specialist, ...] = (
    Specialist(
        "cardiology",
        re.compile(
            r"\b(heart|cardiac|palpitation|blood pressure|hypertension|cholesterol|statin"
            r"|atrial|arrhythm|angina|chest)\w*",
            re.I,
        ),
        ("{q} cardiovascular risk", "{q} warnings cardiac"),
        "Cardiology review: cardiovascular red flags, risk scores (e.g. CHA2DS2-VASc).",
    ),
    Specialist(
        "neurology",
        re.compile(
            r"\b(headache|migraine|numb|tingl|seizure|epilep|dizz|vertigo|faint|memory loss"
            r"|tremor|weakness)\w*",
            re.I,
        ),
        ("{q} neurological warning signs",),
        "Neurology review: focal deficits, thunderclap headache, seizure red flags.",
    ),
    Specialist(
        "pharmacology",
        re.compile(
            r"\b(drug|medication|medicine|tablet|pill|interact|side effect|dose|dosage"
            r"|contraindicat|prescri)\w*",
            re.I,
        ),
        ("{q} drug interactions", "{q} contraindications warnings", "{q} renal impairment"),
        "Pharmacology review: interactions, contraindications, renal/hepatic cautions. "
        "Never set individual doses.",
    ),
)


def route(text: str, drugs: list[str] | None = None) -> list[Specialist]:
    chosen = [s for s in SPECIALISTS if s.matches(text)]
    if drugs and not any(s.name == "pharmacology" for s in chosen):
        chosen.append(next(s for s in SPECIALISTS if s.name == "pharmacology"))
    return chosen
