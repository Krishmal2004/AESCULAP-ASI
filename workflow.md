# AESCULAP-ASI — Build Workflow

> An agentic AI "doctor mind": human-doctor character + deep medical knowledge + autonomous reasoning.
> **Scope:** clinical decision support with human oversight. It does not replace a licensed doctor.

---

## Phase 0 — Vision & Scope

- [ ] Define the mission: who is the user (patient, clinician, student)?
- [ ] Pick the first specialty (e.g. general medicine) before going "ASI-wide"
- [ ] Define success metrics (accuracy on medical benchmarks, safety score, user trust)
- [ ] Write the safety policy: what the system will never do (no final diagnosis without a human, no prescribing)
- [ ] Check legal and regulatory needs (HIPAA/GDPR, medical device rules in your country)

**Output:** `docs/vision.md`, `docs/safety-policy.md`

---

## Phase 1 — Doctor Character Design

Define the human-doctor persona.

- [ ] Personality: calm, empathetic, honest about uncertainty
- [ ] Communication style: plain language for patients, technical for clinicians
- [ ] Bedside manner rules: ask before assuming, explain the why, never alarm needlessly
- [ ] Ethics: Hippocratic principles (do no harm, privacy, consent)
- [ ] Write the master system prompt

**Output:** `character/persona.md`, `character/system_prompt.md`

---

## Phase 2 — Medical Knowledge Base

| Source | Use |
|---|---|
| PubMed / PMC open access | Research literature |
| Clinical guidelines (WHO, NICE, CDC) | Standard of care |
| Drug databases (openFDA, DrugBank, RxNorm) | Interactions, dosing |
| Ontologies (SNOMED CT, ICD-10/11, UMLS) | Standard terminology |
| Medical textbooks (licensed or open) | Foundational knowledge |

Steps:
- [ ] Collect and license-check each source
- [ ] Clean and chunk documents, keeping metadata (source, date, evidence level)
- [ ] Build embeddings and a vector database (Qdrant / pgvector / Chroma)
- [ ] Build a knowledge graph (diseases ↔ symptoms ↔ drugs ↔ tests)
- [ ] Set up a refresh pipeline so knowledge stays current

**Output:** `knowledge/` pipeline, vector DB, graph DB

---

## Phase 3 — Core Reasoning Model

- [ ] Choose the base model (latest Claude model via API, or an open-weight model)
- [ ] Build RAG: retrieve evidence, then answer with citations
- [ ] Add clinical reasoning prompts: differential diagnosis, red-flag screening, risk stratification
- [ ] Add uncertainty calibration: the model says "I'm not sure" when evidence is weak
- [ ] Optional: fine-tune or add adapters on medical Q&A data

**Output:** `core/reasoner.py`, evaluation baseline

---

## Phase 4 — Agentic Layer

Turn the model into an agent that plans and acts.

```
Patient/Clinician input
        │
   ┌────▼─────┐
   │ Planner  │  breaks the case into steps
   └────┬─────┘
        │
   ┌────▼──────────────────────────────┐
   │ Tools                             │
   │  • Knowledge search (RAG)         │
   │  • Drug interaction checker       │
   │  • Lab/imaging result interpreter │
   │  • Guideline lookup               │
   │  • EHR/record reader (read-only)  │
   │  • Calculator (BMI, eGFR, scores) │
   └────┬──────────────────────────────┘
        │
   ┌────▼─────┐
   │ Critic   │  second agent checks for errors and missed red flags
   └────┬─────┘
        │
   ┌────▼──────────┐
   │ Safety Gate   │  blocks unsafe output, escalates to a human
   └────┬──────────┘
        ▼
   Final response
```

- [ ] Build the planner, tool executor, critic, and safety gate
- [ ] Add multi-agent specialists (cardiology, neurology, pharmacology) coordinated by an orchestrator
- [ ] Add memory: patient context within a session, consented long-term memory
- [ ] Log every step for auditability

**Output:** `agents/` with planner, tools, critic, orchestrator

---

## Phase 5 — Safety, Ethics & Guardrails (runs alongside Phases 3–6)

- [ ] Emergency detection (chest pain, stroke signs, suicidal ideation) → immediate escalation message
- [ ] Mandatory disclaimer and "see a doctor" logic by severity
- [ ] Hallucination checks: every medical claim must trace to a retrieved source
- [ ] Bias testing across age, gender, ethnicity
- [ ] Privacy: de-identification, encryption, no training on user data without consent
- [ ] Human-in-the-loop review for high-risk outputs

**Output:** `safety/` rules, red-team test suite

---

## Phase 6 — Evaluation

- [ ] Benchmarks: MedQA, MedMCQA, PubMedQA, MMLU-medical
- [ ] Clinician review panel scoring real-style cases
- [ ] Red-teaming for dangerous advice
- [ ] Track: accuracy, citation faithfulness, refusal quality, empathy score
- [ ] Set pass thresholds before moving on

**Output:** `eval/` harness, report

---

## Phase 7 — Interface

- [ ] Chat UI (web first), voice later
- [ ] Show citations and confidence on each answer
- [ ] "Explain like I'm a patient" / "clinician mode" toggle
- [ ] Multilingual support

**Output:** `app/`

---

## Phase 8 — Pilot & Iterate

- [ ] Closed pilot with clinicians
- [ ] Collect feedback and failure cases
- [ ] Retrain, re-index, and fix prompts
- [ ] Repeat the safety review before each expansion

---

## Suggested Project Structure

```
AESCULAP-ASI/
├── workflow.md
├── docs/            vision, safety policy, architecture
├── character/       persona, system prompt
├── knowledge/       ingestion, embeddings, graph
├── core/            reasoner, RAG
├── agents/          planner, tools, critic, orchestrator
├── safety/          guardrails, emergency rules
├── eval/            benchmarks, red-team tests
└── app/             UI and API
```

## Suggested Tech Stack

| Layer | Option |
|---|---|
| LLM | Claude API (or open-weight alternative) |
| Agent framework | Claude Agent SDK / LangGraph |
| Vector DB | Qdrant or pgvector |
| Graph DB | Neo4j |
| Backend | Python + FastAPI |
| Frontend | Next.js |
| Infra | Docker, GitHub Actions |

## Milestone Checklist

- [ ] M1: Persona + safety policy approved
- [ ] M2: Knowledge base searchable with citations
- [ ] M3: Single agent answers medical questions with sources
- [ ] M4: Multi-agent system with critic and safety gate
- [ ] M5: Benchmarks passed + clinician review
- [ ] M6: Pilot launched

## Rule of Thumb

Build narrow and safe first (one specialty, decision support), prove it works, then widen toward the ASI vision.
