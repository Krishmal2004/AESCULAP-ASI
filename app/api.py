"""Phase 7: HTTP API + web UI.

Run:  python -m app            (http://127.0.0.1:8000)
Admin endpoints (review queue, audit traces) need header ``X-Admin-Token`` matching the
``AESCULAP_ADMIN_TOKEN`` environment variable; they are disabled when it is unset.
"""

from __future__ import annotations

import hmac
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agents.orchestrator import ChatRequest, Orchestrator
from safety.privacy import redact

STATIC = Path(__file__).resolve().parent / "static"


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    mode: Literal["patient", "clinician"] = "patient"
    session_id: str = Field(default="default", max_length=64)
    patient_context: dict[str, Any] | None = None
    locale: str | None = Field(default=None, max_length=40)
    language: str = Field(default="en", max_length=12)
    user_id: str | None = Field(default=None, max_length=64)
    consent_memory: bool = False


class ReviewDecision(BaseModel):
    approve: bool
    reviewer: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=2000)


class FeedbackIn(BaseModel):
    trace_id: str = Field(max_length=32)
    rating: int = Field(ge=1, le=5)
    failure_type: Literal[
        "none", "wrong", "unsafe", "missing_red_flag", "bad_citation", "unclear", "tone", "other"
    ] = "none"
    comment: str = Field(default="", max_length=2000)
    role: Literal["patient", "clinician", "unknown"] = "unknown"


def create_app(orchestrator: Orchestrator | None = None) -> FastAPI:
    app = FastAPI(
        title="AESCULAP-ASI",
        version="0.1.0",
        description="Clinical decision support with human oversight. Not a doctor.",
    )
    state: dict[str, Any] = {"orch": orchestrator}
    lock = threading.Lock()

    def orch() -> Orchestrator:
        with lock:
            if state["orch"] is None:
                state["orch"] = Orchestrator()
            return state["orch"]

    def admin(x_admin_token: str | None = Header(default=None)) -> None:
        expected = os.environ.get("AESCULAP_ADMIN_TOKEN")
        if not expected:
            raise HTTPException(403, "admin endpoints disabled: set AESCULAP_ADMIN_TOKEN")
        if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
            raise HTTPException(401, "invalid admin token")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        o = orch()
        return {
            "status": "ok",
            "llm": o.llm.name,
            "review_high_risk": o.settings.require_review_for_high,
        }

    @app.post("/api/chat")
    def chat(body: ChatIn) -> dict[str, Any]:
        resp = orch().handle(ChatRequest(**body.model_dump()))
        return resp.to_dict()

    @app.post("/api/feedback")
    def feedback(body: FeedbackIn) -> dict[str, str]:
        o = orch()
        record = {
            **body.model_dump(),
            "comment": redact(body.comment),
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        o.audit.log(body.trace_id, "feedback", record)
        if o.settings.persist:
            path = o.settings.data_dir / "feedback.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {"status": "recorded"}

    @app.delete("/api/session/{session_id}")
    def clear_session(session_id: str) -> dict[str, str]:
        orch().sessions.clear(session_id)
        return {"status": "cleared"}

    @app.delete("/api/memory/{user_id}")
    def forget(user_id: str) -> dict[str, Any]:
        """Right to erasure: deletes consented long-term memory for this user."""
        try:
            deleted = orch().long_term.forget(user_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"deleted": deleted}

    @app.get("/api/reviews", dependencies=[Depends(admin)])
    def reviews() -> list[dict[str, Any]]:
        return orch().reviews.pending()

    @app.post("/api/reviews/{review_id}", dependencies=[Depends(admin)])
    def decide(review_id: str, body: ReviewDecision) -> dict[str, Any]:
        o = orch()
        if o.reviews.get(review_id) is None:
            raise HTTPException(404, "unknown review")
        try:
            item = o.reviews.decide(review_id, body.approve, body.reviewer, body.note)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        o.audit.log(
            item["trace_id"],
            "human_review",
            {"review_id": review_id, "status": item["status"], "reviewer": body.reviewer},
        )
        return item

    @app.get("/api/reviews/{review_id}/result")
    def review_result(review_id: str) -> dict[str, Any]:
        """What the user may see: the answer only once a clinician approved it."""
        item = orch().reviews.get(review_id)
        if item is None:
            raise HTTPException(404, "unknown review")
        if item["status"] == "approved":
            return {"status": "approved", "answer": item["answer"]}
        return {"status": item["status"]}

    @app.get("/api/trace/{trace_id}", dependencies=[Depends(admin)])
    def trace(trace_id: str) -> list[dict[str, Any]]:
        return orch().audit.trace(trace_id)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
