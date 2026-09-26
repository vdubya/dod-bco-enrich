# DoD BCO vocabulary review site

Live report: https://vdubya.github.io/dod-bco-enrich/

The report is published from `dod-bco:/docs` using GitHub Pages branch publishing, with `.nojekyll`. Report code, frozen source evidence, and saved review events live in this repository. There is no browser token, third-party database, or running Python server required for the published site.

## Review and save

1. Search the 50 selected source assertions and expand their evidence and document applicability context.
2. Choose **Review assertion** and record a decision, reviewer name, scope, and rationale. Optional editorial wording stays separate from verbatim source text.
3. Choose **Save to GitHub**. The site opens GitHub's native new-file editor with a prepared JSON event.
4. In GitHub, choose **Commit changes**, commit directly to `dod-bco`, and finish the commit. This requires repository write access and your normal GitHub sign-in. A file saved to a different branch or fork is not part of this site's shared review record. No upstream pull request is involved.
5. Return to the report and choose **Refresh saved reviews**. The page confirms the committed record only after reading it from the repository.

Drafts use browser local storage and are explicitly labeled as local. They are not shared or counted as saved decisions. The GitHub commit is the durable write. Anyone can view this public report and its public review records; only users with repository write access can commit to the shared branch. The reviewer name is self-reported; Git history records the saving account.

Each revision creates a UUID-named file in `docs/review-events/`, referencing the events it supersedes. Concurrent heads remain a conflict, without choosing a winner from timestamps. Invalid source versions, changed evidence snapshots, duplicate IDs, cycles, and incomplete histories fail validation. Repository editors should add a correcting event instead of rewriting a past event. Git history retains modifications made outside that convention.

The client pins each refresh to one Git commit and reads the public GitHub API plus immutable raw file URLs. A failed refresh is visible and does not turn missing data into zero accepted decisions. GitHub's unauthenticated API read limit may require waiting before another refresh. The current directory listing is intentionally capped below 1,000 entries; reaching that boundary fails closed and requires an indexed/archive implementation.

**Test GitHub saving** creates a technical persistence receipt. Such records cannot adjudicate any vocabulary assertion and do not change accepted counts. This permits end-to-end save verification without manufacturing a subject-matter decision.

## Source fidelity and boundaries

`data/pilot-ledger.json` is a byte-for-byte copy of the 26 September 2026, 50-entry UFC pilot ledger, representing six UFC publications. `data/source-units.json` contains the 201 exact evidence/context/applicability units referenced by that selection. The ledger hash is verified by the browser; quotes round-trip to the supplied source units. Original extraction manifests, selection, policy snapshot, and validation are in `data/`.

The source adapter covered headings and sentence fields. Tables, media, commentary, and content-only leaves were excluded. Source editions were not refreshed for this publication. Referenced external standards have not been independently validated. Rights metadata and provenance remain attached to each assertion; this report does not assert blanket rights for referenced third-party works.

An accepted source assertion is not automatically an approved ontology concept, a global synonym, or a project applicability determination. The OWL seed and approved concept count are not changed by saving a review here. Mappings, authority resolution, and release governance remain separate steps.

## Maintenance and verification

To regenerate the evidence bundle from the original workspace pilot:

```sh
python3 scripts/build_review_site.py --source /path/to/ufc-vocabulary-pilot-2026-09-26
```

Do not run against a changed corpus as a silent replacement. A new ledger hash requires review of old decisions before reuse.

```sh
node --test tests/review-site/reviews.test.mjs
node --check docs/review.js
python3 -m http.server 54803 --bind 127.0.0.1 --directory docs
```

Nine focused tests cover source round-trips, empty state, revision/reopen history, concurrent decisions, explicit conflict resolution, stale source identity, invalid histories, required acceptance scope, technical receipt separation, and safe GitHub handoff encoding.

Hosting uses [GitHub Pages branch publishing](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site). Saving uses [GitHub's native file creation and commit flow](https://docs.github.com/en/repositories/working-with-files/managing-files/creating-new-files).
