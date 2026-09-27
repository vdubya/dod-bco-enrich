# DoD BCO vocabulary review site

Live report: https://vdubya.github.io/dod-bco-enrich/

The report is published from `dod-bco:/docs` using GitHub Pages branch publishing, with `.nojekyll`. Report code, frozen source evidence, and saved review events live in this repository. The direct-save implementation adds a small authenticated service; its source also lives here in `services/review-save/`.

**Direct-save setup is pending:** this branch contains the replacement for the mobile editor handoff. The service and private GitHub App must be connected before publishing this version. See [service setup and access boundaries](../services/review-save/README.md).

## Review and save

1. Search the 50 selected source assertions and expand their evidence and document applicability context.
2. Choose **Review assertion** and record a decision and reviewer name. Scope and conditions and decision rationale are optional for every decision. Optional editorial wording stays separate from verbatim source text.
3. Choose **Save to GitHub**. Sign in to GitHub when prompted. The prepared review survives that sign-in and is submitted automatically when you return.
4. The report sends the review directly to the save service, which creates a UUID-named file in `docs/review-events/` on `dod-bco`. It confirms the exact committed file before displaying **Saved to GitHub** with a versioned record link. There is no editor handoff or copy-and-paste step.

The GitHub commit is the durable write. The service stores authentication state, not a second review database. The pilot permits the repository owner's verified GitHub account to save, after checking current repository write access. It attaches that account as `authenticated_reviewer`; the typed reviewer name remains a display label. Earlier records saved through the native editor retain their existing attribution in Git history. Anyone can view the public report and public review files.

Drafts use browser local storage and do not count as saved decisions. A pending event survives reload; choose **Save pending review** to resume. Retrying the same review reuses its event ID and timestamp, and the service checks an existing file instead of overwriting it or creating a duplicate. Editing a review prepares a new event. Existing local drafts remain usable. If sign-in expires, the report retains the draft while you reconnect.

Each revision references the events it supersedes. Concurrent heads remain a conflict, without choosing a winner from timestamps. Invalid source versions, changed evidence snapshots, duplicate IDs, cycles, and incomplete histories fail validation. Repository editors should add a correcting event instead of rewriting a past event. Git history retains modifications made outside that convention. No upstream pull request is involved.

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
node --test tests/review-site/*.test.mjs
node --check docs/review.js
python3 -m http.server 54803 --bind 127.0.0.1 --directory docs
```

Focused tests cover source round-trips, review history and conflicts, optional fields, draft identity, direct-save authentication, PKCE and single-use callbacks, encrypted token storage, repository and path restrictions, revoked access, idempotent retries, immutable commit read-back, and failure handling. The service tests use real SQLite with simulated GitHub responses; they do not create real vocabulary decisions. A mobile-width browser check verifies draft restoration and the connection-error state. A real signed-in technical receipt remains required after service deployment.

Hosting uses [GitHub Pages branch publishing](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site). Direct saving uses a [GitHub App user access token](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app) and the [repository contents API](https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents).
