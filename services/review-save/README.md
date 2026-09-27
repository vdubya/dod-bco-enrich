# Direct GitHub review saves

This service lets the GitHub Pages report save a review as a commit without opening the GitHub file editor. The report, corpus, review events, and all service source code remain in `vdubya/dod-bco-enrich`. No review database is maintained here. The service stores encrypted sign-in credentials and short-lived authorization state.

**Setup status:** the implementation is prepared, but the hosted service and private GitHub App have not been connected. `docs/save-config.json` intentionally has no service URL. Do not deploy this report version to the Pages branch until the service and GitHub App are configured. Verify a real technical save receipt immediately after publishing.

## Access boundary

- Register a private GitHub App owned by `vdubya`, with **Contents: read and write** and **Metadata: read**. Install it only on `vdubya/dod-bco-enrich`.
- GitHub permissions cover the repository's contents. The service's code further limits writes to newly created `docs/review-events/<UUID>.json` files on `dod-bco`; it accepts no caller-supplied repository, branch, path, existing-file SHA, or arbitrary API request.
- Only GitHub user ID `6257997` can save in this pilot, and the service checks current repository write permission for every save. The OAuth exchange also requests repository ID `1389728130`.
- The browser receives an opaque service session, not a GitHub access token. GitHub tokens are encrypted with AES-GCM in the service's authentication store. The fixed report origin is allowed by CORS. PKCE, a browser-bound state cookie, and single-use exchange codes protect sign-in.
- Service sessions last at most 30 days. The service refreshes expiring GitHub tokens when permitted. Revocation or expiration requires sign-in again. Sign out deletes the server session; revoking the app in GitHub removes its repository access.
- Every write validates the frozen source hash, candidate identity, field sizes and earlier review references. Optional scope and rationale remain optional. Retries reuse the same event ID. The service verifies the exact saved file at the returned commit before responding with `saved: true`.
- GitHub review records remain public. The verified GitHub account is attached as `authenticated_reviewer`; the typed reviewer name remains a display label. Direct GitHub edits are still possible for repository editors and remain visible in commit history.

## Runtime and configuration

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

After installation, configure the report from the repository root:

```sh
python3 scripts/configure_review_save.py https://THE-DEPLOYED-SERVICE-ORIGIN
```

This writes the public service URL and adds its exact origin to the report's `connect-src` policy. No secret belongs in that configuration. Publish the configured report to the Pages branch, complete GitHub sign-in from the report, run **Test GitHub saving**, and verify the returned commit and JSON receipt. A technical receipt cannot adjudicate a vocabulary assertion. Do not manufacture a real review to test saving.

The public read path still uses a single pinned GitHub snapshot. A read-limit failure does not clear a local draft or imply that no reviews exist. This pilot's review listing still requires an archive/index design before reaching 1,000 files.

The [GitHub user-token flow](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app) requires a server-held client secret. GitHub Pages serves the report's static assets; it cannot safely perform that exchange by itself.
