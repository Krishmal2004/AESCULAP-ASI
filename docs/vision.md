# AESCULAP-ASI — Vision & Scope

> Status: **DRAFT v0.1** — assumptions marked `[ASSUMPTION]` need owner approval (Milestone M1).

## 1. Mission

Build an agentic AI "doctor mind" that combines a human-doctor character, deep medical knowledge, and autonomous reasoning to **support** clinical decision-making and health understanding. It augments licensed professionals; it does not replace them.

## 2. Users

| Priority | User | Need | Mode |
|---|---|---|---|
| Primary `[ASSUMPTION]` | **Clinician** (GP / primary care) | Evidence-backed differential, red-flag checks, guideline and drug-interaction lookup, with citations | Clinician mode |
| Secondary | **Patient / public** | Plain-language explanation of symptoms, results, and when to seek care | Patient mode (stricter safety) |
| Later | Medical student | Case-based learning, explanations | Out of scope for v1 |

Rationale: a clinician in the loop is the strongest safety control. Patient-facing use ships only after the clinician-facing system passes Phase 6 thresholds.

## 3. First Specialty

**General / primary-care medicine** `[ASSUMPTION]` — broad but well covered by open guidelines (WHO, NICE, CDC). Specialist agents (cardiology, neurology, pharmacology) are added in Phase 4 only after the generalist is proven.

## 4. In Scope (v1)

- Differential diagnosis suggestions with reasoning and evidence level
- Red-flag screening and risk stratification
- Guideline and drug-interaction lookup, clinical calculators (BMI, eGFR, scores)
- Cited answers drawn from a curated knowledge base
- Explicit uncertainty ("I'm not sure") when evidence is weak
- Read-only access to supplied patient context

## 5. Out of Scope (v1)

- Final diagnoses or treatment decisions without a human clinician
- Prescribing or dose-setting for individuals
- Writing to EHRs or ordering tests
- Emergency services replacement
- Image/DICOM diagnosis, voice, multi-language (later phases)

## 6. Success Metrics

Thresholds are **proposed** and must be fixed before Phase 6 begins (workflow: "set pass thresholds before moving on").

| Dimension | Metric | Proposed v1 target |
|---|---|---|
| Knowledge accuracy | MedQA (USMLE) | ≥ 85% |
| | MedMCQA / PubMedQA / MMLU-medical | Within 5 pts of best published baseline using same base model |
| Citation faithfulness | Claims traceable to retrieved source | ≥ 95% |
| Safety | Red-team dangerous-advice pass rate | 100% on critical set, ≥ 98% overall |
| | Emergency detection recall (chest pain, stroke, suicidality) | ≥ 99% on test set |
| Calibration | Expected calibration error / appropriate abstention | ECE ≤ 0.10 |
| Clinician trust | Panel score on real-style cases (1–5) | ≥ 4.0 mean, no case rated unsafe |
| Empathy / communication | Rubric score | ≥ 4.0 mean |
| Bias | Accuracy gap across age, gender, ethnicity | ≤ 3 pts |

## 7. Principles

1. **Narrow and safe first**, then widen toward the ASI vision.
2. **Human in the loop** for anything high-risk.
3. **Evidence or silence**: no medical claim without a traceable source.
4. **Honest uncertainty** over confident error.
5. **Privacy by default**; no training on user data without consent.
6. **Auditability**: every agent step is logged.

## 8. Regulatory & Legal Checklist

Jurisdiction is **not yet chosen** — to be decided by the owner. Open items:

- [ ] Target jurisdiction(s): `TBD`
- [ ] **HIPAA** (US) — applies if handling PHI on behalf of covered entities; requires BAAs with any vendor (including the LLM API provider) that sees PHI
- [ ] **GDPR** (EU/UK) — lawful basis, consent, data minimisation, right to erasure, DPIA for health data (special-category)
- [ ] **Medical device rules** — software that provides diagnosis/treatment recommendations may be Software as a Medical Device (FDA SaMD / EU MDR Class IIa+ / UK MHRA). Clinical Decision Support may qualify for exemption only if clinicians can independently review the basis for recommendations (e.g. FDA CDS criteria) — design citations and reasoning display accordingly
- [ ] Licensing review of every knowledge source (PubMed OA subset, textbooks, DrugBank terms)
- [ ] Liability / terms of use / mandatory disclaimers reviewed by counsel
- [ ] Ethics / IRB review before any pilot with real patients (Phase 8)

> This checklist is a starting point, not legal advice. Obtain qualified legal and regulatory review before any real-patient use.

## 9. Open Decisions for Owner

1. Confirm primary user = clinician, and specialty = general medicine.
2. Choose target jurisdiction(s).
3. Approve success-metric targets.
4. Base model choice (Phase 3) — affects PHI/BAA requirements.
