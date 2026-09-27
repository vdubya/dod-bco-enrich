# Official UFC glossary and master reference lists

The [WBDG UFC program page](https://www.wbdg.org/dod/ufc) identifies a consolidated glossary and reference resource as those sections move out of individual UFC documents. The user supplied the [official master PDF](https://www.wbdg.org/FFC/DOD/UFC/CORE_NON_CORE_UFC_Glossary_References.pdf), now registered as `UFC_GLOSSARY_REFERENCES` in the DoD base profile. It is a primary source for UFC-scoped terminology and reference assertions.

The initial download contains **481 pages covering 52 UFC contexts**, with **52 glossary sections, 52 reference sections, and two supplemental-resource sections**. All pages have extracted text. These are coverage counts for source indexing, not counts of validated entities or approved ontology concepts.

## Relationship to the corpus

| Source | Role in BCO |
| --- | --- |
| UFC JSON | Criteria text, hierarchy, document/version IDs, and sentence evidence |
| Official UFC glossary/reference PDF | Acronym expansions, definitions, references, and edition-selection notes within each originating UFC |
| UFGS SEC/XML | Guide-specification text, notes, and tailoring context |
| UFGS UMRL catalog | Separately versioned reference-publication and issuing-organization entities, joined to validated mentions |

The master document does not flatten all UFCs into a universal dictionary. Each page retains its UFC, glossary/reference/resource role, source PDF hash, and PDF page number. A shared term in two UFCs remains two scoped source assertions until reviewed for equivalence. A reference entry retains its own cited edition and any local selection instructions. Catalog membership does not establish project adoption.

For example, PDF page 5 contains UFC 1-200-01 definitions such as Critical Asset and Facilities Criteria. Its references begin on page 6 and include specific 2024 ICC editions. Page 64 explicitly introduces definitions for the cold-regions context of UFC 3-130-01. Some definitions cite MIL-STD-3007 without specifying a revision; the importer does not append a revision. These source statements remain available for later reconciliation with the other criteria and governance sources.

## Archived source and index

The [current pointer](../backend/app/bco/data/ufc-glossary/current.json) selects an immutable snapshot under `backend/app/bco/data/ufc-glossary/snapshots/<PDF SHA-256>/`:

- `source.pdf`: original downloaded bytes.
- `page-index.json`: exact decoded page text, page hashes, stable UFC/section identifiers, physical page anchors, publisher bookmarks, printed section headings, and structural findings.
- `manifest.json`: source and artifact hashes, byte counts, acquisition URL and time, HTTP and PDF metadata, extraction method, and source-role constraints.

Initial PDF SHA-256: `db8e5e076be7dbc08ceadbe25544e69756961ff2c8767869e98d4bb5dbc341c9`.

Creation/modification timestamps and retrieval dates are recorded as metadata, not treated as an authoritative publication edition or adoption date. Association with a UFC designation does not prove that the glossary corresponds to a particular digital UFC version.

The publisher URL can change its contents. For a historical citation, use `source.pdf` in the snapshot selected by the recorded hash and the indexed physical page number, rather than assuming that the current WBDG URL still serves those bytes.

The parser uses publisher bookmarks for section boundaries and corroborates each section's UFC and role against its printed heading. Five discrepancies are retained for review: appendix labels on pages 55, 123, 158, and 161, plus a bookmark calling page 399 a references section when its printed heading says glossary. The printed heading determines the section role; the bookmark is never silently replaced in the evidence.

Text coordinates refer to decoded PDF page text, not PDF bytes or geometric bounding boxes. Line wraps and extraction artifacts remain in the evidence. Relevant samples on pages 5, 6, 64, 399, and 466 were visually inspected; this is not a complete semantic or layout audit of all 481 pages. No OCR was needed for this snapshot. Future documents with an unsupported outline structure are rejected before activation for adapter review.

## Reimport updated releases

From the repository root:

```sh
# Download and compare without changing stored evidence.
.venv/bin/python scripts/import_bco_glossary.py --refresh --dry-run

# Download, validate, archive, and activate a changed release.
.venv/bin/python scripts/import_bco_glossary.py --refresh

# Local source option, explicitly recorded as remote-origin unverified.
.venv/bin/python scripts/import_bco_glossary.py --pdf '/path/to/master.pdf'
```

Identical source bytes return `unchanged` and preserve the original index and acquisition record. Changed bytes create another immutable snapshot. Section-level change reports identify added, changed, absent, and unchanged UFC/role sections. An absent section is not automatically withdrawn. These reports do not claim to compare individual definitions yet.

Writers are serialized, artifacts are validated before activation, and the current pointer is replaced atomically. Prior source snapshots, source spans, review decisions, and the frozen pilot ledger remain intact. A failed import leaves the prior current pointer usable. API readers notice a new pointer without a server restart; a pinned revision continues to return its original source. Parser upgrades do not silently rewrite an existing indexed PDF snapshot.

Refreshes run when the import command is invoked. This addition does not schedule automatic downloads or fetch the third-party publications listed in the PDF. Third-party attribution and source-specific rights remain separate from Enrich's software license.

## Search and extract using the existing pipeline

`GET /bco/glossary` returns archived pages, sections, source provenance, and structural findings. Search parameters are `q`, `designation`, `kind`, `offset`, and `limit`. Pass `revision=<PDF SHA-256>` to query an older snapshot. The API's `q` search requires every whitespace-separated word to occur in the page text; it is not semantic search or an entity count.

`POST /bco/parse`, `/bco/entities/plan`, and `/bco/entities` accept `source_format: "ufc_glossary_pdf"`. The original file is supplied as `content_base64`. Optional `source_designation` and `source_section_kind` select a UFC and appendix role. The CLI exposes those same filters:

```sh
.venv/bin/python scripts/extract_bco_entities.py '/path/to/CORE_NON_CORE_UFC_Glossary_References.pdf' \
  --source-designation 'UFC 1-200-01' --source-section-kind glossary --max-batches 100
```

This command plans only. The existing explicit provider/model and `--run` controls enable a bounded LLM run, with the same span validation and new review-bundle export described in [LLM entity discovery](LLM_ENTITIES.md). Each PDF batch and its context stay within one UFC/appendix scope, and adjacent pages are preferred for cross-page evidence. Validated publication mentions can use the existing UMRL links while preserving the cited edition separately.

The original PDF, page index, registry, adapter, importer, tests, and [source audit](../reports/ufc-glossary-source-audit.json) are committed to the BCO repository. No live model extraction has been run against the master PDF, and no glossary concepts have been approved by this ingestion step. The existing Criteria Atlas entity viewer and published pilot review collection continue to serve their existing datasets.

Validation passed: 101 targeted tests covering the glossary adapter/importer, existing UMRL imports and links, entity extraction, and source-evidence contracts. The complete PDF yields 126 planned batches covering all 481 pages exactly once as targets. These checks measure implementation behavior and source coverage, not semantic accuracy.
