# UMRL entities from the existing Criteria Atlas work

BCO reuses the UMRL catalog, resolver results, and viewer data already produced in the Digital Engineering Criteria workspace. The original May 28, 2026 inventory contains 4,972 reference records, 304 issuing organizations, and 31 saved matches involving 18 reference records across UFC 3-101-01 and UFC 3-120-10. These are existing results, not a new extraction or a corpus-wide coverage claim. Later imports retain this baseline and report their own counts and provenance.

The existing Criteria Atlas application remains the entity and UMRL viewer. Its UMRL view already supports catalog search, organization filters, publication metadata, current-document scope, and navigation from a reference usage to its source paragraph. This change exposes that processed inventory to BCO's entity pipeline and local API. It does not replace or redeploy that viewer.

## Preserved inputs

| Existing workspace artifact | How BCO reuses it |
| --- | --- |
| `data/output/umrl/umrl_catalog.json` | Verifies every catalog field against the viewer inventory; retains the input hash |
| `webapp/public/corpus/umrl-viewer.json` | Bundled byte for byte, including all reference IDs and usage objects |
| `data/output/ufc/UFC_*/umrl_analysis.json` | Retains all original matches, match IDs, source anchors, confidence, review status, and unresolved candidates for the two indexed documents |
| `src/criteria_graph/umrl_pass.py` | Remains the existing reference extraction and alias-resolution implementation |
| `webapp/src/criteria-atlas-app.ts` | Remains the existing entity and UMRL viewer |

The [baseline manifest](../backend/app/bco/data/umrl/manifest.json) records the original artifact hashes and the May 28, 2026 UFGS Master source provenance. BCO checks snapshot hashes before using the data. Catalog/viewer disagreements or broken evidence joins fail visibly. The original analyses also contain eight unresolved candidates, preserved in [prior-analyses.json](../backend/app/bco/data/umrl/prior-analyses.json).

## Entity identity and editions

Each reference is a named `reference_publication` entity. Its `entity_id` is the exact existing viewer `reference_id`, such as `ASCE 7`. Issuing organizations are named entities keyed by the complete organization name, not by an acronym. A separate catalog-entry ID identifies the record in the pinned catalog snapshot.

The existing graph slug is preserved as `legacy_graph_id`. It is not safe as a unique key: `PL-109-58` and `PL 109-58` both produce `PL-109-58`. BCO retains both records and flags this collision without asserting that they are equivalent or different publications.

The listed edition statement is preserved as catalog wording. It does not determine the edition cited by a UFC/UFGS passage or adopted for a project. Source catalog records are separate from proposed ontology concepts and approvals. Reference metadata does not include the standards' full text.

## Connection to entity discovery

After an LLM proposal passes the existing source-span validation, BCO looks up each complete `document` mention in the existing reference inventory. Exact reference IDs receive a publication identity link. Normalized designators yield review candidates, including all colliding records. Unmatched mentions remain unresolved.

Each extraction report now includes an `umrl` section with catalog provenance, linked publication entities, and their organizations. Individual document candidates retain their source spans and pending review status. These links and their provenance also survive export into a review bundle. The planner reports the available UMRL inventory without making model calls.

This step looks up complete, already-extracted designators. It does not rerun the broader Criteria Atlas resolver, perform title or alias extraction, or silently apply historical matches to a new source edition. For example, `ASCE 7` links directly; `ASCE  7` requires normalized-match review; `IBC` remains unresolved by this narrow lookup even though the existing resolver can produce an ICC alias match. The original resolver results remain available as `prior_matches` with their original evidence and review states.

## API and export

The local BCO server provides these read-only endpoints without an LLM provider:

| Route | Result |
| --- | --- |
| `GET /bco/umrl?q=concrete&offset=0&limit=50` | Search reference ID, title, and organization; maximum 200 records per page |
| `GET /bco/umrl/entity?reference_id=ASCE%207` | Exact publication entity, organization, viewer usages, and original resolver matches |
| `GET /bco/umrl/history` | Available revisions, active revision, and the last import's full change report |

Use a query parameter for exact IDs containing slashes. Both catalog endpoints accept `revision=<64-character revision ID>` to inspect an earlier snapshot, including records absent from the current catalog. Responses identify the revision used. GitHub Pages does not run these API endpoints.

Export the full named-entity inventory with no extraction or model calls:

```sh
.venv/bin/python scripts/export_bco_umrl.py \
  --output .bco-state/exports/umrl-entities.json
```

The exporter requires a new file and will not replace an existing export. Add `--revision <revision ID>` to export a historical snapshot. The fork includes the required data and works without the parent Criteria Atlas workspace.

## Reimport updated releases

The input is the updated `data/output/umrl/umrl_catalog.json` and matching `data/source/umrl/source_manifest.json` in the Criteria Atlas workspace. UMRL acquisition and parsing remain in the existing Criteria Atlas pipeline.

When the catalog has been refreshed but document analyses have not, preview the changes:

```sh
.venv/bin/python scripts/import_bco_umrl.py '..' --catalog-only --dry-run \
  --report .bco-state/exports/umrl-update-preview.json
```

Import that catalog with the same command, omitting `--dry-run` and choosing a new optional report path:

```sh
.venv/bin/python scripts/import_bco_umrl.py '..' --catalog-only
```

For a complete, consistent refresh of the catalog, viewer usages, and saved reference analyses, use the original command:

```sh
.venv/bin/python scripts/import_bco_umrl.py '..'
```

Add `--dry-run` to either mode to inspect changes without changing the snapshot store. `--report` writes a separate new JSON file when requested. Reimporting identical input returns `unchanged`; it creates no duplicate snapshot or change report. The importer needs no model credentials and makes no model calls.

Each successful changed import preserves the old snapshot and writes the new snapshot under `backend/app/bco/data/umrl/snapshots/<revision>/`. It records added references, changed fields and editions, references absent from the new catalog, and identity collisions. A missing record means absent from that snapshot, not automatically withdrawn. Unchanged reference IDs remain stable. A renumbered reference appears as an addition and an absence pending identity review.

Changed entries are flagged for review. Imports do not change ontology decisions or infer cited editions, adopted editions, equivalence, or project applicability. Catalog-only mode marks document evidence as `not_reconciled_against_this_catalog`; earlier matches and unresolved candidates remain accessible in their original revision. New reference matches can be imported later after the existing resolver and viewer data have been refreshed.

The importer validates all artifacts and writes the snapshots and immutable change report before atomically replacing `current.json`. Concurrent writers cannot interleave, and an interrupted import leaves the prior active revision available. The original flat-layout files remain the baseline. Completed snapshots, `changes/` reports, and `current.json` are Git-versioned data; temporary files and the import lock are ignored.

The running BCO API detects the new active revision on its next request. Each LLM extraction run captures one catalog revision at startup and keeps that revision throughout the run. The Criteria Atlas UI continues to use its own prepared viewer data; full import validates that data against the updated catalog, while catalog-only import updates BCO independently.

## Verification

Tests compare every original viewer field and match field, exercise exact and ambiguous identity resolution, check source quotations and pending review states after LLM linking, verify API pagination and slash-bearing IDs, and reject modified artifacts or inconsistent saved evidence. Reimport tests cover identical inputs, dry runs, edition changes, added and absent records, preservation of earlier matches and unresolved candidates, migration from the flat baseline, invalid input, interrupted activation, concurrent writers, automatic cache refresh, historical API reads, and imports during LLM extraction.

The 84 focused tests pass. A real reimport of the existing inventory returned `unchanged` for all 4,972 records. See [reimport verification](../reports/umrl-reimport-validation.json). These are integrity and integration checks, not a measurement of extraction precision or recall.
