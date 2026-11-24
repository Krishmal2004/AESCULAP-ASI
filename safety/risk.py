"""Risk tiers (policy section 4). Rule: if classification is uncertain, take the higher tier."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum

from safety.emergency import EmergencyResult, detect_emergency
from safety.scope import ScopeResult, check_scope


class RiskTier(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    CRITICAL = 3

    @property
    def label(self) -> str:
        return self.name.lower()


_HIGH = re.compile(
    r"\b(can i (take|use|have|drink)|(take|use|mix) \w+ (with|and|while)"
    r"|dose|dosage|dosing|how much .{0,30}(take|give)|mg\b|interact|interaction|together with"
    r"|combine|mix .{0,20} with|stop taking|start taking|switch (from|to)|increase my|decrease my"
    r"|critical (value|result)|abnormal (result|lab)|do i have|diagnos)"
)
_MODERATE = re.compile(
    r"\b(symptom|pain|ache|fever|cough|rash|swelling|dizz|nausea|vomit|diarrh|fatigue|tired"
    r"|result|test|lab|blood|scan|x-ray|differential|cause|could it be|what is wrong|sore)"
)
_EDUCATION = re.compile(r"^\s*(what is|what are|define|explain|what does .{0,30} mean)\b")


@dataclass(frozen=True)
class RiskAssessment:
    tier: RiskTier
    reasons: tuple[str, ...]
    emergency: EmergencyResult
    scope: ScopeResult


def assess_risk(text: str) -> RiskAssessment:
    lowered = text.lower()
    emergency = detect_emergency(text)
    scope = check_scope(text)
    reasons: list[str] = []

    if emergency.is_emergency:
        return RiskAssessment(
            RiskTier.CRITICAL, (f"emergency:{','.join(emergency.categories)}",), emergency, scope
        )
    tier = RiskTier.LOW
    if _HIGH.search(lowered):
        tier = RiskTier.HIGH
        reasons.append("medication/dosing/diagnosis request")
    if scope.areas:
        tier = max(tier, RiskTier.HIGH)
        reasons.append(f"out-of-scope population: {','.join(scope.areas)}")
    if tier < RiskTier.MODERATE and _MODERATE.search(lowered):
        tier = RiskTier.MODERATE
        reasons.append("symptoms or test interpretation")
    if tier == RiskTier.LOW and not _EDUCATION.search(lowered) and not scope.non_medical:
        # Not clearly education: uncertain -> bump to the higher tier.
        tier = RiskTier.MODERATE
        reasons.append("uncertain classification -> higher tier")
    if not reasons:
        reasons.append("general health education")
    return RiskAssessment(tier, tuple(reasons), emergency, scope)
