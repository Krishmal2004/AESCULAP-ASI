from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from knowledge.cli import main
from knowledge.config import Config
from knowledge.graph.builder import (
    build_graph,
    export_cypher,
    load_graph,
    load_lexicon,
    neighbors,
    save_graph,
)
from knowledge.models import Chunk
from knowledge.refresh import run, stale_sources
from knowledge.search import format_for_prompt, retrieve

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _write(inbox: Path, name: str, text: str) -> None:
    (inbox / name).write_text(text, encoding="utf-8")


def test_refresh_is_incremental(config: Config, inbox: Path) -> None:
    _write(inbox, "a.md", "---\ntitle: A\n---\ntestdrug is discussed alongside testitis here.")
    [report] = run(config, ["inbox"], now=T0)
    assert (report.new, report.updated, report.unchanged) == (1, 0, 0)

    [again] = run(config, ["inbox"], now=T0)
    assert (again.new, again.updated, again.unchanged) == (0, 0, 1)

    _write(inbox, "a.md", "---\ntitle: A\n---\nRevised text about testitis only.")
    _write(inbox, "b.md", "A second document about testache.")
    [changed] = run(config, ["inbox"], now=T0)
    assert (changed.new, changed.updated, changed.unchanged) == (1, 1, 0)

    hits = retrieve("revised testitis", k=5, config=config)
    assert not any("alongside" in h["text"] for h in hits)  # old version replaced


def test_license_gate_blocks_unapproved_and_planned_sources(config: Config, inbox: Path) -> None:
    _write(inbox, "a.md", "Some text.")
    by_id = {r.source_id: r for r in run(config, ["unreviewed", "planned"], now=T0)}
    assert by_id["unreviewed"].blocked == "license_status=needs_review"
    assert by_id["planned"].blocked == "no ingestor implemented"
    assert retrieve("text", config=config) == []


def test_default_run_only_touches_ready_sources(config: Config, inbox: Path) -> None:
    _write(inbox, "a.md", "Some text.")
    assert [r.source_id for r in run(config, now=T0)] == ["inbox"]


def test_unknown_source_raises(config: Config) -> None:
    with pytest.raises(KeyError):
        run(config, ["nope"])


def test_failure_in_one_source_is_reported_not_raised(config: Config, tmp_path: Path) -> None:
    broken = tmp_path / "broken.md"
    broken.write_text("x", encoding="utf-8")
    config.sources_file.write_text(
        "sources:\n"
        "  - {id: bad, name: Bad, license_status: approved, reviewed_by: t, enabled: true,"
        " ingestor: pubmed, params: {query: q}}\n",
        encoding="utf-8",
    )

    def boom(url: str, params: object) -> str:
        raise OSError("network down")

    [report] = run(config, fetch=boom, now=T0)  # type: ignore[arg-type]
    assert report.errors and "network down" in report.errors[0]


def test_retrieve_returns_citation_fields(config: Config, inbox: Path) -> None:
    _write(
        inbox,
        "g.md",
        "---\ntitle: Guideline G\ndate: 2024-02-02\nurl: https://example.org/g\n"
        "evidence_level: guideline\n---\nAdvice about testitis management.",
    )
    run(config, ["inbox"], now=T0)
    [hit] = retrieve("testitis management", k=1, config=config)
    assert hit["id"] == "S1"
    assert (hit["title"], hit["date"], hit["evidence_level"]) == (
        "Guideline G",
        "2024-02-02",
        "guideline",
    )
    assert hit["url"] == "https://example.org/g"
    assert hit["license"] == "test-license"
    assert "[S1] Guideline G" in format_for_prompt([hit])


def test_no_results_message() -> None:
    assert format_for_prompt([]) == "(no supporting evidence found)"


def test_embedder_switch_is_rejected(config: Config, inbox: Path) -> None:
    _write(inbox, "a.md", "Some text.")
    run(config, ["inbox"], now=T0)
    # Simulate an index built with a different embedder.
    manifest = json.loads(config.manifest_path.read_text(encoding="utf-8"))
    manifest["embedder"], manifest["dim"] = "sentence-transformers", 384
    config.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="embedder"):
        run(config, ["inbox"])


def test_staleness(config: Config, inbox: Path) -> None:
    assert stale_sources(config, now=T0) == ["inbox"]  # never run
    _write(inbox, "a.md", "Some text.")
    run(config, ["inbox"], now=T0)
    assert stale_sources(config, now=T0 + timedelta(days=3)) == []
    assert stale_sources(config, now=T0 + timedelta(days=8)) == ["inbox"]


def test_graph_comention_and_roundtrip(config: Config, tmp_path: Path) -> None:
    entities = load_lexicon(config.lexicon_file)
    chunks = [
        Chunk("c1", "d", 0, "Testdrug is used for test inflammation.", {}),
        Chunk("c2", "d", 1, "TESTDRUG may cause testache. Testitis is unrelated.", {}),
        Chunk("c3", "d", 2, "Nothing relevant here.", {}),
    ]
    graph = build_graph(entities, chunks)
    assert graph.nodes["drug:testdrug"]["mentions"] == 2
    assert graph.edges["disease:testitis", "drug:testdrug"]["weight"] == 2
    assert graph.edges["disease:testitis", "drug:testdrug"]["evidence"] == ["c1", "c2"]
    top = neighbors(graph, "drug:testdrug")
    assert top[0]["id"] == "disease:testitis"
    assert neighbors(graph, "drug:testdrug", min_weight=3) == []
    assert neighbors(graph, "missing") == []

    path = tmp_path / "g.json"
    save_graph(graph, path)
    assert load_graph(path).edges["disease:testitis", "drug:testdrug"]["weight"] == 2


def test_word_boundaries_prevent_partial_matches(config: Config) -> None:
    entities = load_lexicon(config.lexicon_file)
    graph = build_graph(entities, [Chunk("c", "d", 0, "megatestdrugs and testitiss", {})])
    assert graph.nodes["drug:testdrug"]["mentions"] == 0


def test_cypher_export_escapes_quotes(config: Config, tmp_path: Path) -> None:
    graph = build_graph(
        load_lexicon(config.lexicon_file), [Chunk("c'1", "d", 0, "testdrug testitis", {})]
    )
    out = tmp_path / "g.cypher"
    export_cypher(graph, out)
    text = out.read_text(encoding="utf-8")
    assert "MERGE (n:Drug {id: 'drug:testdrug'})" in text
    assert "c\\'1" in text
    assert "CO_MENTIONED" in text


def test_real_lexicon_loads() -> None:
    entities = load_lexicon(Path("knowledge/graph/lexicon.yaml"))
    assert len({e.id for e in entities}) == len(entities)


def test_cli_end_to_end(
    config: Config, inbox: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(inbox, "a.md", "Testdrug and testitis appear together.")
    monkeypatch.setenv("AESCULAP_DATA_DIR", str(config.data_dir))
    monkeypatch.setenv("AESCULAP_SOURCES", str(config.sources_file))
    monkeypatch.setenv("AESCULAP_LEXICON", str(config.lexicon_file))

    assert main(["sources"]) == 0
    assert "BLOCKED unreviewed" in capsys.readouterr().out
    assert main(["ingest", "--source", "inbox"]) == 0
    assert main(["ingest", "--source", "unreviewed"]) == 1  # explicit blocked request fails
    capsys.readouterr()
    assert main(["search", "testdrug"]) == 0
    assert "[S1]" in capsys.readouterr().out
    assert main(["graph", "--entity", "drug:testdrug"]) == 0
    assert "disease:testitis" in capsys.readouterr().out
    assert main(["status"]) == 0
