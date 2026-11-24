"""Language-model backends.

``ClaudeLLM``  production backend (Anthropic SDK). Needs credentials (ANTHROPIC_API_KEY or
               an ``ant auth login`` profile). Must be covered by a BAA/DPA before any real
               PHI is sent (docs/safety-policy.md section 5).
``OfflineLLM`` deterministic, dependency-free extractive composer. It only quotes retrieved
               evidence with citations, so it cannot hallucinate; used for tests, the eval
               harness and offline demos. Its answers are far less fluent than Claude's.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from safety.guardrails import check_output

DEFAULT_MODEL = "claude-opus-5-5"


@dataclass
class ReasoningRequest:
    question: str
    mode: str
    system: str
    user: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    confidence: str = "insufficient"
    missing_info: list[str] = field(default_factory=list)
    critic_feedback: list[str] = field(default_factory=list)
    language: str = "en"
    focus_terms: list[str] = field(default_factory=list)  # e.g. drugs named in the question
    search_text: str = ""  # demographic-neutral text used for evidence ranking


class LLMRefusal(RuntimeError):
    """The model declined the request (stop_reason == 'refusal')."""


class LLM(Protocol):
    name: str

    def complete(self, request: ReasoningRequest) -> str: ...


# --------------------------------------------------------------------------- Claude


class ClaudeLLM:
    name = "claude"

    def __init__(self, model: str | None = None, effort: str = "high") -> None:
        import anthropic  # optional dependency at import time

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("AESCULAP_MODEL", DEFAULT_MODEL)
        self.effort = effort

    def complete(self, request: ReasoningRequest) -> str:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=request.system,
            messages=[{"role": "user", "content": request.user}],
            output_config={"effort": self.effort},
            # On a safety-classifier decline, the API retries on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise LLMRefusal(getattr(response.stop_details, "explanation", None) or "refused")
        return "".join(b.text for b in response.content if b.type == "text").strip()


# --------------------------------------------------------------------------- Offline

_WORD = re.compile(r"[a-z0-9]+")
_SENT = re.compile(r"(?<=[.!?])\s+|\n+")
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "are", "for", "with", "on", "what",
    "how", "my", "i", "me", "do", "does", "can", "it", "be", "this", "that", "about", "should",
    "have", "has", "when", "which", "you", "your", "at", "as", "by", "from", "any", "there",
}


def _terms(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2}


_XREF = re.compile(
    r"\[[^\]]*\]|\(\s*(see\b[^)]*|\d+(\.\d+)*\s*)\)|^\s*\d+(\.\d+)*\s+|\b\d+\.\d+\s+(?=[A-Z])", re.I
)
_NON_TEXT = re.compile("\\(\\s*\\)|[^\\x20-\\x7e\\u00a0-\\u024f]")


def _best_sentences(question: str, text: str, n: int = 2) -> list[str]:
    q = _terms(question)
    scored: list[tuple[int, int, str]] = []
    for i, raw in enumerate(_SENT.split(text)):
        sent = " ".join(_XREF.sub(" ", raw.strip().lstrip("#")).split())
        sent = _NON_TEXT.sub("", sent).strip(" .;,:") + "."
        if len(sent) < 25 or len(sent) > 400:
            continue
        if not check_output(sent).ok:  # never quote dosing/diagnosis-shaped text verbatim
            continue
        overlap = len(q & _terms(sent))
        if overlap:
            scored.append((overlap, -i, sent if sent.endswith((".", "!", "?")) else sent + "."))
    scored.sort(reverse=True)
    return [s for _, _, s in scored[:n]]


class OfflineLLM:
    name = "offline-extractive"

    def complete(self, request: ReasoningRequest) -> str:
        patient = request.mode != "clinician"
        # Extractive output is grounded by construction, so critic feedback needs no rewrite.
        lines: list[str] = []
        if patient:
            lines.append("Thanks for your question. Here is what my sources say.")
        else:
            lines.append("**Summary (extractive, offline mode):**")

        findings: list[str] = []
        seen: set[str] = set()
        focus = [t.lower() for t in request.focus_terms]
        uncovered = [
            t for t in focus
            if not any(t in str(ev.get("title", "")).lower() for ev in request.evidence)
        ]
        for ev in request.evidence:
            title = str(ev.get("title", "")).lower()
            if focus and not any(t in title for t in focus):
                continue  # evidence about a different drug is not evidence for this question
            for sent in _best_sentences(request.search_text or request.question, ev.get("text", "")):
                if sent.lower() not in seen:
                    seen.add(sent.lower())
                    findings.append(f"{sent} [{ev['id']}]")
            if len(findings) >= 4:
                break

        tool_lines = [
            f"{t['tool']}: {t['summary']}" for t in request.tool_results if t.get("summary")
        ]

        if uncovered:
            lines.append(
                "I couldn't find supporting evidence in my sources about: "
                + ", ".join(uncovered) + "."
            )
        if request.confidence == "insufficient" or not findings:
            lines.append(
                "I'm not sure here. I couldn't find supporting evidence for that in my sources, "
                "so I won't guess."
            )
        else:
            lines.append("" if patient else "**Evidence:**")
            lines.extend(f"- {f}" for f in findings)
        if tool_lines:
            lines.append("**Tool results:**" if not patient else "Calculated values:")
            lines.extend(f"- {t}" for t in tool_lines)
        if request.missing_info:
            lines.append(
                "To help further, could you tell me: " + "; ".join(request.missing_info[:3]) + "?"
            )
        lines.append(f"**Confidence:** {request.confidence}.")
        if request.evidence and findings:
            lines.append("**Sources:**")
            used = {f.rsplit("[", 1)[1].rstrip("]") for f in findings}
            for ev in request.evidence:
                if ev["id"] in used:
                    lines.append(
                        f"- [{ev['id']}] {ev.get('title', '')} ({ev.get('source', '')}, "
                        f"{ev.get('date') or 'n/a'}, {ev.get('evidence_level', 'unspecified')})"
                    )
        lines.append(
            "**Next step:** please discuss this with a clinician or pharmacist who can examine "
            "you and review your history."
            if patient
            else "**Next step:** clinician to review against examination and local pathways."
        )
        if request.language and request.language != "en":
            lines.insert(
                0, f"(Offline mode answers in English only; requested language: {request.language}.)"
            )
        return "\n".join(line for line in lines if line is not None)


def get_llm(name: str | None = None) -> LLM:
    """``AESCULAP_LLM`` = claude | offline | auto (default: claude if credentials exist)."""
    choice = (name or os.environ.get("AESCULAP_LLM", "auto")).lower()
    if choice == "offline":
        return OfflineLLM()
    if choice == "claude":
        return ClaudeLLM()
    has_creds = any(
        os.environ.get(v) for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE")
    )
    if has_creds:
        try:
            return ClaudeLLM()
        except ImportError:
            pass
    return OfflineLLM()
