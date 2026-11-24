"""Planner: breaks a case into reasoning tasks and tool calls.

Rule-based on purpose: the plan is auditable, deterministic and testable. The language
model composes the answer; it does not decide which tools touch patient data.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from agents.specialists import Specialist, route
from knowledge.graph.builder import EntityMatcher, load_lexicon

LEXICON = Path(__file__).resolve().parent.parent / "knowledge" / "graph" / "lexicon.yaml"


@dataclass
class Step:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    tasks: list[str] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    drugs: list[str] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)
    specialists: list[Specialist] = field(default_factory=list)

    def describe(self) -> dict[str, Any]:
        return {
            "tasks": self.tasks,
            "steps": [{"tool": s.tool, "args": s.args} for s in self.steps],
            "drugs": self.drugs,
            "missing_info": self.missing_info,
            "specialists": [s.name for s in self.specialists],
        }


@lru_cache(maxsize=1)
def _drug_matcher() -> tuple[EntityMatcher, dict[str, str]]:
    drugs = [e for e in load_lexicon(LEXICON) if e.type == "drug"]
    return EntityMatcher(drugs), {e.id: e.name for e in drugs}


def _num(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text, re.I)
    return float(m.group(1)) if m else None


_SYMPTOM = re.compile(
    r"\b(pain|ache|fever|cough|rash|swelling|dizz|nausea|vomit|diarrh|fatigue|tired|sore"
    r"|breath|headache|bleed|itch|lump|numb|palpitation|symptom|feel(ing)? (sick|unwell))\w*",
    re.I,
)
_DRUG_Q = re.compile(r"\b(drug|medication|medicine|tablet|pill|interact|side effect|dose|take)\w*", re.I)
_RISK_Q = re.compile(r"\b(risk|score|likelihood|chance|stratif)\w*", re.I)
_DIAG_Q = re.compile(r"\b(what is wrong|could it be|do i have|cause|differential|diagnos)\w*", re.I)
_DURATION = re.compile(r"\b(\d+|a|an|few|couple|several)\s*(hour|day|week|month|year)s?\b|since|for ages", re.I)


def make_plan(question: str, patient_context: Mapping[str, Any] | None = None) -> Plan:
    ctx = dict(patient_context or {})
    plan = Plan()
    text = question

    matcher, names = _drug_matcher()
    drugs = [names[i] for i in sorted(matcher.find(text))]
    for med in ctx.get("medications", []) or []:
        name = str(med.get("name") if isinstance(med, Mapping) else med).strip().lower()
        if name and name not in drugs:
            drugs.append(name)
    plan.drugs = drugs

    # Tasks
    symptomatic = bool(_SYMPTOM.search(text))
    if symptomatic or _DIAG_Q.search(text):
        plan.tasks += ["red_flags", "differential"]
    if drugs or _DRUG_Q.search(text):
        plan.tasks.append("drug_info")
    if ctx.get("labs"):
        plan.tasks.append("lab_interpretation")
    if _RISK_Q.search(text):
        plan.tasks.append("risk_stratification")
    if not plan.tasks:
        plan.tasks.append("education")

    # Tools
    if len(drugs) >= 2:
        plan.steps.append(Step("drug_interaction_check", {"drugs": drugs}))
    if ctx.get("labs"):
        plan.steps.append(Step("lab_interpreter", {"results": ctx["labs"]}))

    age = ctx.get("age") or _num(r"\b(\d{2,3})[- ]?(?:years?|yrs?|yo|y/o)\b", text)
    sex = ctx.get("sex") or (
        "female" if re.search(r"\b(female|woman|\d+\s?f)\b", text, re.I)
        else "male" if re.search(r"\b(male|man|\d+\s?m)\b", text, re.I) else None
    )
    weight = ctx.get("weight_kg") or _num(r"(\d{2,3}(?:\.\d+)?)\s?kg\b", text)
    height = ctx.get("height_cm") or _num(r"(\d{3}(?:\.\d+)?)\s?cm\b", text)
    creat = ctx.get("creatinine_mg_dl") or _num(r"creatinine (?:of |is )?(\d+(?:\.\d+)?)\s?mg/dl", text)
    sbp = ctx.get("sbp")
    dbp = ctx.get("dbp")
    bp = re.search(r"\b(\d{2,3})/(\d{2,3})\s?(mmhg)?\b", text, re.I)
    if bp and not sbp:
        sbp, dbp = float(bp.group(1)), float(bp.group(2))

    if weight and height:
        plan.steps.append(Step("bmi", {"weight_kg": weight, "height_cm": height}))
    if creat and age and sex:
        plan.steps.append(Step("egfr", {"creatinine_mg_dl": creat, "age": age, "sex": sex}))
    if sbp and dbp:
        plan.steps.append(Step("map", {"sbp": sbp, "dbp": dbp}))
    if re.search(r"atrial fibrillation|\bAF\b|CHA2DS2", text, re.I) and age and sex:
        plan.steps.append(
            Step(
                "cha2ds2_vasc",
                {
                    "age": age,
                    "sex": sex,
                    "hypertension": bool(re.search(r"hypertension|high blood pressure", text, re.I)),
                    "diabetes": bool(re.search(r"diabet", text, re.I)),
                    "chf": bool(re.search(r"heart failure", text, re.I)),
                    "stroke_tia": bool(re.search(r"stroke|\bTIA\b", text, re.I)),
                    "vascular": bool(re.search(r"vascular disease|myocardial infarction|PAD", text, re.I)),
                },
            )
        )
    if re.search(r"pneumonia|CURB", text, re.I) and age:
        plan.steps.append(Step("curb65", {"age": age, "confusion": bool(re.search(r"confus", text, re.I)),
                                          "sbp": sbp, "dbp": dbp}))

    # Ask before assuming (max 3, persona rule 1)
    if symptomatic and not age:
        plan.missing_info.append("your age")
    if symptomatic and not _DURATION.search(text):
        plan.missing_info.append("how long this has been going on")
    if "drug_info" in plan.tasks and not ctx.get("medications") and not ctx.get("allergies"):
        plan.missing_info.append("any other medicines you take and any allergies")
    plan.missing_info = plan.missing_info[:3]

    plan.specialists = route(text, drugs)
    return plan
