"""Safety Gate: the last control before a response reaches the user.

Decisions:
  escalate  emergency detected -> escalation message only (policy 3.1)
  block     a hard prohibition was violated -> safe replacement message
  review    high-risk output held for human review (pilot setting, policy section 4)
  allow     delivered, with the disclaimer guaranteed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from safety.disclaimer import ensure_disclaimer
from safety.emergency import escalation_message
from safety.grounding import check_grounding
from safety.guardrails import check_output
from safety.risk import RiskAssessment, RiskTier


class Decision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REVIEW = "review"
    ESCALATE = "escalate"


@dataclass
class GateResult:
    decision: Decision
    text: str
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    faithfulness: float = 1.0


MIN_FAITHFULNESS = 0.95  # docs/vision.md citation-faithfulness target


def safe_fallback(locale: str | None, reason: str) -> str:
    return ensure_disclaimer(
        "I'm not able to give a safe, evidence-backed answer to that as written "
        f"({reason}). A clinician or pharmacist who can review your full situation is the "
        "right person to help. If you'd like, I can share general, cited background "
        "information or help you prepare questions for them.",
        locale,
    )


def apply_gate(
    draft: str,
    risk: RiskAssessment,
    valid_source_ids: set[str],
    *,
    locale: str | None = None,
    require_review_for_high: bool = False,
) -> GateResult:
    if risk.tier == RiskTier.CRITICAL and risk.emergency.is_emergency:
        return GateResult(Decision.ESCALATE, escalation_message(risk.emergency, locale))

    out = check_output(draft, valid_source_ids)
    grounding = check_grounding(draft, valid_source_ids)
    violations = list(out.violations)
    if grounding.faithfulness < MIN_FAITHFULNESS:
        violations.append("unsupported_claims")

    if violations:
        return GateResult(
            Decision.BLOCK,
            safe_fallback(locale, "it did not pass safety checks"),
            violations,
            out.warnings,
            grounding.faithfulness,
        )

    text = ensure_disclaimer(draft, locale)
    if require_review_for_high and risk.tier >= RiskTier.HIGH:
        return GateResult(Decision.REVIEW, text, [], out.warnings, grounding.faithfulness)
    return GateResult(Decision.ALLOW, text, [], out.warnings, grounding.faithfulness)
