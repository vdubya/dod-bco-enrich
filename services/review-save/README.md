# Direct GitHub review saves

This service lets the GitHub Pages report save a review as a commit without opening the GitHub file editor. The report, corpus, review events, and all service source code remain in `vdubya/dod-bco-enrich`. No review database is maintained here. The service stores encrypted sign-in credentials and short-lived authorization state.

**Setup status:** connected at `https://dod-bco-save.vdub.chatgpt.site`. The private `DoD BCO Reviews vdubya` app is installed only on `vdubya/dod-bco-enrich`; `docs/save-config.json` and the report's CSP name this service origin. The published report's authenticated technical save was verified at [commit `e53a8e3`](https://github.com/vdubya/dod-bco-enrich/blob/e53a8e39ffc8b35bc3bfac84960f11fc0a4250b0/docs/review-events/12d35504-d06e-4196-af9f-a4920032edf8.json). The initial `SETUP_KEY` has been removed from the hosted environment. Preserve the existing `SESSION_KEY` and encrypted app configuration.

## Access boundary

- Register a private GitHub App owned by `vdubya`, with **Contents: read and write** and **Metadata: read**. Install it only on `vdubya/dod-bco-enrich`.
- GitHub permissions cover the repository's contents. The service's code further limits writes to newly created `docs/review-events/<UUID>.json` files on `dod-bco`; it accepts no caller-supplied repository, branch, path, existing-file SHA, or arbitrary API request.
- Only GitHub user ID `6257997` can save in this pilot, and the service checks current repository write permission for every save. The OAuth exchange also requests repository ID `1389728130`.
- The browser receives an opaque service session, not a GitHub access token. GitHub tokens are encrypted with AES-GCM in the service's authentication store. The fixed report origin is allowed by CORS. PKCE, a browser-bound state cookie, and single-use exchange codes protect sign-in.
- Service sessions last at most 30 days. The service refreshes expiring GitHub tokens when permitted. Revocation or expiration requires sign-in again. Sign out deletes the server session; revoking the app in GitHub removes its repository access.
- Every write validates the frozen source hash, candidate identity, field sizes and earlier review references. Optional scope and rationale remain optional. Retries reuse the same event ID. The service verifies the exact saved file at the returned commit before responding with `saved: true`.
- GitHub review records remain public. The verified GitHub account is attached as `authenticated_reviewer`; the typed reviewer name remains a display label. Direct GitHub edits are still possible for repository editors and remain visible in commit history.

## Runtime and configuration

`POST /reviews` saves an individual review. `POST /reviews/batch` accepts 1 to 50 distinct approvals, a UUID batch ID, and the pinned base commit. Both routes require the same owner session and repository permission. Batches create one immutable event file per assertion through a Git tree based on the existing tree, one commit with the current head as its parent, and a non-forced branch update. Only generated review-event paths are changed. The service validates the entire batch before any write and verifies every file's Git blob identity at the resulting immutable commit. A duplicate retry succeeds only if every expected file already matches; partial or mismatched records fail without overwriting anything. A branch race fails without replacing another commit.

The report checks current review heads before submission. The service also requires the exact supplied base commit and validates superseded records against the frozen ledger. A successful response includes all normalized events, their authenticated reviewer, and one commit link; the browser rejects partial or mismatched receipts. The technical save check uses two `persistence_check` records through this same route and cannot approve vocabulary.

The entry point exports a standard Worker `fetch(request, env)` handler. It needs Web Crypto and a D1-compatible database binding. Tests use Node's real SQLite engine through the same binding interface. All dependencies are bundled; runtime code has no npm dependencies.

| Binding | Purpose |
| --- | --- |
| `DB` | Authentication tables only; Drizzle migrations applied during deployment |
| `SERVICE_URL` | Fixed HTTPS origin of this service |
| `SESSION_KEY` | Secret, base64-encoded 32 random bytes for AES-GCM encryption |
| `SETUP_KEY` | Secret, base64url-encoded 32 random bytes for initial setup |

Set secrets through the hosting provider's protected environment settings. Never commit them, put them in the report, or print them to logs. Keep `SESSION_KEY` stable across deployments; changing it invalidates encrypted app configuration and sessions. This service deliberately does not log request bodies, authorization headers, callback query strings, or tokens; configure hosting request logs to avoid query-string collection as well.

```sh
cd services/review-save
npm ci
npm run build
npm test
```

Deploy `dist/worker.mjs` with the bindings above. Verify `/health` responds with the expected repository and `ready: false`. Initial setup uses `/setup?ticket=<SETUP_KEY>` on that service. Treat this as a private, short-lived setup link. The resulting GitHub form creates a private app through [GitHub's manifest flow](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest); permission approval happens in GitHub. Its callback stores the app client secret encrypted and discards the unused PEM and webhook secret. Install only the named repository. Setup endpoints become unavailable after registration.

If registration creates the GitHub App but the callback fails before exchanging its code, reopen the protected setup link and use **Resume an app already created** within GitHub's one-hour conversion window. This binds the existing code to a fresh single-use state and secure cookie; it does not create a duplicate app. The recovery form uses the same GET callback as GitHub. Server requests use `redirect: 'manual'` and reject unsuccessful responses, so credentials never follow an unexpected redirect. The deployed host rejects the otherwise-standard `redirect: 'error'` option.

After installation, configure the report from the repository root:

```sh
python3 scripts/configure_review_save.py https://THE-DEPLOYED-SERVICE-ORIGIN
```

This writes the public service URL and adds its exact origin to the report's `connect-src` policy. No secret belongs in that configuration. Publish the configured report to the Pages branch, complete GitHub sign-in from the report, run **Test GitHub saving**, and verify the returned commit and JSON receipt. A technical receipt cannot adjudicate a vocabulary assertion. Do not manufacture a real review to test saving.

The public read path still uses a single pinned GitHub snapshot. A read-limit failure does not clear a local draft or imply that no reviews exist. This pilot's review listing still requires an archive/index design before reaching 1,000 files.

The [GitHub user-token flow](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app) requires a server-held client secret. GitHub Pages serves the report's static assets; it cannot safely perform that exchange by itself.
