"""Scope checks (policy section 3.6): v1 covers adult general / primary care only."""

from __future__ import annotations

import re
from dataclasses import dataclass

_OUT_OF_SCOPE: dict[str, str] = {
    "paediatrics": (
        r"\b(my|our|a) (baby|infant|toddler|newborn|child|son|daughter|kid)\b"
        r"|\b(\d{1,2})[- ](month|week)[- ]old\b|\bpaediatric|\bpediatric"
        r"|\b([0-9]|1[0-5])[- ]?(year|yr)s?[- ]old\b"
    ),
    "pregnancy": r"\bpregnan|\bbreastfeed|\bbreast-feed|\btrimester\b|\bexpecting a baby\b",
    "oncology": r"\bcancer\b|\btumou?r\b|\bchemo|\boncolog|\bmetasta|\blymphoma\b|\bleuka?emia\b",
}
_COMPILED = {k: re.compile(v) for k, v in _OUT_OF_SCOPE.items()}

_NON_MEDICAL = re.compile(
    r"\b(write (me )?(a|an) (poem|essay|story|code)|stock|bitcoin|recipe for (?!health)"
    r"|weather|football|homework)\b"
)


@dataclass(frozen=True)
class ScopeResult:
    in_scope: bool
    areas: tuple[str, ...] = ()
    non_medical: bool = False

    def message(self) -> str:
        if self.non_medical:
            return (
                "I'm a clinical decision-support assistant, so I can only help with health "
                "and medical questions. Is there something health-related I can help with?"
            )
        joined = ", ".join(self.areas)
        return (
            f"This question involves {joined}, which is outside what this version of "
            "Aesculap covers (adult general and primary care). Please speak to a clinician "
            "who specialises in this area. I can still share general, cited information, "
            "but it must be reviewed by them."
        )


def check_scope(text: str) -> ScopeResult:
    lowered = text.lower()
    areas = tuple(k for k, pat in _COMPILED.items() if pat.search(lowered))
    non_medical = bool(_NON_MEDICAL.search(lowered)) and not areas
    return ScopeResult(in_scope=not areas and not non_medical, areas=areas, non_medical=non_medical)
