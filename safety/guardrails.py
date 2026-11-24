"""Input and output guardrails (policy sections 2 and 3).

Input checks classify what the user is asking for (prohibited content, jailbreaks).
Output checks inspect a draft answer for policy violations before it is shown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------- input checks

_INJECTION = re.compile(
    r"(ignore|disregard|forget|override) (all |any |the |your )?(previous|prior|above|earlier|system)"
    r"( instructions| rules| prompt)?"
    r"|you are (now )?(a |an )?(real|licensed|human) (doctor|physician)"
    r"|pretend (to be|you are) (a |an )?(real |licensed |human )?(doctor|physician)"
    r"|developer mode|jailbreak|\bDAN\b|no (safety|restrictions|rules)"
    r"|reveal (your|the) (system )?prompt|act as my doctor and prescribe",
    re.IGNORECASE,
)

_HARM_REQUEST = re.compile(
    r"(lethal|fatal|deadly) (dose|amount|quantity)"
    r"|how (much|many) .{0,40}(to (die|kill)|would kill|is fatal|is lethal|to overdose)"
    r"|(best|easiest|painless|quickest) way to (die|kill (myself|yourself|someone)|end my life)"
    r"|how (do i|to|can i) (kill|poison|hurt) (someone|somebody|my|him|her|them)"
    r"|(poison|harm) (someone|somebody) without",
    re.IGNORECASE,
)

_PRESCRIBE_REQUEST = re.compile(
    r"(prescribe|write (me )?a prescription|give me (a |some )?(prescription|antibiotics|opioids)"
    r"|what dose should i (take|give)|how (much|many) .{0,30} should i (take|give)"
    r"|should i (stop|start|increase|decrease|double|change) (taking )?(my )?\w+"
    r"|can i stop (taking )?my)",
    re.IGNORECASE,
)

_DIAGNOSIS_REQUEST = re.compile(
    r"(just )?tell me (exactly )?what (i have|it is|is wrong)|give me (a|the|my) (final )?diagnosis"
    r"|diagnose me|do i have \w+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class InputFlags:
    prompt_injection: bool = False
    harm_request: bool = False
    prescribe_request: bool = False
    diagnosis_request: bool = False

    def as_list(self) -> list[str]:
        return [k for k, v in self.__dict__.items() if v]


def check_input(text: str) -> InputFlags:
    return InputFlags(
        prompt_injection=bool(_INJECTION.search(text)),
        harm_request=bool(_HARM_REQUEST.search(text)),
        prescribe_request=bool(_PRESCRIBE_REQUEST.search(text)),
        diagnosis_request=bool(_DIAGNOSIS_REQUEST.search(text)),
    )


def contains_injection(text: str) -> bool:
    """Used on retrieved documents and records: they are data, never instructions."""
    return bool(_INJECTION.search(text))


# --------------------------------------------------------------- output checks

_PRESCRIBING = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\byou should (take|start|stop|increase|decrease|double|switch to) (taking )?\w+",
        r"\b(take|give|use) \d+(\.\d+)?\s?(mg|mcg|µg|g|ml|units?|tablets?|pills?)\b",
        r"\bi (am )?(prescrib|recommend you take|recommend taking)",
        r"\bstop taking your\b",
        r"\bi('ll| will) prescribe\b",
        r"\byour dose (should|is) be\b",
    )
]
_FINAL_DIAGNOSIS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\byou (definitely |certainly |clearly )?have (a |an )?(?!any\b|to\b|a few\b|some\b|questions?\b)"
        r"[a-z]+(itis|osis|emia|oma|pathy|disease|syndrome|infection|diabetes|cancer|failure)\b",
        r"\bmy diagnosis is\b",
        r"\bthe diagnosis is\b",
        r"\byou are suffering from\b",
        r"\bthis is definitely\b",
    )
]
_DOCTOR_CLAIM = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bi am a (licensed |qualified |real |board[- ]certified )?(doctor|physician|nurse|gp)\b",
        r"\bi'm a (licensed |qualified |real |board[- ]certified )?(doctor|physician|nurse|gp)\b",
        r"\bin my (clinical )?(experience|practice) (as a|treating|with patients)",
        r"\bi have (seen|treated) (many |lots of )?patients\b",
        r"\bas your doctor\b",
    )
]
_HARM_CONTENT = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(lethal|fatal) dose (is|of .{0,30} is)\s+\d",
        r"\bto (kill yourself|end your life),? (you could|you can|take)",
    )
]
_OVERCONFIDENT = re.compile(
    r"\b(definitely|certainly|without (a )?doubt|100%|guaranteed|it'?s (probably )?nothing"
    r"|nothing to worry about)\b",
    re.IGNORECASE,
)
_CITATION = re.compile(r"\[(S\d+)\]")


@dataclass
class OutputReport:
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cited_ids: list[str] = field(default_factory=list)
    unknown_citations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def cited_ids(text: str) -> list[str]:
    seen: list[str] = []
    for cid in _CITATION.findall(text):
        if cid not in seen:
            seen.append(cid)
    return seen


def check_output(text: str, valid_source_ids: set[str] | None = None) -> OutputReport:
    report = OutputReport()
    for pat in _PRESCRIBING:
        if pat.search(text):
            report.violations.append("prescribing_or_dosing")
            break
    for pat in _FINAL_DIAGNOSIS:
        if pat.search(text):
            report.violations.append("final_diagnosis")
            break
    for pat in _DOCTOR_CLAIM:
        if pat.search(text):
            report.violations.append("claims_to_be_doctor")
            break
    for pat in _HARM_CONTENT:
        if pat.search(text):
            report.violations.append("harmful_content")
            break
    if _OVERCONFIDENT.search(text):
        report.warnings.append("overconfident_language")

    report.cited_ids = cited_ids(text)
    if valid_source_ids is not None:
        report.unknown_citations = [c for c in report.cited_ids if c not in valid_source_ids]
        if report.unknown_citations:
            report.violations.append("fabricated_citation")
    return report
