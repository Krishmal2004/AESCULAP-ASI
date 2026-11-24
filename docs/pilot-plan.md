# AESCULAP-ASI: Phase 8 Pilot Plan

> Status: **DRAFT v0.1**. It needs owner, clinical-advisor and legal sign-off. Running a pilot needs people and approvals that software cannot provide. This document and the tooling below prepare for it.

## 1. Entry criteria (all required)

- [ ] M1 approved: persona and safety policy signed off (`docs/vision.md` §9 open decisions closed)
- [ ] Jurisdiction chosen; regulatory classification (SaMD / CDS exemption) assessed by counsel
- [ ] BAA/DPA with the LLM provider if any real PHI could be entered; otherwise synthetic cases only
- [ ] Ethics/IRB approval if real patients are involved
- [ ] `python -m eval all --llm claude` shows **every** gate measured and passing, including a licensed MedQA-format benchmark (`--file`) and a clinician panel score (`panel-export` → `panel-score`)
- [ ] Guideline sources license-approved and ingested; semantic embedder selected and benchmarked

## 2. Pilot design

| Item | Plan |
|---|---|
| Users | 5 to 10 primary-care clinicians, **clinician mode only** |
| Setting | Closed deployment and named accounts. Not patient-facing. |
| Duration | 4 to 6 weeks |
| Oversight | `AESCULAP_REVIEW_HIGH=1`, so high-risk answers wait for clinician approval in `/api/reviews` |
| Data | Synthetic or de-identified cases until legal review clears real data |

## 3. Running it

```bash
export AESCULAP_LLM=claude AESCULAP_REVIEW_HIGH=1 AESCULAP_ADMIN_TOKEN=<random secret>
python -m app --host 0.0.0.0 --port 8000     # behind TLS + SSO in any shared deployment
```

## 4. Feedback and failure capture

- Each answer has thumbs up/down and a failure type (incorrect, unsafe, missed red flag, bad citation, unclear, tone). These are stored in `app_data/feedback.jsonl` and linked to the audit trace.
- Weekly triage: pull every `unsafe` and `missing_red_flag` item, read the trace with `GET /api/trace/{id}`, and classify the root cause (retrieval, prompt, detector, knowledge gap).
- **Every safety incident becomes a new red-team case** in `eval/cases/redteam.yaml` (policy §7) before it is fixed.

## 5. Iterate loop

1. Fix: detector rules, prompts, critic checks, or knowledge sources (re-ingest with `python -m knowledge ingest`).
2. Re-run `python -m eval all` and check that no gate regressed.
3. Run the clinician panel again on changed behaviour.
4. Repeat the safety review before any expansion (new specialty, patient mode, new region).

## 6. Exit criteria

- No unsafe outcome attributed to the system
- Panel trust ≥ 4.0 and empathy ≥ 4.0
- All Phase 6 gates still pass on the final build
- Documented decision by owner and clinical advisor on whether and how to widen scope
