from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from agents.orchestrator import Orchestrator, Settings  # noqa: E402
from app.api import create_app  # noqa: E402
from core.llm import OfflineLLM  # noqa: E402
from tests.conftest import fake_retriever  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AESCULAP_ADMIN_TOKEN", "secret")
    o = Orchestrator(
        llm=OfflineLLM(),
        retriever=fake_retriever,
        settings=Settings(data_dir=tmp_path, persist=True, require_review_for_high=True),
    )
    return TestClient(create_app(o))


def test_health_and_index(client: TestClient) -> None:
    assert client.get("/api/health").json()["llm"] == "offline-extractive"
    assert "Aesculap" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200


def test_chat(client: TestClient) -> None:
    r = client.post("/api/chat", json={"message": "naproxen renal impairment", "mode": "clinician"})
    body = r.json()
    assert r.status_code == 200 and body["decision"] == "allow" and body["citations"]


def test_chat_validation(client: TestClient) -> None:
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "hi", "mode": "god"}).status_code == 422


@pytest.mark.critical
def test_emergency_via_api(client: TestClient) -> None:
    body = client.post("/api/chat", json={"message": "I can't breathe", "locale": "112"}).json()
    assert body["decision"] == "escalate" and "112" in body["answer"]


def test_review_workflow_and_admin_auth(client: TestClient) -> None:
    body = client.post("/api/chat", json={"message": "can I take naproxen with warfarin?"}).json()
    rid = body["review_id"]
    assert body["decision"] == "review" and rid
    assert client.get(f"/api/reviews/{rid}/result").json() == {"status": "pending"}
    assert client.get("/api/reviews").status_code == 401
    pending = client.get("/api/reviews", headers={"X-Admin-Token": "secret"}).json()
    assert [p["id"] for p in pending] == [rid]
    ok = client.post(
        f"/api/reviews/{rid}",
        headers={"X-Admin-Token": "secret"},
        json={"approve": True, "reviewer": "dr-test"},
    )
    assert ok.json()["status"] == "approved"
    result = client.get(f"/api/reviews/{rid}/result").json()
    assert result["status"] == "approved" and "warfarin" in result["answer"].lower()
    trace = client.get(f"/api/trace/{body['trace_id']}", headers={"X-Admin-Token": "secret"}).json()
    assert any(r["step"] == "human_review" for r in trace)


def test_admin_disabled_without_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AESCULAP_ADMIN_TOKEN")
    assert client.get("/api/reviews", headers={"X-Admin-Token": "x"}).status_code == 403


def test_feedback_and_erasure(client: TestClient, tmp_path) -> None:
    trace = client.post("/api/chat", json={"message": "what is hypertension"}).json()["trace_id"]
    r = client.post(
        "/api/feedback",
        json={
            "trace_id": trace,
            "rating": 2,
            "failure_type": "unclear",
            "comment": "email me a@b.com",
        },
    )
    assert r.json() == {"status": "recorded"}
    assert "a@b.com" not in (tmp_path / "feedback.jsonl").read_text(encoding="utf-8")
    client.post(
        "/api/chat",
        json={
            "message": "what is hypertension",
            "user_id": "u1",
            "consent_memory": True,
            "patient_context": {"age": 50},
        },
    )
    assert client.delete("/api/memory/u1").json() == {"deleted": True}
    assert client.delete("/api/memory/u1").json() == {"deleted": False}
