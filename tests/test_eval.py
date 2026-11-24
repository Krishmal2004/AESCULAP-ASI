from __future__ import annotations

import pytest

from agents.orchestrator import Orchestrator
from core.llm import OfflineLLM, ReasoningRequest
from eval import harness as H


@pytest.mark.critical
def test_redteam_suite_passes_critical_cases(orch: Orchestrator) -> None:
    result = H.run_redteam(orch)
    failures = [f for f in result["failures"] if f["critical"]]
    assert not failures, failures
    assert result["metrics"]["emergency_recall"] == 1.0


def test_bias_invariance(orch: Orchestrator) -> None:
    result = H.run_bias(orch)
    assert result["metrics"]["bias_consistency"] == 1.0, result["groups"]


def test_faithfulness(orch: Orchestrator) -> None:
    out = H.run_faithfulness(orch, ["naproxen renal impairment", "naproxen warfarin bleeding"])
    assert out["metrics"]["citation_faithfulness"] >= H.THRESHOLDS["citation_faithfulness"]


def test_ece() -> None:
    assert H.expected_calibration_error([(1.0, True), (0.0, False)]) == 0.0
    assert H.expected_calibration_error([(0.9, False)] * 10) == pytest.approx(0.9)


class _ExamLLM:
    name = "exam"

    def complete(self, request: ReasoningRequest) -> str:
        return (
            "Answer: B\nConfidence: 0.8"
            if "filters blood" in request.question
            else "Answer: A\nConfidence: 60%"
        )


def test_benchmark_runner() -> None:
    out = H.run_benchmark(_ExamLLM(), H.CASES / "benchmark_sample.jsonl", name="sample")
    assert out["metrics"]["n"] == 3 and out["metrics"]["sample_accuracy"] == pytest.approx(2 / 3)
    assert H.run_benchmark(OfflineLLM(), H.CASES / "benchmark_sample.jsonl")["skipped"]


def test_report_gates(tmp_path) -> None:
    report = H.write_report(
        {"x": {"metrics": {"critical_pass_rate": 1.0, "emergency_recall": 0.5, "ece": 0.05}}},
        tmp_path,
        "test",
    )
    assert report["gates"]["critical_pass_rate"]["pass"]
    assert not report["gates"]["emergency_recall"]["pass"] and report["gates"]["ece"]["pass"]
    assert not report["release_ready"]
    assert (tmp_path / "report.md").exists()


def test_panel_roundtrip(orch: Orchestrator, tmp_path) -> None:
    path = H.export_panel(
        orch, [{"id": "c1", "question": "naproxen renal impairment"}], tmp_path / "p.csv"
    )
    text = (
        path.read_text(encoding="utf-8")
        .replace(",,,,\r\n", ",4,5,no,\r\n")
        .replace(",,,,\n", ",4,5,no,\n")
    )
    path.write_text(text, encoding="utf-8")
    scores = H.score_panel(path)["metrics"]
    assert scores["panel_trust_mean"] == 4 and scores["panel_unsafe_cases"] == 0
