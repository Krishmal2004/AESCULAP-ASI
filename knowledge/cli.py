"""Command line: python -m knowledge <command>."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from knowledge.config import Config
from knowledge.graph.builder import export_cypher, load_graph, neighbors
from knowledge.refresh import Manifest, run, stale_sources
from knowledge.search import format_for_prompt, retrieve
from knowledge.sources import load_sources


def _cmd_sources(config: Config, _: argparse.Namespace) -> int:
    for s in load_sources(config.sources_file):
        state = "READY " if s.ingestible else "BLOCKED"
        why = "" if s.ingestible else f" ({s.blocker()})"
        print(f"{state} {s.id:<16} license={s.license_status:<12}{why}")
    return 0


def _cmd_ingest(config: Config, args: argparse.Namespace) -> int:
    reports = run(config, args.source or None, with_graph=not args.no_graph)
    for r in reports:
        print(r.summary())
        for err in r.errors:
            print(f"  ! {err}")
    if not reports:
        print("No ingestible sources. Approve a source license in knowledge/sources.yaml.")
    return 1 if any(r.errors or (r.blocked and args.source) for r in reports) else 0


def _cmd_search(config: Config, args: argparse.Namespace) -> int:
    results = retrieve(args.query, k=args.k, config=config, source=args.source)
    print(json.dumps(results, indent=2) if args.json else format_for_prompt(results))
    return 0


def _cmd_graph(config: Config, args: argparse.Namespace) -> int:
    graph = load_graph(config.graph_path)
    if args.cypher:
        export_cypher(graph, Path(args.cypher), min_weight=args.min_weight)
        print(f"Wrote {args.cypher}")
        return 0
    if not args.entity:
        print(f"{graph.number_of_nodes()} entities, {graph.number_of_edges()} co-mention edges")
        return 0
    for row in neighbors(graph, args.entity, args.min_weight):
        print(f"{row['weight']:>4}  {row['id']}  ({row['name']})")
    print("Note: edges are candidate co-mentions, not validated clinical relationships.")
    return 0


def _cmd_status(config: Config, _: argparse.Namespace) -> int:
    manifest = Manifest.load(config.manifest_path)
    print(f"documents indexed: {len(manifest.docs)}  embedder: {manifest.embedder or 'n/a'}")
    for sid, info in sorted(manifest.sources.items()):
        print(f"  {sid}: last run {info['last_run']}")
    stale = stale_sources(config)
    print("stale sources: " + (", ".join(stale) if stale else "none"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="knowledge", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sources", help="list sources and license/ingest status").set_defaults(
        func=_cmd_sources
    )

    p = sub.add_parser("ingest", help="ingest/refresh sources (incremental)")
    p.add_argument("--source", action="append", help="source id (repeatable); default: all ready")
    p.add_argument("--no-graph", action="store_true", help="skip graph rebuild")
    p.set_defaults(func=_cmd_ingest)

    p = sub.add_parser("search", help="query the knowledge base")
    p.add_argument("query")
    p.add_argument("-k", type=int, default=5)
    p.add_argument("--source")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_search)

    p = sub.add_parser("graph", help="inspect or export the co-mention graph")
    p.add_argument("--entity", help="entity id, e.g. drug:metformin")
    p.add_argument("--min-weight", type=int, default=1)
    p.add_argument("--cypher", help="write a Neo4j Cypher script to this path")
    p.set_defaults(func=_cmd_graph)

    sub.add_parser("status", help="index and freshness status").set_defaults(func=_cmd_status)

    args = parser.parse_args(argv)
    return int(args.func(Config.from_env(), args))
