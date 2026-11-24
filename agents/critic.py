"""Critic: a second pass that checks a draft for errors and missed red flags.

Deterministic checks always run. When an LLM critic is supplied it adds a model review on
top; its findings can only ADD issues, never clear deterministic ones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from safety.grounding import check_grounding
from safety.guardrails import check_output
from safety.risk import RiskAssessment, RiskTier

_WARNING_SIGNS = re.compile(
    r"stiff neck|neck stiffness|fever.{0,30}rash|rash.{0,30}fever|blood in (stool|urine|vomit)"
    r"|black (stool|tarry)|weight loss|night sweats|confus|fainted|faint(ing)?"
    r"|worse at night|getting worse|sudden",
    re.I,
)
_URGENT_ADVICE = re.compile(r"urgent|same[- ]day|emergency|immediately|right away|promptly", re.I)
_JARGON = re.compile(
    r"\b(aetiology|etiology|differential diagnosis|contraindicated|idiopathic|prophylaxis"
    r"|pharmacokinetic|nephrotoxic|hepatotoxic|sequelae|comorbidit|titrat)\w*",
    re.I,
)
_NEXT_STEP = re.compile(
    r"next step|see a|speak (to|with)|contact|call|visit|appointment|clinician", re.I
)


@dataclass
class CriticReport:
    issues: list[str] = field(default_factory=list)
    hard: bool = False  # policy violation (must revise or block)

    @property
    def ok(self) -> bool:
        return not self.issues


class Critic:
    def __init__(self, llm_review: Any = None) -> None:
        self.llm_review = llm_review  # optional callable(draft, question) -> list[str]

    def review(
        self,
        draft: str,
        *,
        question: str,
        valid_ids: set[str],
        risk: RiskAssessment,
        mode: str,
    ) -> CriticReport:
        report = CriticReport()
        out = check_output(draft, valid_ids)
        for v in out.violations:
            report.issues.append(f"policy violation: {v.replace('_', ' ')}")
            report.hard = True
        for w in out.warnings:
            report.issues.append(f"{w.replace('_', ' ')}: soften certainty and state confidence")

        grounding = check_grounding(draft, valid_ids)
        for sent in grounding.ungrounded[:5]:
            report.issues.append(f"unsupported claim (add a valid [S#] or remove): {sent[:160]}")
        if grounding.ungrounded:
            report.hard = True

        if _WARNING_SIGNS.search(question) and not _URGENT_ADVICE.search(draft):
            report.issues.append(
                "missed red flag: question contains warning signs but the draft gives no "
                "urgent-care safety net"
            )
        if risk.tier >= RiskTier.HIGH and not _NEXT_STEP.search(draft):
            report.issues.append("high-risk topic without a clear next step to a clinician")
        if mode == "patient" and len(_JARGON.findall(draft)) >= 2:
            report.issues.append("too much jargon for patient mode; use plain language")

        if self.llm_review is not None:
            try:
                report.issues.extend(self.llm_review(draft, question))
            except Exception as exc:  # the model critic is advisory
                report.issues.append(f"(llm critic unavailable: {exc.__class__.__name__})")
        return report
