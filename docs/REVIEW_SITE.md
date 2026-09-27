# DoD BCO vocabulary review site

Live report: https://vdubya.github.io/dod-bco-enrich/

The report is published from `dod-bco:/docs` using GitHub Pages branch publishing, with `.nojekyll`. Report code, frozen source evidence, and saved review events live in this repository. The direct-save implementation adds a small authenticated service; its source also lives here in `services/review-save/`.

**Direct saving is connected and verified.** The private GitHub App is installed only on `vdubya/dod-bco-enrich`. The report saves through `https://dod-bco-save.vdub.chatgpt.site`, while report files and review records remain in GitHub. See [service setup and access boundaries](../services/review-save/README.md).

## Review and save

1. Use the compact **List** to compare terms, exact source wording, and saved status. Filter by publication, record type, status, or search text. **Details** expands the evidence and applicability context; **Detailed cards** retains the full original view.
2. Check individual rows or **Select all on this page**, then choose **Approve selected**. A batch holds up to 50 assertions and shows the selected terms before saving. Changing a filter or page clears the selection, so hidden rows are never silently included.
3. Enter the reviewer name once. Scope and conditions and decision rationale are optional shared notes. Choose **Approve and save** to save every selected assertion in one GitHub commit. Sign in when prompted; the prepared batch survives sign-in and resumes automatically.
4. Each assertion still receives a separate UUID-named file in `docs/review-events/` on `dod-bco`. The service confirms every committed file before displaying **Saved to GitHub** and a commit link. There is no editor handoff or copy-and-paste step.

Approved rows, conflicting histories, proposed editorial wording, and local drafts require individual review. Use **Review** for another decision or revised wording; scope and rationale remain optional. Bulk approval accepts the displayed source assertion within its stated source scope and does not merge similar terms across publications.

The GitHub commit is the durable write. The service stores authentication state, not a second review database. The pilot permits the repository owner's verified GitHub account to save, after checking current repository write access. It attaches that account as `authenticated_reviewer`; the typed reviewer name remains a display label. Earlier records saved through the native editor retain their existing attribution in Git history. Anyone can view the public report and public review files.

Drafts use browser local storage and do not count as saved decisions. A pending event survives reload; choose **Save pending review** to resume. Retrying the same review reuses its event ID and timestamp, and the service checks an existing file instead of overwriting it or creating a duplicate. Editing a review prepares a new event. Existing local drafts remain usable. If sign-in expires, the report retains the draft while you reconnect.

A pending batch also survives reload and uses the same event IDs on retry. Before submitting it, the report refreshes saved reviews and checks that each selected assertion's review history is unchanged. The service adds all files in one commit and advances the branch without force. A concurrent branch change stops the update; retrying rechecks the batch. **Clear pending batch** discards only the local pending selection and never deletes a saved GitHub record.

Each revision references the events it supersedes. Concurrent heads remain a conflict, without choosing a winner from timestamps. Invalid source versions, changed evidence snapshots, duplicate IDs, cycles, and incomplete histories fail validation. Repository editors should add a correcting event instead of rewriting a past event. Git history retains modifications made outside that convention. No upstream pull request is involved.

The client pins each refresh to one Git commit and reads the public GitHub API plus immutable raw file URLs. A failed refresh is visible and does not turn missing data into zero accepted decisions. GitHub's unauthenticated API read limit may require waiting before another refresh. The current directory listing is intentionally capped below 1,000 entries; reaching that boundary fails closed and requires an indexed/archive implementation.

**Test GitHub saving** creates two technical persistence receipts in one batch commit. Such records cannot adjudicate any vocabulary assertion and do not change accepted counts. This permits end-to-end batch verification without manufacturing a subject-matter decision.

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

Focused tests cover source round-trips, review history and conflicts, optional fields, draft identity, direct-save authentication, PKCE and single-use callbacks, encrypted token storage, repository and path restrictions, revoked access, idempotent retries, immutable commit read-back, setup recovery, hosted HTTP compatibility, and failure handling. Batch tests cover 50 approvals in one commit, partial or conflicting retries, non-forced concurrent updates, exact verification of every file, and changed review histories. The service tests use real SQLite with simulated GitHub responses; they do not create real vocabulary decisions. Browser checks cover filtered selection, the shared approval form, evidence expansion, and a 390-pixel phone layout without horizontal overflow.

On 27 September 2026 (UTC), the published report completed GitHub sign-in as `vdubya` and saved a [technical receipt at commit `e53a8e3`](https://github.com/vdubya/dod-bco-enrich/blob/e53a8e39ffc8b35bc3bfac84960f11fc0a4250b0/docs/review-events/12d35504-d06e-4196-af9f-a4920032edf8.json). Both the service and an independent repository read confirmed the exact file, frozen ledger hash, and authenticated reviewer ID. The test left substantive review and accepted-assertion counts at zero. A phone browser needs its own one-time GitHub sign-in; the full authenticated flow was verified in desktop Chrome.

Hosting uses [GitHub Pages branch publishing](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site). Direct saving uses a [GitHub App user access token](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app), the [repository contents API](https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents) for individual reviews, and the [Git tree API](https://docs.github.com/en/rest/git/trees) for batches.
