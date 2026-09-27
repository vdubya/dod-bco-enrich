# LLM entity discovery

This method discovers built-environment entities from UFC JSON or UFGS SEC/XML without restricting discovery to the 68 seed classes. It uses the source adapters and provider interface from the Enrich fork. It does not require an existing ontology match.

The model proposes assets, spaces, systems, materials, activities, organizations, responsibility roles, property interests, documents, requirements, locations, and quantities. General concepts and named individuals are separate categories. Every proposal remains `candidate_pending_subject_matter_review` with no accepted concept ID.

Publication mentions now link to the [existing UMRL entity inventory](UMRL_ENTITIES.md) after source validation. The initial snapshot reuses 4,972 processed reference records and their existing viewer data. It makes no additional model calls, preserves prior evidence and review states, and keeps catalog editions separate from cited or adopted editions. Each extraction run records and holds one UMRL revision even when a newer release is imported during that run.

## Run from the installed workspace

Install the optional SDK snapshot once:

```sh
.venv/bin/python -m pip install -r requirements-bco-llm.txt
```

Preview the exact source-unit batches without making model calls:

```sh
.venv/bin/python scripts/extract_bco_entities.py \
  ../data/source/ufc/UFC_1-200-01.json --max-batches 5
```

Choose a provider and explicit model. Configure its key in the local environment or existing Enrich settings. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and the corresponding `FOLIO_ENRICH_*_API_KEY` settings are supported. Never put credentials in source files, command arguments, or GitHub commits. The public-request key policy still requires a caller-supplied key when `require_user_api_key` is enabled.

With `BCO_MODEL` set to your chosen model identifier:

```sh
.venv/bin/python scripts/extract_bco_entities.py \
  ../data/source/ufc/UFC_1-200-01.json \
  --run --provider openai --model "$BCO_MODEL" \
  --max-batches 5 --output .bco-state/entity-runs/ufc-building-code-01
```

Use `--provider anthropic` or `--provider ollama` for those configured providers. Ollama must already be running with the requested model. The command never installs or downloads a local model automatically. Other providers in the existing Enrich registry remain available.

For SEC input, specify a file and optionally a review profile:

```sh
.venv/bin/python scripts/extract_bco_entities.py '/path/to/01 45 00.SEC' \
  --profile usace --max-batches 5
```

Profile selection records review context. It does not determine legal applicability or precedence.

The default is a plan only. `--run` permits calls. A run defaults to five batches, 24 target units per batch, two concurrent calls, two application attempts, and a 90-second timeout per attempt. Target text is limited to 12,000 characters per batch; same-paragraph context has a separate 12,000-character cap. Schema and metadata add prompt overhead. These are character limits, not token or price estimates. Increase `--max-batches` explicitly for wider coverage. A source unit larger than the configured character cap stops planning rather than being truncated.

Successful responses are cached in `.bco-state/entity-cache` under the source, prompt, schema, provider, endpoint, model, and invocation-parameter fingerprint. Run again into a new output directory to resume unchanged batches. Changed inputs or model settings get a different cache key. Invalid or incomplete cached proposals are retried. A model version behind an alias can change; use a versioned model identifier when the provider offers one.

Exit code `0` means every source batch completed with valid proposals. Code `2` means a failed or partial run, including an intentionally limited batch budget. Code `1` means a configuration, source, or output error. Inspect coverage and batch findings instead of interpreting an empty candidate list as success.

## Results and review handoff

Each run writes:

- `entity-report.json`: validated mentions, proposed labels and categories, optional cited definitions and scope, run provenance, per-batch status, and coverage.
- `review-bundle/pilot-ledger.json`: candidates using the reviewer ledger shape.
- `review-bundle/source-units.json`: exact decoded evidence and original source locations.
- `review-bundle/site-manifest.json`: immutable candidate-ledger hash and coverage.
- `review-bundle/extraction-report.json`: the complete run report alongside the review material.

Review exports must use a new directory. They do not overwrite the published 50-assertion pilot, its frozen hash, saved decisions, or the ontology. The export is a new collection prepared for review; it is not automatically registered with the public GitHub save service. Publishing a new collection requires registering its evidence snapshot while retaining the existing review history.

The model supplies exact text and source-unit IDs. Python derives character positions, checks all quotations, rejects unknown units and invented spans, distinguishes guide notes, and generates stable source- and profile-specific candidate IDs. Repeated terms in different sources or contexts remain separate. Proposed descriptions are editorial text, never presented as source quotations. Model confidence is uncalibrated. Source span validity is not a semantic accuracy measurement.

The method reads the full units chosen by the deterministic batch plan, including units with no prior keyword or seed match. It can therefore discover vocabulary missed by label matching. It does not resolve synonyms, adjudicate authority, infer inheritance, approve ontology concepts, or establish project applicability.

## API

The local BCO server exposes the same engine:

| Route | Behavior |
| --- | --- |
| `POST /bco/entities/plan` | Plan source-unit batches without any provider call |
| `POST /bco/entities` | Start an asynchronous entity job; returns its status and result URLs |
| `GET /enrich/{job_id}` | Read job progress, coverage, and error state |
| `GET /bco/entities/{job_id}` | Download the completed or partial entity report |

Requests use the existing source envelope: `content_base64`, `source_format`, `profile_ids`, optional `llm_provider`, `llm_model`, and `api_key`, plus an `options` object with the batch controls above. `use_llm: false` is rejected by the execution route; use the planning route instead. Credentials are not persisted with the job. A partial job is marked failed at the job level while retaining validated candidates and the detailed partial report.

OpenAI calls use the Responses API with strict JSON Schema, `store: false`, a 12,000-token output cap, and SDK retries disabled. Refusal and incomplete output produce explicit failures. [OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs) distinguishes schema conformance from JSON-only output. Other provider adapters retain their existing structured/JSON behavior; the same Python validation applies to all of them. Their SDKs may perform internal retries in addition to the application attempt count.

## Validation and current execution status

Tests cover exact Unicode and whitespace spans, repeated mentions, unknown citations, invented text, source/profile separation, guide notes, duplicate proposals, omitted units, bounded concurrency, timeouts/retries, cache identity and corruption, partial coverage, immutable review exports, credential-policy failures, the asynchronous API, and OpenAI requests through the installed SDK with a mocked HTTP transport. These are implementation tests, not measured semantic precision or recall.

Verification passed: 110 Python extraction, source-adapter, and provider tests; 43 existing review-site tests; and the installed dependency consistency check. Provider cleanup failures are also checked to ensure they cannot prevent saving an extraction report or expose credentials in logs.

No live LLM run has been made for this method yet. At implementation time, no provider key was configured in this fork and neither local Ollama nor LM Studio was reachable. [The corpus run plan](../reports/entity-extraction-plan.json) is a deterministic planning artifact, with zero model calls and zero generated or approved entities.

Reproduce the corpus plan with:

```sh
.venv/bin/python scripts/plan_bco_entities.py \
  --ufc-directory ../data/source/ufc \
  --ufgs-archive ../data/source/umrl/UFGS_M_2026-05-28.zip \
  --output reports/entity-extraction-plan.json
```

The current plan examines 48 UFC JSON files and 685 SEC members. At the default character limit, 722 documents are ready, seven SEC members have an oversized text unit requiring a larger limit or a future fragment adapter, and the four previously identified malformed XML files remain blocked. The planner does not repair sources or quietly omit oversized text.
