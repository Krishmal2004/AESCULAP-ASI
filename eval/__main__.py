"""python -m eval [redteam|bias|faithfulness|benchmark|panel-export|panel-score|all]"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agents.orchestrator import Orchestrator, Settings
from core.llm import get_llm
from eval import harness as H


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="eval", description=__doc__)
    p.add_argument(
        "suite",
        choices=[
            "redteam",
            "bias",
            "faithfulness",
            "benchmark",
            "panel-export",
            "panel-score",
            "all",
        ],
    )
    p.add_argument("--llm", default=None, help="claude | offline (default: auto)")
    p.add_argument("--file", type=Path, help="benchmark JSONL / panel CSV")
    p.add_argument("--name", help="benchmark name, e.g. medqa")
    p.add_argument("--limit", type=int)
    p.add_argument("--out", type=Path, default=Path("eval/reports"))
    args = p.parse_args(argv)

    llm = get_llm(args.llm)
    orch = Orchestrator(llm=llm, settings=Settings(persist=False))
    sections: dict[str, dict] = {}

    if args.suite in ("redteam", "all"):
        sections["redteam"] = H.run_redteam(orch)
    if args.suite in ("bias", "all"):
        sections["bias"] = H.run_bias(orch)
    if args.suite in ("faithfulness", "all"):
        sections["faithfulness"] = H.run_faithfulness(orch)
    if args.suite in ("benchmark", "all"):
        path = args.file or (H.CASES / "benchmark_sample.jsonl")
        sections["benchmark"] = H.run_benchmark(llm, path, args.limit, args.name)
    if args.suite == "panel-export":
        cases = [
            {"id": f"c{i}", "question": q} for i, q in enumerate(H.DEFAULT_FAITHFULNESS_QUESTIONS)
        ]
        out = H.export_panel(orch, cases, args.out / "panel.csv")
        print(f"Wrote {out}. Ask panel clinicians to fill trust/empathy/unsafe columns.")
        return 0
    if args.suite == "panel-score":
        if not args.file:
            p.error("--file panel.csv required")
        sections["panel"] = H.score_panel(args.file)

    report = H.write_report(sections, args.out, llm.name)
    print(
        json.dumps({k: report[k] for k in ("gates", "unmeasured_gates", "release_ready")}, indent=2)
    )
    print(f"Report: {args.out / 'report.md'}")
    measured_fail = any(not g["pass"] for g in report["gates"].values())
    return 1 if measured_fail else 0


if __name__ == "__main__":
    sys.exit(main())
