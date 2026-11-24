# AESCULAP-ASI

An agentic AI "doctor mind": a human-doctor character, deep medical knowledge, and autonomous reasoning, built for **clinical decision support with human oversight**.

> **Important:** AESCULAP-ASI does not replace a licensed doctor. It provides no final diagnoses and no prescriptions, and it must not be used in an emergency. If you may be experiencing a medical emergency, call your local emergency number immediately.

## Status

All software phases (2 to 7) are built and tested. The remaining gates need people: owner and clinical sign-off (M1), a licensed benchmark dataset, a clinician review panel, and a pilot.

| Phase | Description | Status |
|---|---|---|
| 0 | Vision & scope, safety policy | Draft, awaiting owner approval |
| 1 | Doctor character design | Draft, awaiting owner approval |
| 2 | Medical knowledge base | Built (openFDA live; guideline sources license-blocked) |
| 3 | Core reasoning model (RAG) | Built: `core/` |
| 4 | Agentic layer | Built: `agents/` |
| 5 | Safety, ethics & guardrails | Built: `safety/` + red-team suite |
| 6 | Evaluation | Harness built: `eval/`. MedQA-style benchmark and clinician panel not yet run |
| 7 | Interface | Built: `app/` (web UI + API) |
| 8 | Pilot & iterate | Plan and tooling ready: [`docs/pilot-plan.md`](docs/pilot-plan.md). Not started |

See [`workflow.md`](workflow.md) for the build plan and [`docs/architecture.md`](docs/architecture.md) for how it fits together.

## Architecture

```
Input → Triage (emergency, harm, scope) → Planner → Tools (RAG, drug interactions,
calculators, labs, read-only record) → Specialists → Reasoner (Claude) → Critic
→ Safety Gate → Response (citations, confidence, disclaimer) — every step audited
```

## Quick start

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest                                    # offline, synthetic data only

python -m knowledge ingest                # build the knowledge base (network)
python -m app                             # web UI at http://127.0.0.1:8000
python -m eval all                        # red-team, bias, faithfulness, benchmark gates
```

With no Anthropic credentials the system runs on a deterministic **offline extractive** backend that only quotes retrieved sources. To use Claude, set `ANTHROPIC_API_KEY` (or log in with `ant auth login`) and optionally `AESCULAP_LLM=claude`. Do not enter real patient data until a BAA/DPA and legal review are in place.

Docker:

```bash
docker build -t aesculap . && docker run -p 8000:8000 -v aesculap-data:/data aesculap
```

## Project structure

```
AESCULAP-ASI/
├── workflow.md      build plan
├── docs/            vision, safety policy, architecture, pilot plan
├── character/       persona, system prompt (loaded at runtime)
├── knowledge/       ingestion, embeddings, vector store, graph
├── core/            prompt, LLM backends, confidence, RAG reasoner
├── agents/          planner, tools, specialists, critic, memory, audit, review, orchestrator
├── safety/          emergency, risk tiers, scope, guardrails, grounding, fairness, privacy, gate
├── eval/            red-team / bias cases, harness, benchmarks, clinician panel
├── app/             FastAPI API and web UI
└── tests/           tests for phases 3–7 (knowledge/tests covers phase 2)
```

## Safety

Safety rules bind every phase. They are enforced in code, not only in the prompt. The system:

- never gives a final diagnosis without a human clinician
- never prescribes or sets individual doses
- never makes a medical claim without a traceable source (ungrounded answers are blocked)
- always escalates emergencies first and states its uncertainty
- logs every step for audit, redacted

Details: [`docs/safety-policy.md`](docs/safety-policy.md). Release needs **every** gate in `docs/vision.md` §6 to be measured and passed; `python -m eval all` reports which gates are still unmeasured.

## Tech stack

| Layer | Choice |
|---|---|
| LLM | Claude (`claude-opus-5-5`) through the Anthropic SDK, with an offline extractive fallback |
| Orchestration | Code-controlled workflow (`agents/orchestrator.py`) |
| Vector store | In-memory/JSON (default) or Chroma |
| Graph | networkx; Cypher export for Neo4j |
| Backend | Python + FastAPI |
| Frontend | Static HTML/JS served by FastAPI |
| Infra | Docker |

## Milestones

- [ ] M1: Persona + safety policy approved
- [x] M2: Knowledge base searchable with citations
- [x] M3: Single agent answers medical questions with sources
- [x] M4: Multi-agent system with critic and safety gate
- [ ] M5: Benchmarks passed + clinician review (harness ready; needs dataset and panel)
- [ ] M6: Pilot launched

## Data & Privacy

Development and evaluation use synthetic or public de-identified data only until legal review is complete. No user data is used for training. Long-term memory needs explicit consent and can be erased with `DELETE /api/memory/{user_id}`.

## Contributing

Changes to the safety policy need approval from the project owner and a clinical advisor. Each safety incident gets a documented review and a new red-team case in `eval/cases/redteam.yaml`.

## License

Not yet chosen. Each knowledge source is license-checked before use (`knowledge/sources.yaml`).
