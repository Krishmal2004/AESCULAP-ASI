# AESCULAP-ASI: Architecture

> Status: **v0.1**. It describes the code as built. The safety policy (`docs/safety-policy.md`) is binding on every component.

## Request flow

```text
POST /api/chat (app/api.py)
   │
   ▼
Orchestrator.handle (agents/orchestrator.py), and every step is written to the audit log
   │
   ├─ 1. Triage      safety.risk.assess_risk   emergency? → ESCALATE (no differential, stop)
   ├─ 2. Input gate  safety.guardrails.check_input   harm request → BLOCK
   │                 jailbreak / prescribe / diagnose → add a notice, continue within rules
   ├─ 3. Scope       safety.scope   non-medical → redirect; paeds/pregnancy/oncology → notice
   ├─ 4. Context     agents.tools.ehr_reader (read-only, injection-stripped) + session memory
   │                 + consented long-term memory
   ├─ 5. Plan        agents.planner.make_plan   tasks, tool calls, missing info, specialists
   ├─ 6. Tools       calculators (BMI, eGFR CKD-EPI 2021, CHA2DS2-VASc, CURB-65, MAP),
   │                 drug_interaction_check (sources only), lab_interpreter (supplied ranges only)
   ├─ 7. Retrieval   core.reasoner.retrieve   demographic-neutral queries + specialist queries,
   │                 merged, injected text quarantined, renumbered S1..Sn
   ├─ 8. Reason      core.reasoner.answer → LLM (ClaudeLLM or OfflineLLM)
   ├─ 9. Critic      agents.critic   violations, unsupported claims, missed red flags,
   │                 overconfidence, jargon → revise (up to 2 times)
   └─10. Gate        safety.gate.apply_gate   BLOCK on any violation or faithfulness < 0.95;
                     REVIEW for high-risk when AESCULAP_REVIEW_HIGH=1; else ALLOW + disclaimer
```

## Packages

| Package | Phase | Role |
|---|---|---|
| `knowledge/` | 2 | Ingest, chunk, embed, index, graph, cited retrieval |
| `core/` | 3 | Prompt rendering from `character/system_prompt.md`, clinical task prompts, confidence calibration, LLM backends, RAG reasoner |
| `agents/` | 4 | Planner, tools, specialists (cardiology, neurology, pharmacology), critic, memory, audit log, review queue, orchestrator |
| `safety/` | 5 | Emergency detection, risk tiers, scope, input/output guardrails, grounding check, fairness (neutral retrieval), privacy redaction, disclaimer, safety gate |
| `eval/` | 6 | Red-team suite, bias invariance, citation faithfulness, MCQ benchmarks + ECE, clinician panel export/score, release gates |
| `app/` | 7 | FastAPI API, web UI (citations, confidence, patient/clinician toggle, languages, feedback) |

## LLM backends

| `AESCULAP_LLM` | Backend | Notes |
|---|---|---|
| `auto` (default) | Claude if credentials exist, else offline | |
| `claude` | `claude-opus-5-5` through the Anthropic SDK (`AESCULAP_MODEL` overrides) | Server-side refusal fallback enabled (`fallbacks: "default"`); refusals are handled as a safe block. **No real PHI until a BAA/DPA is in place.** |
| `offline` | Deterministic extractive composer | Only quotes retrieved evidence, so it cannot hallucinate. Used by tests and CI. English only. |

## Design decisions

- **Code-controlled workflow, not a free agent loop.** The planner is rule-based, so the tools that touch patient data are auditable and deterministic. The model composes the answer and the safety layer checks it.
- **Defence in depth.** The prompt states the rules, the critic asks for revisions, and the gate enforces the rules regardless of what the model wrote.
- **Evidence or silence.** Every clinical sentence needs a valid `[S#]`. A fabricated citation or ungrounded claim blocks the answer.
- **Retrieved text and records are data.** Instruction-shaped text is removed before it reaches the model.
- **Fairness.** Ethnicity, gender words and age phrasing are stripped from retrieval and evidence ranking. Clinically relevant values reach tools through structured context.
- **Privacy.** Audit logs, memory and feedback are redacted before they are written. Long-term memory needs explicit consent, and `DELETE /api/memory/{user_id}` erases it.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `AESCULAP_LLM` | `auto` | Backend choice |
| `AESCULAP_MODEL` | `claude-opus-5-5` | Claude model id |
| `AESCULAP_APP_DATA` | `app_data` | Audit log, review queue, feedback, memory |
| `AESCULAP_REVIEW_HIGH` | `0` | `1` holds high-risk answers for clinician approval (pilot) |
| `AESCULAP_ADMIN_TOKEN` | unset | Enables `/api/reviews` and `/api/trace` (header `X-Admin-Token`) |
| `AESCULAP_DATA_DIR`, `AESCULAP_EMBEDDER`, `AESCULAP_STORE` | see `knowledge/README.md` | Knowledge pipeline |

## Known limits

- Rule-based detectors (emergency, guardrails, grounding) favour recall and are English-only. A model-based classifier should be added as a second layer and evaluated, not used as a replacement.
- The hashing embedder is lexical. Use sentence-transformers before any pilot.
- The knowledge base holds openFDA labels only. Guideline sources are still blocked pending license review.
- The in-memory session store is per process. Use a shared store (Redis or Postgres) for multi-worker deployments.
