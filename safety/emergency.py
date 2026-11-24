"""Emergency detection (policy section 3.1).

Deliberately high-recall: a false alarm costs a sentence, a miss can cost a life.
Patterns are matched on lower-cased input. Negations ("no chest pain") are honoured
only for the simple "no/denies/without X" form; anything more ambiguous still triggers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from safety.disclaimer import emergency_phrase

# category -> regex fragments
_PATTERNS: dict[str, list[str]] = {
    "cardiac": [
        r"chest (pain|pressure|tightness|discomfort|heaviness)",
        r"crushing (pain|pressure)",
        r"pain (spreading|radiating) (to|down|into) (my |the )?(left )?(arm|jaw|neck|back)",
        r"heart attack",
    ],
    "stroke": [
        r"face (is )?(droop|drooping|numb)",
        r"(facial|face) droop",
        r"(sudden|suddenly).{0,40}(weak|weakness|numb|numbness|paraly)",
        r"(one|left|right) side (of my body )?(is )?(weak|numb|paraly)",
        r"(slurred|slurring) (speech|words)|can'?t (speak|talk) (properly|clearly)",
        r"\bstroke\b",
        r"worst headache (of my life|ever)|thunderclap headache",
    ],
    "breathing": [
        r"can'?t breathe|cannot breathe|unable to breathe",
        r"(severe|extreme|serious) (shortness of breath|breathlessness|difficulty breathing)",
        r"struggling to breathe|gasping for (air|breath)",
        r"(lips|face) (are |is |turning )?(blue|grey|gray)",
        r"choking",
    ],
    "anaphylaxis": [
        r"anaphyla",
        r"(throat|tongue|lips?) (is |are )?(swelling|swollen|closing)",
        r"swelling (of|in) (my |the )?(throat|tongue|face|lips)",
    ],
    "bleeding": [
        r"(severe|heavy|uncontrolled|won'?t stop|wont stop|can'?t stop) bleeding",
        r"bleeding (heavily|a lot|won'?t stop|that won'?t stop|profusely)",
        r"vomiting blood|coughing up (a lot of )?blood",
    ],
    "overdose": [
        r"overdos",
        r"took (too many|a lot of|an entire|the whole|all (of )?(my|the)) (pills|tablets|bottle)",
        r"swallowed (a bottle|too many|all)",
        r"\bpoison(ed|ing)\b",
    ],
    "consciousness": [
        r"(unconscious|unresponsive|passed out and|not waking up|won'?t wake up)",
        r"(having|had) a seizure|seizing|convuls",
    ],
    "self_harm": [
        r"(kill|hurt|harm) (myself|me)\b",
        r"suicid",
        r"end (my|it all|my life)",
        r"(want|wanting|going) to die",
        r"don'?t want to (live|be alive|wake up)",
        r"self[- ]harm|cutting myself",
        r"better off dead|no reason to live",
    ],
}

_NEGATION = re.compile(r"\b(no|denies|denied|without|not|never had)\s+(any\s+)?$")

_COMPILED = {cat: [re.compile(p) for p in pats] for cat, pats in _PATTERNS.items()}


@dataclass(frozen=True)
class EmergencyResult:
    is_emergency: bool
    categories: tuple[str, ...] = ()
    matches: tuple[str, ...] = ()

    @property
    def self_harm(self) -> bool:
        return "self_harm" in self.categories


def _negated(text: str, start: int) -> bool:
    window = text[max(0, start - 25) : start]
    return bool(_NEGATION.search(window))


def detect_emergency(text: str) -> EmergencyResult:
    lowered = " ".join(text.lower().split())
    cats: list[str] = []
    found: list[str] = []
    for cat, patterns in _COMPILED.items():
        for pat in patterns:
            for m in pat.finditer(lowered):
                if cat != "self_harm" and _negated(lowered, m.start()):
                    continue
                if cat not in cats:
                    cats.append(cat)
                found.append(m.group(0))
                break
    return EmergencyResult(bool(cats), tuple(cats), tuple(found))


def escalation_message(result: EmergencyResult, locale: str | None = None) -> str:
    """The first message on an emergency: act now, then brief support. No differential."""
    number = emergency_phrase(locale)
    if result.self_harm and len(result.categories) == 1:
        return (
            "I'm really sorry you're feeling this way, and I'm glad you told me. "
            f"Please contact a crisis line or call {number} right now, and if you can, "
            "reach out to someone you trust to be with you. If you are in immediate danger "
            "or have already hurt yourself, call emergency services now.\n\n"
            "You don't have to go through this alone. I'm here to keep talking while you "
            "reach out for help."
        )
    lines = [
        f"**This may be a medical emergency. Please call {number} now.**",
        "",
        "What you describe can be a sign of a serious condition that needs to be checked "
        "in person immediately. Do not wait to see if it gets better, and do not drive "
        "yourself if you feel unwell.",
    ]
    if "anaphylaxis" in result.categories:
        lines.append(
            "If an adrenaline (epinephrine) auto-injector has been prescribed for you, "
            "follow its instructions while you wait for help."
        )
    if result.self_harm:
        lines.append(
            "If you are having thoughts of harming yourself, please also contact a crisis "
            "line and someone you trust."
        )
    lines.append("Stay with someone if you can until help arrives.")
    return "\n".join(lines)
