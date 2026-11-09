# Knowledge Pipeline (Phase 2)

Collects, cleans, chunks, embeds, and indexes medical sources, builds a candidate knowledge graph, and serves cited retrieval for the reasoner (Phase 3).

```text
sources.yaml ──► ingest ──► clean ──► hash ──► chunk ──► embed ──► vector store
 (license gate)  openfda    html,     skip     sentence-   hashing /   in-memory (JSON)
                 pubmed     unicode   if       aware,      sentence-   or Chroma
                 local      control   unchanged overlap    transformers
                 files      chars                │
                                                 ├──► manifest.json (hashes, last run, embedder)
                                                 └──► co-mention graph ──► graph.json / Cypher
```

## Quick start

Run from the repository root.

```bash
pip install -r requirements.txt
python -m knowledge sources                      # what is ready vs blocked, and why
python -m knowledge ingest                       # all ready sources (incremental)
python -m knowledge ingest --source openfda_labels
python -m knowledge search "renal impairment dosing" -k 3
python -m knowledge graph --entity drug:metformin
python -m knowledge graph --cypher out.cypher    # load into Neo4j
python -m knowledge status                       # index size, last runs, stale sources
```

Runtime data lives in `knowledge/data/` (git-ignored). Override with `AESCULAP_DATA_DIR`.

## License gate

`sources.yaml` is the source registry. A source is ingested only if it is `enabled`, has an implemented `ingestor`, and a **human** set `license_status: approved` with `reviewed_by`. Everything except openFDA starts blocked. The license notes are a starting point for your review, not legal advice.

To enable a source: confirm its terms for your use (especially commercial use), then set `license_status: approved`, fill in `reviewed_by`, and set `enabled: true`.

## Sources

| Source | Ingestor | Status |
|---|---|---|
| openFDA drug labels | `openfda` | Ready (approved in draft, owner to confirm) |
| PubMed abstracts | `pubmed` | Built, blocked (license review). Set `NCBI_EMAIL`, optionally `NCBI_API_KEY` |
| WHO / NICE / CDC guidelines | `local_files` | Built, blocked (license review). Drop `.md`/`.txt` files in `knowledge/data/inbox/<source>/` |
| RxNorm, DrugBank, SNOMED CT, ICD, UMLS, textbooks | none | Planned, license required |

Local files accept optional front matter: `title`, `date`, `url`, `evidence_level`, `license`.

## Metadata and citations

Every chunk carries `source`, `title`, `url`, `date`, `evidence_level`, and `license`. `knowledge.search.retrieve()` returns items shaped for the `{{retrieved_sources}}` placeholder in `character/system_prompt.md`, with ids `S1`, `S2`, ... for `[S1]` citations. `format_for_prompt()` renders them as text.

## Refresh

`python -m knowledge ingest` is idempotent: unchanged documents are skipped by content hash, changed ones are re-chunked and replaced. Each source has `max_age_days`; `python -m knowledge status` lists stale sources. Schedule `ingest` with cron or a CI job that has persistent storage.

## Embeddings and stores

| Option | Use |
|---|---|
| `AESCULAP_EMBEDDER=hashing` (default) | Dependency-free **lexical** baseline for tests and offline use. It has no semantic understanding, so related terms with different words will not match. |
| `AESCULAP_EMBEDDER=sentence-transformers` | Semantic embeddings. Pick and benchmark a medical-suitable model in Phase 3 (`AESCULAP_EMBED_MODEL`). |
| `AESCULAP_STORE=memory` (default) | Brute-force cosine, JSON-persisted. Fine below roughly 50k chunks. |
| `AESCULAP_STORE=chroma` | Persistent vector DB. `pip install -r knowledge/requirements-optional.txt` |

Switching embedders needs a fresh index; the pipeline refuses to mix them.

## Knowledge graph

Edges are **candidate co-mentions** (two entities in the same chunk) with the supporting chunk ids. They are not validated clinical relationships. Never show an edge to a user as fact without the cited source text. The starter `graph/lexicon.yaml` holds names and synonyms only; replace it with an ICD/SNOMED/UMLS-derived vocabulary once those licenses are approved. A typed-relation extractor (for example "drug treats disease") is future work.

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

Tests are offline and use synthetic data only.

## Known limits

- openFDA labels are regulatory text, not clinical guidelines or evidence synthesis.
- Retrieval quality with the hashing embedder is a baseline only.
- Only `openfda`, `pubmed`, and `local_files` ingestors exist; PMC full text, RxNorm, and ontologies are not built.
- No PHI belongs in this pipeline (`docs/safety-policy.md` section 5).
