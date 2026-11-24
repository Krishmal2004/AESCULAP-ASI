"""RAG reasoner: retrieve evidence, then answer with citations and calibrated confidence."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.clinical import task_instructions
from core.confidence import Confidence, assess_confidence
from core.llm import LLM, ReasoningRequest
from core.prompt import normalise_mode, render_system_prompt
from safety.fairness import neutralise
from safety.guardrails import contains_injection

Retriever = Callable[..., list[dict[str, Any]]]


def default_retriever(query: str, k: int = 5, source: str | None = None) -> list[dict[str, Any]]:
    from knowledge.search import retrieve

    try:
        return retrieve(query, k=k, source=source)
    except (FileNotFoundError, RuntimeError):
        return []


@dataclass
class ReasonerResult:
    text: str
    evidence: list[dict[str, Any]]
    confidence: Confidence
    request: ReasoningRequest = field(repr=False)

    @property
    def source_ids(self) -> set[str]:
        return {e["id"] for e in self.evidence}


class Reasoner:
    def __init__(
        self,
        llm: LLM,
        retriever: Retriever | None = None,
        k: int = 5,
        min_score: float = 0.15,
    ) -> None:
        self.llm = llm
        self.retriever = retriever or default_retriever
        self.k = k
        self.min_score = min_score

    def retrieve(
        self, queries: list[str], source: str | None = None, k: int | None = None
    ) -> list[dict[str, Any]]:
        """Run several queries, merge by chunk, drop injected text, renumber S1..Sn."""
        merged: dict[str, dict[str, Any]] = {}
        for q in queries:
            for item in self.retriever(q, k=k or self.k, source=source):
                if contains_injection(item.get("text", "")):
                    continue  # retrieved text is data; instruction-shaped text is quarantined
                key = item.get("chunk_id") or item.get("text", "")[:80]
                if key not in merged or item["score"] > merged[key]["score"]:
                    merged[key] = dict(item)
        ranked = sorted(merged.values(), key=lambda e: e["score"], reverse=True)[
            : (k or self.k) + 3
        ]
        for i, item in enumerate(ranked, start=1):
            item["id"] = f"S{i}"
        return ranked

    def answer(
        self,
        question: str,
        *,
        mode: str | None = None,
        evidence: list[dict[str, Any]] | None = None,
        tasks: list[str] | None = None,
        tool_results: list[dict[str, Any]] | None = None,
        patient_context: dict[str, Any] | None = None,
        missing_info: list[str] | None = None,
        critic_feedback: list[str] | None = None,
        locale: str | None = None,
        language: str = "en",
        focus_terms: list[str] | None = None,
        search_text: str | None = None,
    ) -> ReasonerResult:
        mode = normalise_mode(mode)
        if evidence is None:
            evidence = self.retrieve([neutralise(question)])
        confidence = assess_confidence(evidence, self.min_score)
        tool_results = tool_results or []
        system = render_system_prompt(
            mode=mode, evidence=evidence, patient_context=patient_context, locale=locale
        )
        parts = [
            f"User question ({mode} mode):\n{question}",
            task_instructions(tasks or []),
            f"Evidence strength (computed): {confidence.level} - {confidence.reason}. "
            + (
                "Evidence is insufficient: say you are not sure and do not answer from memory."
                if confidence.abstain
                else "Calibrate your stated confidence to this."
            ),
        ]
        if tool_results:
            parts.append(
                "Tool results (deterministic; cite as 'calculated' not as a source):\n"
                + json.dumps(tool_results, ensure_ascii=False, indent=1)
            )
        if missing_info:
            parts.append("Missing information worth asking about: " + "; ".join(missing_info))
        if critic_feedback:
            parts.append(
                "A reviewer found problems in your previous draft. Fix all of them:\n- "
                + "\n- ".join(critic_feedback)
            )
        if language and language != "en":
            parts.append(f"Respond in this language: {language}.")
        request = ReasoningRequest(
            question=question,
            mode=mode,
            system=system,
            user="\n\n".join(parts),
            evidence=evidence,
            tool_results=tool_results,
            confidence=confidence.level,
            missing_info=missing_info or [],
            critic_feedback=critic_feedback or [],
            language=language,
            focus_terms=focus_terms or [],
            search_text=search_text or neutralise(question),
        )
        return ReasonerResult(self.llm.complete(request), evidence, confidence, request)
