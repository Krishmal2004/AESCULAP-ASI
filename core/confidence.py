"""Uncertainty calibration from the retrieved evidence.

The model is told how strong the evidence is and must abstain ("I'm not sure") when it is
insufficient. Weights are a starting point and should be re-fit on Phase 6 calibration data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

EVIDENCE_WEIGHT = {
    "guideline": 1.0,
    "systematic-review": 1.0,
    "meta-analysis": 1.0,
    "rct": 0.9,
    "regulatory-label": 0.75,
    "cohort": 0.7,
    "abstract": 0.6,
    "case-report": 0.4,
    "unspecified": 0.4,
}


@dataclass(frozen=True)
class Confidence:
    level: str  # high | moderate | low | insufficient
    score: float
    reason: str

    @property
    def abstain(self) -> bool:
        return self.level == "insufficient"


def assess_confidence(evidence: list[dict[str, Any]], min_score: float = 0.15) -> Confidence:
    relevant = [e for e in evidence if float(e.get("score", 0.0)) >= min_score]
    if not relevant:
        return Confidence("insufficient", 0.0, "no sufficiently relevant evidence retrieved")
    weighted = sorted(
        (
            float(e["score"]) * EVIDENCE_WEIGHT.get(str(e.get("evidence_level")), 0.4)
            for e in relevant
        ),
        reverse=True,
    )[:3]
    support = min(1.0, len(relevant) / 3)
    score = round(min(1.0, (sum(weighted) / len(weighted)) * 1.6) * (0.6 + 0.4 * support), 3)
    if score >= 0.6:
        level = "high"
    elif score >= 0.35:
        level = "moderate"
    else:
        level = "low"
    return Confidence(level, score, f"{len(relevant)} relevant source(s); top-weighted score {score}")
