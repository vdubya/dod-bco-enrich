# DoD BCO fork validation

26 September 2026. Local development fork, BCO layer 0.1.0.

## Verified behavior

- 198 tests passed in the targeted BCO and upstream regression suite; one upstream slow test was deselected. The entire upstream test suite was not run.
- `pip check` reported no broken requirements. `git diff --check` passed.
- Source adapters parsed all 48 local UFC JSON files and 681 of 685 SEC members. Four malformed XML members were quarantined without repair: `02 83 00.SEC`, `22 60 70.SEC`, `32 11 23.23.SEC`, and `35 05 40.14 10.SEC`.
- Browser review verified DoD BCO branding, eight review scopes, SEC upload, exact read-only source preview, symbolic enrichment, and a successful source-evidence download.
- Distinct Owner and Real Property Owner matches, no Chapter 2 bankruptcy match, source offsets, scoped sense IDs, XML rejection, local OWL loading, disabled-LLM behavior, domain prompt routing, and exclusion of judicial propositions have regression coverage.

## Symbolic extraction pilot

These are extraction counts for this run, not precision, recall, code coverage, or approved definitions. No live LLM or embedding evaluation was performed.

| Source | Source units | Concept annotations | Individuals | Properties | Syntactic triples | Valid evidence records | Missing component spans | Approved concepts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| UFC 1-200-01 | 706 | 908 | 207 | 45 | 368 | 2247 | 17 | 0 |
| UFGS 01 45 00 | 571 | 598 | 234 | 30 | 642 | 2745 | 43 | 0 |

Both completed pilot jobs have zero invalid source spans among the recorded candidates. Missing syntactic participants are retained as explicit findings, with no invented source span. This is not proof that the extracted relationship is semantically correct. The UFGS quality-control job uses the `usace` review scope, which does not establish USACE applicability of every clause.

The evidence audit found that upstream relationship display text inserted spaces around punctuation. The BCO path now stores the verbatim covering quote separately from normalized subject/predicate/object labels. Conditional phrases such as “in the event” are no longer emitted by the BCO named-individual heuristics; conditions remain source evidence.

Full results are retained locally under `.bco-state/pilot/`, outside Git. [pilot-summary.json](pilot-summary.json) records edition/source hashes, result hashes, job identifiers, and local review URLs. [adapter-audit.json](adapter-audit.json) records the source inventory, archive hash, member hashes, adapter coverage, and parsing failures.

## Reproduce the tests

```sh
cd backend
../.venv/bin/python -m pytest -q \
  tests/test_bco.py tests/test_ontology_registry.py tests/test_ontology_threading.py \
  tests/test_ontology_cache_paths.py tests/test_ontology_embedding_gating.py \
  tests/test_ontology_infra_hardening.py tests/test_branch_detail.py \
  tests/test_canon_branch_label_snap.py tests/test_individual_extraction.py \
  tests/test_branch_judge.py tests/test_rerank_stage.py \
  tests/test_proposition_stage.py tests/test_proposition_byte_neutral.py
```

Use `requirements-bco.txt` for the verified Python 3.12 environment. The initially installed PyArrow 25 binary exports differed from upstream fixtures; the same mismatch reproduced on unchanged upstream code. Pinning PyArrow 23.0.1 to the upstream lock version restored those fixtures. The fork also preserves the legacy serialized document shape when no BCO source envelope is present.

## Remaining work

Adjudicate source definitions, run a held-out semantic precision/recall evaluation, validate a configured LLM/embedding path, implement reviewed authority/applicability resolution, and add ER/EM, WHS BC, and PFGS adapters. The 68-class OWL is an editorial matching scaffold. The existing UFC definition pilot remains separate and unapproved.

The GitHub-hosted fork is [vdubya/dod-bco-enrich](https://github.com/vdubya/dod-bco-enrich), with BCO development on `dod-bco`. The repository retains the full upstream history and its MIT license. The independent `fix-source-span-offsets` branch is prepared for upstream review; no upstream pull request has been submitted.
