"""Co-mention knowledge graph.

IMPORTANT: edges here are *candidate associations* found by two entities appearing in
the same chunk. They are NOT validated clinical relationships. Every edge keeps the
supporting chunk ids so a human (or a later extraction model) can verify or curate it.
Never present an edge to a user as a medical fact without the cited source text.
"""

from __future__ import annotations

import itertools
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx
import yaml

from knowledge.models import Chunk

ENTITY_TYPES = {"disease", "symptom", "drug", "test"}
MAX_EVIDENCE = 20


@dataclass(frozen=True)
class Entity:
    id: str
    name: str
    type: str
    synonyms: tuple[str, ...] = ()
    codes: dict[str, str] = field(default_factory=dict)


def load_lexicon(path: Path) -> list[Entity]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entities: list[Entity] = []
    for item in raw.get("entities", []):
        if item["type"] not in ENTITY_TYPES:
            raise ValueError(f"{item['id']}: invalid entity type {item['type']!r}")
        entities.append(
            Entity(
                id=item["id"],
                name=item["name"],
                type=item["type"],
                synonyms=tuple(item.get("synonyms", [])),
                codes={k: str(v) for k, v in (item.get("codes") or {}).items()},
            )
        )
    return entities


class EntityMatcher:
    def __init__(self, entities: Iterable[Entity]) -> None:
        self._patterns: list[tuple[Entity, re.Pattern[str]]] = []
        for ent in entities:
            names = sorted({ent.name, *ent.synonyms}, key=len, reverse=True)
            body = "|".join(re.escape(n) for n in names)
            pattern = re.compile(rf"(?<![A-Za-z0-9])(?:{body})(?![A-Za-z0-9])", re.IGNORECASE)
            self._patterns.append((ent, pattern))

    def find(self, text: str) -> set[str]:
        return {ent.id for ent, pat in self._patterns if pat.search(text)}


def build_graph(entities: list[Entity], chunks: Iterable[Chunk]) -> nx.Graph:
    graph: nx.Graph = nx.Graph()
    for ent in entities:
        graph.add_node(ent.id, name=ent.name, type=ent.type, codes=ent.codes, mentions=0)
    matcher = EntityMatcher(entities)
    for chunk in chunks:
        found = sorted(matcher.find(chunk.text))
        for eid in found:
            graph.nodes[eid]["mentions"] += 1
        for a, b in itertools.combinations(found, 2):
            if not graph.has_edge(a, b):
                graph.add_edge(
                    a,
                    b,
                    relation=f"{graph.nodes[a]['type']}-{graph.nodes[b]['type']} co-mention",
                    weight=0,
                    evidence=[],
                )
            edge = graph.edges[a, b]
            edge["weight"] += 1
            if len(edge["evidence"]) < MAX_EVIDENCE and chunk.chunk_id not in edge["evidence"]:
                edge["evidence"].append(chunk.chunk_id)
    return graph


def neighbors(graph: nx.Graph, entity_id: str, min_weight: int = 1) -> list[dict[str, Any]]:
    if entity_id not in graph:
        return []
    rows = [
        {
            "id": other,
            "name": graph.nodes[other]["name"],
            "type": graph.nodes[other]["type"],
            "weight": data["weight"],
            "evidence": list(data["evidence"]),
        }
        for other, data in graph[entity_id].items()
        if data["weight"] >= min_weight
    ]
    return sorted(rows, key=lambda r: (-r["weight"], r["id"]))


def save_graph(graph: nx.Graph, path: Path) -> None:
    payload = {
        "nodes": [{"id": n, **attrs} for n, attrs in graph.nodes(data=True)],
        "edges": [{"source": a, "target": b, **attrs} for a, b, attrs in graph.edges(data=True)],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_graph(path: Path) -> nx.Graph:
    payload = json.loads(path.read_text(encoding="utf-8"))
    graph: nx.Graph = nx.Graph()
    for node in payload["nodes"]:
        attrs = {k: v for k, v in node.items() if k != "id"}
        graph.add_node(node["id"], **attrs)
    for edge in payload["edges"]:
        attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
        graph.add_edge(edge["source"], edge["target"], **attrs)
    return graph


def _cy(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def export_cypher(graph: nx.Graph, path: Path, min_weight: int = 1) -> None:
    """Write a Cypher script to load the graph into Neo4j (no driver dependency)."""
    lines: list[str] = []
    for node, attrs in graph.nodes(data=True):
        if attrs["type"] not in ENTITY_TYPES:
            raise ValueError(f"invalid node type {attrs['type']!r}")
        label = attrs["type"].capitalize()
        lines.append(
            f"MERGE (n:{label} {{id: {_cy(node)}}}) SET n.name = {_cy(attrs['name'])}, "
            f"n.mentions = {int(attrs['mentions'])};"
        )
    for a, b, attrs in graph.edges(data=True):
        if attrs["weight"] < min_weight:
            continue
        evidence = "[" + ", ".join(_cy(e) for e in attrs["evidence"]) + "]"
        lines.append(
            f"MATCH (a {{id: {_cy(a)}}}), (b {{id: {_cy(b)}}}) "
            f"MERGE (a)-[r:CO_MENTIONED]-(b) "
            f"SET r.weight = {int(attrs['weight'])}, r.evidence = {evidence};"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
