# AESCULAP-ASI

An agentic AI "doctor mind": a human-doctor character, deep medical knowledge, and autonomous reasoning, built for **clinical decision support with human oversight**.

> **Important:** AESCULAP-ASI does not replace a licensed doctor. It provides no final diagnoses and no prescriptions, and it must not be used in an emergency. If you may be experiencing a medical emergency, call your local emergency number immediately.

## Status

Early stage. **Phase 0 (Vision & Scope) is drafted** and awaiting owner approval. No code exists yet.

| Phase | Description | Status |
|---|---|---|
| 0 | Vision & scope, safety policy | Draft |
| 1 | Doctor character design | Not started |
| 2 | Medical knowledge base | Not started |
| 3 | Core reasoning model (RAG) | Not started |
| 4 | Agentic layer | Not started |
| 5 | Safety, ethics & guardrails | Not started |
| 6 | Evaluation | Not started |
| 7 | Interface | Not started |
| 8 | Pilot & iterate | Not started |

See [`workflow.md`](workflow.md) for the full build plan and milestones.

## Vision

- **Primary user (assumed):** clinicians in general / primary-care medicine
- **Secondary user:** patients, with stricter safety rules, after the clinician-facing system passes evaluation
- **Approach:** narrow and safe first (one specialty, decision support), prove it works, then widen

Details: [`docs/vision.md`](docs/vision.md)

## Safety

Safety rules bind every phase. In short, the system:

- never gives a final diagnosis without a human clinician
- never prescribes or sets individual doses
- never makes a medical claim without a traceable source
- always escalates emergencies and states its uncertainty
- logs every step for audit

Details: [`docs/safety-policy.md`](docs/safety-policy.md)

## Planned Architecture

```
Input → Planner → Tools (RAG, drug checker, calculators, guidelines, read-only EHR)
      → Critic → Safety Gate → Response
```

## Planned Project Structure

```
AESCULAP-ASI/
├── workflow.md      build plan
├── docs/            vision, safety policy, architecture
├── character/       persona, system prompt
├── knowledge/       ingestion, embeddings, graph
├── core/            reasoner, RAG
├── agents/          planner, tools, critic, orchestrator
├── safety/          guardrails, emergency rules
├── eval/            benchmarks, red-team tests
└── app/             UI and API
```

Only `docs/` exists so far.

## Planned Tech Stack

| Layer | Option |
|---|---|
| LLM | Claude API (or open-weight alternative) |
| Agent framework | Claude Agent SDK / LangGraph |
| Vector DB | Qdrant or pgvector |
| Graph DB | Neo4j |
| Backend | Python + FastAPI |
| Frontend | Next.js |
| Infra | Docker, GitHub Actions |

## Milestones

- [ ] M1: Persona + safety policy approved
- [ ] M2: Knowledge base searchable with citations
- [ ] M3: Single agent answers medical questions with sources
- [ ] M4: Multi-agent system with critic and safety gate
- [ ] M5: Benchmarks passed + clinician review
- [ ] M6: Pilot launched

## Data & Privacy

Development and evaluation use synthetic or public de-identified data only until legal review is complete. No user data is used for training without explicit consent.

## Contributing

Changes to the safety policy require approval from the project owner and a clinical advisor. Safety incidents get a documented review and a new regression test.

## License

Not yet chosen. Knowledge sources will each be license-checked before use (Phase 2).
