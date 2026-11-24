"""Clinical reasoning task instructions added to the user turn."""

from __future__ import annotations

TASKS: dict[str, str] = {
    "differential": (
        "Task: build a differential diagnosis as SUGGESTIONS for a clinician to confirm. "
        "Order by likelihood and by danger; name must-not-miss conditions. Label each with "
        "the evidence that supports it ([S#]) or say the evidence does not cover it."
    ),
    "red_flags": (
        "Task: screen for red flags. List any present or not yet excluded, and the questions "
        "or checks that would exclude them. Red flags override everything else."
    ),
    "risk_stratification": (
        "Task: stratify risk (low / moderate / high) using only supplied data and any "
        "calculator results. State what missing data would change the stratification."
    ),
    "drug_info": (
        "Task: give general, cited drug information (interactions, contraindications, "
        "warnings). Do NOT set an individual dose or tell anyone to start, stop or change a "
        "medicine; direct them to a prescriber or pharmacist."
    ),
    "lab_interpretation": (
        "Task: interpret the supplied results against the supplied reference ranges only. "
        "Never invent a reference range. Say what a clinician would consider next."
    ),
    "education": "Task: explain the topic clearly using only the retrieved evidence.",
}


def task_instructions(tasks: list[str]) -> str:
    return "\n".join(TASKS[t] for t in tasks if t in TASKS) or TASKS["education"]
