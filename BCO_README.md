# DoD BCO Enrich

**DoD BCO**, pronounced **beeco**, stands for **DoD Building Code Ontology**.
Descriptor: **Ontology and Knowledge Graph for the DoD built environment**.

This is [vdubya's fork](https://github.com/vdubya/dod-bco-enrich) of [Alea Institute's FOLIO Enrich](https://github.com/alea-institute/folio-enrich), with upstream history preserved on branch `dod-bco`. It adds facilities vocabulary, source adapters, scoped evidence, and domain prompts to the existing extraction pipeline. It is a research prototype, without agency endorsement or approved definitions.

## Live vocabulary review

Open the [DoD BCO vocabulary review](https://vdubya.github.io/dod-bco-enrich/) to search the 50-source-assertion pilot, inspect evidence, and save decisions through your GitHub sign-in. Report assets and append-only review events are versioned on `dod-bco`. See [the review-site guide](docs/REVIEW_SITE.md) for saving, source coverage, and verification.

## Run the installed workspace

From this repository:

```sh
.venv/bin/python scripts/run_bco.py
```

Open <http://127.0.0.1:8765/?ontology=dod-bco>. The launcher selects BCO, stores jobs and feedback in `.bco-state/`, and defaults to symbolic extraction with embeddings disabled. Upload UFC JSON or UFGS SEC/XML to preserve source locations. Uploaded source previews are read-only. Plain text remains supported but has no original-file anchor. The result screen provides **Download source evidence**.

To clone the BCO branch and create a fresh Python 3.12 environment matching this run:

```sh
git clone --branch dod-bco https://github.com/vdubya/dod-bco-enrich.git
cd dod-bco-enrich
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-bco.txt
.venv/bin/python -m pip install --no-deps -e ./backend
.venv/bin/python scripts/run_bco.py
```

The pinned snapshot includes the spaCy English model and the development tools. It is the verified local environment; the upstream `backend/uv.lock` remains available for its separate locked workflow. `pyarrow==23.0.1` matches the upstream binary-export fixtures. Credentials are excluded from the repository.

## Extract a source reproducibly

For **LLM entity discovery beyond the seed vocabulary**, use the new [entity extraction method](docs/LLM_ENTITIES.md). It provides a no-call plan, bounded and resumable provider calls, exact source-span validation, explicit failures, an asynchronous API, and a new review-bundle export. The existing general enrichment command below remains available for seed matching and broader pipeline enrichment.

[UMRL entities](docs/UMRL_ENTITIES.md) reuse the already processed Criteria Atlas catalog and viewer data: 4,972 reference records, 304 issuing organizations, and 31 saved reference matches across two UFCs. BCO preserves the original reference IDs and evidence, exposes searchable catalog endpoints, and links validated LLM publication mentions to the inventory. The existing Criteria Atlas viewer remains in place.

With the server running:

```sh
.venv/bin/python scripts/enrich_bco.py \
  ../data/source/ufc/UFC_1-200-01.json \
  --output .bco-state/ufc-1-200-01.json

.venv/bin/python scripts/enrich_bco.py '/path/to/01 45 00.SEC' \
  --profile usace --output .bco-state/ufgs-01-45-00.json
```

This CLI explicitly disables LLM calls unless `--with-llm` is supplied. Optional LLM providers use upstream configuration and the BCO-specific concept, role, relationship, branch, and contextual-ranking prompts. Live LLM accuracy and embedding matching were not evaluated in this implementation. Prompt routing was tested with a fake provider. A configured provider by itself is not evidence of a successful extraction call.

API entry points:

- `POST /bco/parse`: original bytes encoded as `content_base64`, `source_format` (`ufc_json` or `ufgs_sec`), and optional `profile_ids`.
- `POST /bco/enrich`: the same envelope, plus optional LLM configuration or `use_llm: false`.
- `GET /enrich/{job_id}`: the upstream job with `result.metadata.bco_evidence`.
- `GET /bco/evidence/{job_id}`: a downloadable JSON evidence ledger.
- Existing generic exports remain available. The BCO evidence JSON is the source review ledger; generic graph exports are machine-generated candidate graphs, not accepted code assertions.

## What this fork implements

The bundled matching scaffold has **68 classes in nine branches and 10 relationship properties**, all editorial proposals. It uses a provisional `example.org` namespace, an integrity manifest, and local OWL loading. It contains zero adjudicated definitions. Owner, Owner's Representative, Real Property Owner, contracting roles, and jurisdiction roles remain separate candidates.

UFC evidence retains original-byte hashes, document/version identifiers, JSON pointers, node/sentence identifiers, section paths, and exact decoded field text. The current adapter mines headings and sentence fields; commentary, media, and content-only nodes are explicitly outside its coverage. It does not claim complete table or image extraction.

SEC evidence retains original-byte hashes, XML paths, decoded text, and ancestor tags/attributes. Guide notes remain distinguishable from specification text. Inline XML is flattened into decoded text for matching; the source hash identifies the original markup. These are decoded-text coordinates, not raw XML byte offsets. The adapter rejects malformed XML and DTDs, and does not evaluate brackets, tailoring, or whether a guide specification has become a project requirement. Archive-member names and archive hashes are recorded in the corpus audit.

The BCO normalizer preserves the character coordinate system. Each accepted evidence record must round-trip to its source quote. Syntactic relationship components retain their normalized labels separately from verbatim covering source spans. Missing component spans are review findings. Scope cues preserve words such as `shall`, `unless`, and `for leased` in their source context; they are not yet a complete normative logic model.

The existing Enrich label matching, resolution, named-entity extraction, syntactic triples, review UI, and export machinery are reused. The BCO path replaces legal citation extraction with publication-designator matching. Judicial proposition taxonomy, legal metadata mining, and area-of-law assessment are excluded from BCO jobs.

## Scoped meanings and future sources

[profiles.json](backend/app/bco/profiles.json) carries the existing 11-module / eight-profile design for DoD, USACE, USACE Engineering and Construction, USACE Real Estate, USAF, NAVFAC, WHS, and WHS Pentagon. A candidate sense ID includes source bytes, profile selection, source span, and proposed match. Choosing a profile records review context, not legal applicability or precedence.

MIL-STD-3007G governance, UFC/UFGS, USACE ER/EM, WHS Building Code, and PFGS have distinct source roles in the registry. Only UFC JSON and UFGS SEC adapters are implemented here. ER/EM, WHS/PFGS acquisition and adapters, edition-specific authority edges, automatic inheritance/conflict resolution, and community views remain future work. No blanket rule makes ER/EM subordinate to UFGS or makes a community explanation override a source definition.

The earlier 50-entry UFC vocabulary ledger remains a separate candidate-review artifact in the parent workspace. This fork does not turn those entries into approved OWL definitions. The next research gate is adjudicating those source definitions and benchmarking LLM-assisted discovery on held-out passages.

## Validation and provenance

See [validation report](reports/validation.md), [adapter audit](reports/adapter-audit.json), and [fork provenance](bco-fork.json). The checks cover source fidelity and integration, not semantic precision or recall. Upstream machine status `confirmed` means a machine match; the BCO ledger continues to say `candidate_pending_subject_matter_review` and reports zero accepted concepts.

The hosted fork is [vdubya/dod-bco-enrich](https://github.com/vdubya/dod-bco-enrich). The development branch is `dod-bco`; `main` retains the upstream baseline. The independent `fix-source-span-offsets` branch contains the generic whitespace/relationship-span fix prepared for upstream review.

In the original workspace, `origin` points to the hosted fork and `upstream` points to Alea Institute. After a fresh clone, add the upstream remote with `git remote add upstream https://github.com/alea-institute/folio-enrich.git`. Keep upstream changes reviewable with `git fetch upstream` and a reviewed merge into `dod-bco`.

The original [MIT license](LICENSE) and upstream attribution are retained. Enrich code licensing is distinct from FOLIO ontology licensing. The BCO seed is an editorial scaffold and does not copy FOLIO's legal ontology; source-corpus rights and third-party materials retain their separate review requirements.
