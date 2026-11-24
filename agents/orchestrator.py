"""Orchestrator: Input -> Triage -> Planner -> Tools/Specialists -> Reasoner -> Critic
-> Safety Gate -> Response. Every step is written to the audit log."""

from __future__ import annotations

import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agents import tools as T
from agents.audit import AuditLog
from agents.critic import Critic
from agents.memory import LongTermMemory, SessionMemory
from agents.planner import Plan, make_plan
from agents.review import ReviewQueue
from core.llm import LLM, LLMRefusal, get_llm
from core.prompt import normalise_mode
from core.reasoner import Reasoner, Retriever
from safety.disclaimer import emergency_phrase, ensure_disclaimer
from safety.emergency import escalation_message
from safety.fairness import neutralise
from safety.gate import Decision, apply_gate, safe_fallback
from safety.guardrails import check_input, cited_ids
from safety.risk import RiskTier, assess_risk

MAX_REVISIONS = 2


@dataclass
class ChatRequest:
    message: str
    mode: str | None = None
    session_id: str = "default"
    patient_context: dict[str, Any] | None = None
    locale: str | None = None
    language: str = "en"
    user_id: str | None = None
    consent_memory: bool = False


@dataclass
class ChatResponse:
    answer: str
    decision: str
    risk_tier: str
    mode: str
    trace_id: str
    confidence: str = "n/a"
    citations: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    critic_issues: list[str] = field(default_factory=list)
    plan: dict[str, Any] = field(default_factory=dict)
    review_id: str | None = None
    notices: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Settings:
    data_dir: Path = Path(os.environ.get("AESCULAP_APP_DATA", "app_data"))
    require_review_for_high: bool = os.environ.get("AESCULAP_REVIEW_HIGH", "0") == "1"
    persist: bool = True


class Orchestrator:
    def __init__(
        self,
        llm: LLM | None = None,
        retriever: Retriever | None = None,
        settings: Settings | None = None,
        critic: Critic | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.llm = llm or get_llm()
        self.reasoner = Reasoner(self.llm, retriever)
        self.critic = critic or Critic()
        d = self.settings.data_dir
        p = self.settings.persist
        self.audit = AuditLog(d / "audit.jsonl" if p else None)
        self.reviews = ReviewQueue(d / "reviews.jsonl" if p else None)
        self.sessions = SessionMemory()
        self.long_term = LongTermMemory(d / "memory")

    # ------------------------------------------------------------------ helpers

    def _run_tools(self, plan: Plan, trace: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for step in plan.steps:
            try:
                if step.tool in T.CALCULATORS:
                    out = T.CALCULATORS[step.tool](**step.args)
                elif step.tool == "drug_interaction_check":
                    out = T.drug_interaction_check(self.reasoner.retriever, **step.args)
                elif step.tool == "lab_interpreter":
                    out = T.lab_interpreter(**step.args)
                else:
                    raise T.ToolError(f"unknown tool {step.tool}")
            except (T.ToolError, TypeError) as exc:
                out = {"tool": step.tool, "error": str(exc), "summary": ""}
            self.audit.log(trace, "tool", {"tool": step.tool, "args": step.args, "result": out})
            results.append(out)
        return results

    def _finish(self, req: ChatRequest, resp: ChatResponse) -> ChatResponse:
        self.sessions.add_turn(req.session_id, "user", req.message)
        self.sessions.add_turn(req.session_id, "assistant", resp.answer)
        self.audit.log(
            resp.trace_id,
            "response",
            {
                "decision": resp.decision,
                "risk_tier": resp.risk_tier,
                "confidence": resp.confidence,
                "citations": [c["chunk_id"] for c in resp.citations if "chunk_id" in c],
                "review_id": resp.review_id,
            },
        )
        return resp

    # ------------------------------------------------------------------ main flow

    def handle(self, req: ChatRequest) -> ChatResponse:
        trace = uuid.uuid4().hex[:16]
        mode = normalise_mode(req.mode)
        self.audit.log(
            trace, "input", {"message": req.message, "mode": mode, "session": req.session_id}
        )

        # 1. Triage: emergencies interrupt everything (policy 3.1).
        risk = assess_risk(req.message)
        flags = check_input(req.message)
        self.audit.log(
            trace,
            "triage",
            {"tier": risk.tier.label, "reasons": list(risk.reasons), "flags": flags.as_list()},
        )
        if risk.tier == RiskTier.CRITICAL:
            return self._finish(
                req,
                ChatResponse(
                    escalation_message(risk.emergency, req.locale),
                    Decision.ESCALATE.value,
                    risk.tier.label,
                    mode,
                    trace,
                ),
            )

        # 2. Prohibited requests (policy 2.7).
        if flags.harm_request:
            text = (
                "I can't help with that. I don't provide information that could be used to "
                "harm yourself or anyone else.\n\nIf you're having thoughts of harming yourself, "
                "you're not alone: please contact a crisis line or call "
                f"{emergency_phrase(req.locale)} now, and reach out to someone you trust. "
                "If someone has taken too much of a medicine, call emergency services or "
                "poison control right away."
            )
            return self._finish(
                req, ChatResponse(text, Decision.BLOCK.value, RiskTier.CRITICAL.label, mode, trace)
            )

        notices: list[str] = []
        if flags.prompt_injection:
            notices.append(
                "I can't change how I work or act as a licensed doctor, but I'm happy to help "
                "within my rules."
            )
        if flags.prescribe_request:
            notices.append(
                "I can't prescribe or set a personal dose. I can share general, cited "
                "information to discuss with your prescriber or pharmacist."
            )
        if flags.diagnosis_request:
            notices.append(
                "I can't give a final diagnosis, as that needs an examination by a clinician. "
                "I can describe possibilities and what a clinician would check."
            )

        # 3. Scope (policy 3.6).
        if risk.scope.non_medical:
            return self._finish(
                req,
                ChatResponse(
                    risk.scope.message(), Decision.ALLOW.value, risk.tier.label, mode, trace
                ),
            )
        if risk.scope.areas:
            notices.append(risk.scope.message())

        # 4. Context (read-only) + memory.
        ctx = dict(T.ehr_reader(req.patient_context))
        if req.user_id:
            ctx = {**self.long_term.recall(req.user_id), **ctx}
        ctx = self.sessions.update_context(req.session_id, ctx)

        # 5. Plan, tools, specialists, evidence.
        plan = make_plan(req.message, ctx)
        self.audit.log(trace, "plan", plan.describe())
        tool_results = self._run_tools(plan, trace)
        neutral = neutralise(req.message)  # protected attributes never steer retrieval
        queries = [neutral] + [q for s in plan.specialists for q in s.queries(neutral)]
        evidence = self.reasoner.retrieve(queries)
        self.audit.log(
            trace,
            "retrieval",
            {
                "queries": queries,
                "chunks": [(e["id"], e.get("chunk_id"), e["score"]) for e in evidence],
            },
        )

        # 6. Reason -> critic -> revise.
        feedback: list[str] = []
        issues: list[str] = []
        result = None
        try:
            for attempt in range(MAX_REVISIONS + 1):
                result = self.reasoner.answer(
                    req.message,
                    mode=mode,
                    evidence=evidence,
                    tasks=plan.tasks + [s.focus for s in plan.specialists],
                    tool_results=[t for t in tool_results if "error" not in t],
                    patient_context=ctx,
                    missing_info=plan.missing_info,
                    critic_feedback=feedback,
                    locale=req.locale,
                    language=req.language,
                    focus_terms=plan.drugs,
                    search_text=neutral,
                )
                critique = self.critic.review(
                    result.text,
                    question=req.message,
                    valid_ids=result.source_ids,
                    risk=risk,
                    mode=mode,
                )
                issues = critique.issues
                self.audit.log(trace, "critic", {"attempt": attempt, "issues": issues})
                if critique.ok:
                    break
                feedback = issues
        except LLMRefusal as exc:
            self.audit.log(trace, "llm_refusal", {"reason": str(exc)})
            return self._finish(
                req,
                ChatResponse(
                    safe_fallback(req.locale, "the request could not be processed safely"),
                    Decision.BLOCK.value,
                    risk.tier.label,
                    mode,
                    trace,
                ),
            )
        assert result is not None

        # 7. Safety gate.
        gate = apply_gate(
            result.text,
            risk,
            result.source_ids,
            locale=req.locale,
            require_review_for_high=self.settings.require_review_for_high,
        )
        self.audit.log(
            trace,
            "gate",
            {
                "decision": gate.decision.value,
                "violations": gate.violations,
                "warnings": gate.warnings,
                "faithfulness": gate.faithfulness,
            },
        )

        cited = set(cited_ids(gate.text))
        citations = [e for e in result.evidence if e["id"] in cited]
        answer = gate.text
        if notices and gate.decision != Decision.BLOCK:
            answer = "\n\n".join(notices) + "\n\n" + answer
        review_id = None
        if gate.decision == Decision.REVIEW:
            review_id = self.reviews.submit(
                trace, req.message, answer, {"risk": risk.tier.label, "mode": mode}
            )
            answer = ensure_disclaimer(
                "This question is high-risk, so my answer is being held for review by a "
                f"clinician before it is shared (review id {review_id}). If your situation is "
                "urgent, please contact a clinician or pharmacist directly.",
                req.locale,
            )

        if req.user_id and req.consent_memory:
            keep: dict[str, Any] = {
                k: ctx[k] for k in ("age", "sex", "allergies", "medications") if k in ctx
            }
            self.long_term.remember(req.user_id, keep, consent=True)

        return self._finish(
            req,
            ChatResponse(
                answer=answer,
                decision=gate.decision.value,
                risk_tier=risk.tier.label,
                mode=mode,
                trace_id=trace,
                confidence=result.confidence.level,
                citations=[
                    {
                        k: e.get(k)
                        for k in (
                            "id",
                            "chunk_id",
                            "title",
                            "source",
                            "url",
                            "date",
                            "evidence_level",
                            "score",
                            "text",
                        )
                    }
                    for e in citations
                ],
                tool_results=tool_results,
                critic_issues=issues,
                plan=plan.describe(),
                review_id=review_id,
                notices=notices,
            ),
        )
