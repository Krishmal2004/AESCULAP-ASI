# AESCULAP-ASI — Safety Policy

> Status: **DRAFT v0.1** — requires owner and clinical-advisor approval (Milestone M1).
> This policy is binding on all later phases. Phase 5 turns it into enforceable code and tests.

## 1. Purpose

AESCULAP-ASI is a **clinical decision-support** system. It informs; licensed humans decide.

## 2. Hard Prohibitions ("Never")

The system must **never**:

1. **Issue a final diagnosis** without human clinician confirmation. It may offer a *differential* with probabilities/evidence labelled as suggestions.
2. **Prescribe** medication or set individual doses, or instruct a patient to start, stop, or change a prescribed medication.
3. **Present itself as a licensed doctor** or claim a medical license, credentials, or personal clinical experience.
4. **Discourage or delay emergency care** when red flags are present.
5. **State a medical claim without a traceable source** from the knowledge base; if none is found it must say so.
6. **Fabricate** citations, study results, drug data, or lab reference ranges.
7. **Provide self-harm methods**, lethal-dose guidance for self-harm, or instructions facilitating harm to others.
8. **Write to or alter** patient records, orders, or external systems (read-only access only in v1).
9. **Use or retain** user health data for training without explicit, revocable consent.
10. **Share** identifiable patient data with third parties outside the declared processing chain.

## 3. Mandatory Behaviours ("Always")

1. **Emergency escalation** — on detecting chest pain, stroke signs (FAST), severe breathing difficulty, anaphylaxis, severe bleeding, overdose, or suicidal/self-harm ideation, interrupt normal flow and show an immediate escalation message (call local emergency number / crisis line) before anything else.
2. **Disclaimer & severity-based referral** — every response carries a decision-support disclaimer; advice to see a clinician scales with severity (self-care → routine visit → urgent → emergency).
3. **Calibrated uncertainty** — express confidence; abstain ("I'm not sure") when evidence is weak, conflicting, or outside scope; never inflate certainty.
4. **Cite sources** with source, date, and evidence level for each medical claim.
5. **Ask before assuming** — request missing critical information (age, pregnancy, allergies, current medications, duration) before risk-relevant advice.
6. **Flag out-of-scope** cases (paediatrics, pregnancy, oncology, etc., until covered) and refer to a human.
7. **Audit log** — record inputs, retrieved sources, tool calls, critic findings, and safety-gate decisions for every response.

## 4. Risk Tiers & Human Oversight

| Tier | Examples | Required handling |
|---|---|---|
| **Critical** | Emergencies, self-harm, suspected life-threatening conditions | Immediate escalation message; log; no further speculative advice |
| **High** | Drug interactions, dosing questions, pregnancy, paediatrics, abnormal critical labs, new diagnosis suggestions | Critic + safety gate; **human review** before delivery in pilot; clinician-only in v1 |
| **Moderate** | Differential for common conditions, test interpretation | Citations + uncertainty; recommend clinician follow-up |
| **Low** | General health education, definitions | Citations + disclaimer |

Safety Gate rule: **if classification is uncertain, treat as the higher tier.**

## 5. Privacy & Data Handling

- Minimise data collected; de-identify before logging or indexing where possible.
- Encrypt in transit and at rest.
- No user data used for training or fine-tuning without explicit consent; consent is revocable.
- Retention limits and deletion on request (GDPR erasure).
- Vendor/LLM provider must be covered by appropriate agreements (BAA / DPA) before handling real PHI.
- Development and evaluation use **synthetic or public de-identified data only** until legal review is complete.

## 6. Fairness

- Test performance across age, sex/gender, and ethnicity; gaps above the threshold in `vision.md` block release.
- Do not infer or use protected attributes beyond clinical relevance.

## 7. Testing & Release Gates

- A red-team suite (Phase 5) must cover every item in §2 and §3; **100% pass on critical cases** is required to release.
- No expansion (new specialty, new user group, new region) without repeating the safety review.
- Any safety incident triggers a documented review, root-cause fix, and a new regression test.

## 8. Governance

| Role | Responsibility |
|---|---|
| Project owner | Approves policy and changes |
| Clinical advisor (to be appointed) | Reviews medical content, red-team cases, thresholds |
| Privacy/legal reviewer (to be appointed) | Regulatory and data-protection sign-off |

Policy changes are versioned in git and require owner + clinical-advisor approval.

## 9. Disclaimer Text (v1 draft)

> *AESCULAP-ASI provides decision support based on published evidence. It is not a substitute for professional medical judgment, does not provide a final diagnosis or prescription, and must not be used in an emergency. If you may be experiencing a medical emergency, call your local emergency number immediately.*
