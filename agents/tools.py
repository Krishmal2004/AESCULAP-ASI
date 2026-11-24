"""Agent tools. Every tool is read-only and deterministic.

Calculators implement published formulas; their category labels are the standard
published bands. Tools never invent drug facts or reference ranges: interaction checks
return only what retrieved sources say, and lab interpretation requires supplied ranges.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from safety.guardrails import contains_injection

Retriever = Callable[..., list[dict[str, Any]]]
GUIDELINE_SOURCES = ("who_guidelines", "nice_guidelines", "cdc_guidelines")


class ToolError(ValueError):
    pass


def _require(value: float | None, name: str, lo: float, hi: float) -> float:
    if value is None:
        raise ToolError(f"missing {name}")
    v = float(value)
    if not (lo <= v <= hi) or math.isnan(v):
        raise ToolError(f"{name}={value} outside plausible range [{lo}, {hi}]")
    return v


# ------------------------------------------------------------------ calculators


def bmi(weight_kg: float, height_cm: float) -> dict[str, Any]:
    w = _require(weight_kg, "weight_kg", 2, 400)
    h = _require(height_cm, "height_cm", 40, 250) / 100
    value = round(w / (h * h), 1)
    if value < 18.5:
        band = "underweight"
    elif value < 25:
        band = "normal range"
    elif value < 30:
        band = "overweight"
    else:
        band = "obesity"
    return {
        "tool": "bmi",
        "value": value,
        "unit": "kg/m2",
        "category": band,
        "method": "WHO adult BMI bands",
        "summary": f"BMI {value} kg/m2 ({band}, WHO adult bands) (calculated)",
    }


def egfr_ckd_epi_2021(creatinine_mg_dl: float, age: float, sex: str) -> dict[str, Any]:
    """CKD-EPI 2021 race-free creatinine equation (adults)."""
    scr = _require(creatinine_mg_dl, "creatinine_mg_dl", 0.1, 20)
    a = _require(age, "age", 18, 120)
    female = str(sex).lower().startswith("f")
    kappa, alpha = (0.7, -0.241) if female else (0.9, -0.302)
    value = 142 * min(scr / kappa, 1) ** alpha * max(scr / kappa, 1) ** -1.200 * 0.9938**a
    if female:
        value *= 1.012
    value = round(value)
    stages = [(90, "G1"), (60, "G2"), (45, "G3a"), (30, "G3b"), (15, "G4"), (0, "G5")]
    stage = next(s for cut, s in stages if value >= cut)
    return {
        "tool": "egfr",
        "value": value,
        "unit": "mL/min/1.73m2",
        "category": stage,
        "method": "CKD-EPI 2021 (race-free); KDIGO GFR categories",
        "summary": f"eGFR {value} mL/min/1.73m2, KDIGO category {stage} (calculated)",
    }


def cha2ds2_vasc(
    age: float,
    sex: str,
    chf: bool = False,
    hypertension: bool = False,
    diabetes: bool = False,
    stroke_tia: bool = False,
    vascular: bool = False,
) -> dict[str, Any]:
    a = _require(age, "age", 18, 120)
    score = (
        (2 if a >= 75 else 1 if a >= 65 else 0)
        + (1 if str(sex).lower().startswith("f") else 0)
        + int(chf) + int(hypertension) + int(diabetes) + int(vascular) + (2 if stroke_tia else 0)
    )
    return {
        "tool": "cha2ds2_vasc",
        "value": score,
        "unit": "points",
        "method": "CHA2DS2-VASc (stroke risk in atrial fibrillation)",
        "summary": f"CHA2DS2-VASc {score} points (calculated); interpret with local guideline",
    }


def curb65(
    age: float,
    confusion: bool = False,
    urea_mmol_l: float | None = None,
    resp_rate: float | None = None,
    sbp: float | None = None,
    dbp: float | None = None,
) -> dict[str, Any]:
    a = _require(age, "age", 18, 120)
    score = int(confusion) + int(a >= 65)
    score += int(urea_mmol_l is not None and urea_mmol_l > 7)
    score += int(resp_rate is not None and resp_rate >= 30)
    score += int((sbp is not None and sbp < 90) or (dbp is not None and dbp <= 60))
    missing = [n for n, v in (("urea", urea_mmol_l), ("resp_rate", resp_rate), ("bp", sbp)) if v is None]
    note = f"; missing {', '.join(missing)} so score may be underestimated" if missing else ""
    return {
        "tool": "curb65",
        "value": score,
        "unit": "points",
        "method": "CURB-65 (community-acquired pneumonia severity)",
        "summary": f"CURB-65 {score} points (calculated){note}",
    }


def mean_arterial_pressure(sbp: float, dbp: float) -> dict[str, Any]:
    s = _require(sbp, "sbp", 40, 300)
    d = _require(dbp, "dbp", 20, 200)
    value = round(d + (s - d) / 3)
    return {
        "tool": "map",
        "value": value,
        "unit": "mmHg",
        "method": "MAP = DBP + (SBP - DBP)/3",
        "summary": f"Mean arterial pressure {value} mmHg (calculated)",
    }


CALCULATORS: dict[str, Callable[..., dict[str, Any]]] = {
    "bmi": bmi,
    "egfr": egfr_ckd_epi_2021,
    "cha2ds2_vasc": cha2ds2_vasc,
    "curb65": curb65,
    "map": mean_arterial_pressure,
}


# ------------------------------------------------------------------ evidence tools


def knowledge_search(retriever: Retriever, query: str, k: int = 5) -> list[dict[str, Any]]:
    return retriever(query, k=k)


def guideline_lookup(retriever: Retriever, query: str, k: int = 3) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for src in GUIDELINE_SOURCES:
        results.extend(retriever(query, k=k, source=src))
    return sorted(results, key=lambda r: r["score"], reverse=True)[:k]


def drug_interaction_check(retriever: Retriever, drugs: list[str]) -> dict[str, Any]:
    """Find sources that mention each pair together. Absence of evidence is not safety."""
    names = sorted({d.lower() for d in drugs if d})
    pairs: list[dict[str, Any]] = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            hits = retriever(f"drug interactions {a} {b}", k=8)
            both = [
                h for h in hits
                if re.search(rf"\b{re.escape(a)}\b", h["text"], re.I)
                and re.search(rf"\b{re.escape(b)}\b", h["text"], re.I)
            ]
            pairs.append(
                {"pair": [a, b], "evidence_chunks": [h["chunk_id"] for h in both], "found": bool(both)}
            )
    found = [p for p in pairs if p["found"]]
    summary = (
        "Sources mention together: " + "; ".join(" + ".join(p["pair"]) for p in found)
        if found
        else "No source in the knowledge base mentions these drugs together"
    )
    return {
        "tool": "drug_interaction_check",
        "pairs": pairs,
        "summary": summary + " (calculated). This is not proof of safety; ask a pharmacist.",
    }


def lab_interpreter(results: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Flag values against SUPPLIED reference ranges only."""
    rows: list[dict[str, Any]] = []
    for r in results:
        name = str(r.get("name", "?"))
        try:
            value = float(r["value"])
        except (KeyError, TypeError, ValueError):
            rows.append({"name": name, "flag": "unreadable value"})
            continue
        low, high = r.get("low"), r.get("high")
        if low is None and high is None:
            rows.append({"name": name, "value": value, "flag": "no reference range supplied"})
            continue
        flag = "within supplied range"
        if low is not None and value < float(low):
            flag = "below supplied range"
        elif high is not None and value > float(high):
            flag = "above supplied range"
        rows.append({"name": name, "value": value, "unit": r.get("unit", ""), "flag": flag})
    summary = "; ".join(f"{x['name']} {x.get('value', '')} {x['flag']}" for x in rows)
    return {"tool": "lab_interpreter", "results": rows, "summary": f"{summary} (calculated)"}


def ehr_reader(patient_context: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Read-only view of supplied patient context. Instruction-shaped text is dropped."""
    if not patient_context:
        return MappingProxyType({})
    clean: dict[str, Any] = {}
    for key, value in patient_context.items():
        if isinstance(value, str) and contains_injection(value):
            clean[key] = "[removed: instruction-like text in record]"
        else:
            clean[key] = value
    return MappingProxyType(clean)
