# Phase Plan — Claude subscription sign-in (OAuth)

> Required by AGENTS.md rule 1: this plan must exist and be confirmed by the
> user before any implementation code is written.

## Goal

Let users who pay for Claude via a subscription (Pro/Max) authenticate with a
browser sign-in instead of pasting an API key. Settings gains a "Sign in with
Claude" flow for the existing `claude` provider; once connected, all Claude
calls (reviews, scoring, rewrites, cover letters, model listing) use the OAuth
access token and refresh automatically. The API-key path stays untouched and
remains the default when no OAuth session exists.

This reuses the same public OAuth client Claude Code uses
(`https://claude.com/cai/oauth/authorize` → `https://platform.claude.com/v1/oauth/token`,
client id `9d1c250a-e61b-44d9-88ed-5944d1962f5e`, PKCE S256, scopes
`user:profile user:inference`). OAuth-authenticated Messages API calls must send
`Authorization: Bearer …` plus `anthropic-beta: oauth-2025-04-20` instead of
`x-api-key`.

### Risk note (must be acknowledged when confirming this plan)

This is an **undocumented third-party use of Claude Code's OAuth client**, not
an Anthropic-supported integration. Anthropic can change endpoints, revoke the
client, or restrict subscription usage outside Claude Code at any time, and its
consumer terms may limit programmatic use of subscription credentials. The
feature must therefore degrade cleanly: when OAuth fails or is disconnected,
the API-key and mock providers keep working. No Anthropic ToS text is bundled
with the app by this change.

## Success criteria

- [x] `GET /api/settings` returns `claude_auth_mode`, `claude_oauth_connected`,
      `claude_oauth_account`, `claude_oauth_expires_at` and never any token
      material (only masked `claude_key` as today).
- [x] `POST /api/settings/claude/oauth/start` returns an authorize URL whose
      query has exactly: `code=true`, the client id, `response_type=code`,
      `redirect_uri=https://platform.claude.com/oauth/code/callback`,
      `scope=user:profile user:inference`, `code_challenge`,
      `code_challenge_method=S256`, `state`.
- [x] Exchanging a bogus/replayed code returns HTTP 400 with a readable message
      and stores nothing.
- [ ] A real Claude subscription sign-in (user-performed) stores encrypted
      access + refresh tokens, sets `claude_auth_mode=oauth`, and makes
      `POST /api/settings/providers/models` with `{"provider":"claude"}` return
      a model list **without** an API key.
- [ ] A review created with provider `claude` completes end-to-end on the
      subscription token (SSE stages/deltas, score, suggestions).
- [x] The access token is refreshed automatically before expiry; the rotated
      refresh token is persisted, so a second run hours later still works
      without re-login.
- [x] Settings UI: Connect, connected state (account/expiry), Disconnect, and
      the API-key form all work; New Review lists Claude as configured while
      OAuth is connected. Mock provider still works with no keys.
- [x] Tokens never appear in logs, API responses, or the browser; DB rows show
      ciphertext length only.

## Phases

### Phase 1 — Schema and settings plumbing
- Files: `backend/app/models.py`, `backend/app/schemas.py`,
  `backend/app/routers/settings.py`, new Alembic revision.
- Changes:
  - `UserSettings` gains: `claude_auth_mode` (String(20), null = API key),
    `claude_oauth_access_token` (Text, Fernet-encrypted),
    `claude_oauth_refresh_token` (Text, Fernet-encrypted),
    `claude_oauth_expires_at` (DateTime, naive UTC),
    `claude_oauth_account` (String(255), email/plan hint if the token response
    provides it).
  - `SettingsOut` exposes auth mode, connected bool, account and expiry; no
    token fields. `SettingsIn` unchanged (connect/disconnect use dedicated
    endpoints in Phase 4).
  - `delete_provider_key("claude")` also clears the four OAuth fields.
  - Alembic `revision --autogenerate` + `upgrade head`.
- Verify: `alembic upgrade head`; `psql -c "\d user_settings"` shows the five
  columns; `curl /api/settings` is unchanged apart from the new keys.

### Phase 2 — Claude OAuth service
- Files: new `backend/app/services/claude_oauth.py`.
- Changes:
  - Constants: authorize URL, token URL, client id, manual redirect URI,
    scopes, beta header name/value.
  - `start()` → `(authorize_url, state, code_verifier)`; verifier =
    base64url(32 random bytes), challenge = base64url(sha256(verifier)),
    state = random hex. PKCE stays client-side in the Settings tab (stateless;
    the local app has no session store) and is posted back on exchange.
  - `exchange(settings, code, state, code_verifier)` → POST token endpoint,
    JSON `{grant_type: authorization_code, code, redirect_uri, client_id,
    code_verifier, state}`; store encrypted tokens + expiry + account; set
    mode `oauth`. Handles the manual page's `code#state` paste form.
  - `ensure_access_token(settings)` → returns a valid access token; refreshes
    when expiry is within 60 s, POST JSON `{grant_type: refresh_token,
    refresh_token, client_id, scope}` under a module-level `asyncio.Lock`;
    mutates the passed `settings` object and persists the rotated token via a
    short-lived `SessionLocal` (guarded so a concurrent re-login is never
    clobbered).
  - `disconnect(settings)` → clears the fields, mode back to `api_key`.
  - All failures become concise `ClaudeOAuthError` messages ("Session expired —
    reconnect in Settings") with no token text in logs/errors.
- Verify: unit-style script exercises `start()` URL shape and calls
  `exchange()` with a bogus code expecting a clean error; assert encrypted
  round-trip via `crypto.decrypt`.

### Phase 3 — Wire OAuth into LLM and model listing
- Files: `backend/app/services/llm.py`,
  `backend/app/services/model_catalog.py`.
- Changes:
  - `_request_spec` becomes `async`; for `claude` in OAuth mode it awaits
    `ensure_access_token` and sends `Authorization: Bearer …`,
    `anthropic-version`, `anthropic-beta: oauth-2025-04-20`,
    `x-app: cli` (Claude Code compatibility), and **no** `x-api-key`. API-key
    mode keeps today's `x-api-key` headers.
  - `_chat_completion` / `_stream_chat_completion` await the spec builder;
    request/response handling is otherwise unchanged.
  - `list_models("claude")` uses `ensure_access_token` when in OAuth mode and
    the Bearer + beta headers, so the model dropdown works without a key.
  - Errors surface as normal provider failures (review run marked failed with
    a reconnect hint when tokens are expired/revoked).
- Verify: with a connected token, `POST /api/settings/providers/models`
  (`claude`) returns models and a review completes; with `claude_auth_mode`
  set to `api_key` the existing key path still works; mock review unaffected.

### Phase 4 — Settings API endpoints
- Files: `backend/app/routers/settings.py`, `backend/app/schemas.py`.
- Changes:
  - `POST /api/settings/claude/oauth/start` → `{authorize_url, state,
    code_verifier}`.
  - `POST /api/settings/claude/oauth/exchange` body `{code, state,
    code_verifier}` → tokens saved, `llm_provider` promoted from `mock` to
    `claude`, returns `SettingsOut`.
  - `DELETE /api/settings/claude/oauth` → disconnect, returns `SettingsOut`.
  - Map `ClaudeOAuthError` to HTTP 400; validate non-empty inputs.
- Verify: curl start/exchange/disconnect; bogus code → 400; settings show
  `claude_oauth_connected` toggling true/false; no token in responses
  (`grep -i refresh` empty).

### Phase 5 — Frontend
- Files: `frontend/src/api.js`, `frontend/src/llmProviders.js`,
  `frontend/src/pages/SettingsPage.jsx`,
  `frontend/src/components/NewReviewModal.jsx`.
- Changes:
  - `api.js`: `startClaudeOAuth`, `exchangeClaudeOAuth`,
    `disconnectClaudeOAuth`.
  - `llmProviders.js`: `isProviderConfigured(settings, spec)` = masked key OR
    (`claude` + `claude_oauth_connected`); reuse it in Settings and New Review
    instead of `hasStoredKey`.
  - Settings Claude section: "Sign in with Claude" opens the authorize URL in a
    new tab, shows a paste-code field, Connect, and a connected badge with
    account/expiry + Disconnect. Provider cards and the delete confirmation
    describe subscription connections correctly. Model auto-fetch triggers
    when OAuth is connected.
  - New Review modal: OAuth-connected Claude is selectable and labeled
    "subscription".
- Verify: browser pass on http://localhost:5174 (light + dark): connect,
  model list populates, review runs, disconnect restores "no key saved" state;
  API-key entry still works; mock works with no keys.

### Phase 6 — Docs
- Files: `DOCS.md` (LLM providers + API reference + schema + security),
  `AGENTS.md` conventions (one bullet on OAuth precedence/refresh).
- Changes: document the sign-in flow, precedence (OAuth mode wins while
  connected, API key otherwise), token storage/refresh, endpoints, and the
  third-party-client risk.
- Verify: docs match the shipped behavior; no secret values included.

## Out of scope

- Importing the local Claude Code keychain/credentials file (platform-specific,
  prompts for Keychain access).
- The console (`platform.claude.com/oauth/authorize`) API-key OAuth path —
  only the Claude.ai subscription path is exposed.
- Token revocation endpoint calls on disconnect (local deletion only).
- Automatic retry-after-401 with a forced refresh; refresh is pre-emptive
  (60 s window). A 401 surfaces a "reconnect in Settings" error instead.
- Multi-user auth, org/seat management, or showing subscription quotas.
- Any change to API-key encryption or existing provider behavior.

## Database impact

One Alembic migration: add the five `claude_oauth_*` / `claude_auth_mode`
columns to `user_settings`. No data backfill; null `claude_auth_mode` means
API-key mode. No ad-hoc DDL.

## Verification

1. `cd backend && alembic upgrade head`; `psql resumaxxing -c "\d user_settings"`
   shows the new columns; `alembic current` is head.
2. `curl -s localhost:8001/api/settings | jq` → new fields present,
   `claude_oauth_connected=false`, no token values.
3. `curl -s -X POST localhost:8001/api/settings/claude/oauth/start | jq -r .authorize_url`
   → decoded params match the success criteria exactly.
4. Bogus exchange:
   `curl -s -o /tmp/oauth.err -w '%{http_code}' -X POST localhost:8001/api/settings/claude/oauth/exchange -H 'content-type: application/json' -d '{"code":"bogus","state":"x","code_verifier":"abc"}'`
   → `400`; `cat /tmp/oauth.err` has a readable message; `GET /api/settings`
   still reports not connected.
5. Real sign-in (user-performed): open the authorize URL, approve, copy the
   code, paste it in Settings → Connect. Then:
   `curl -s -X POST localhost:8001/api/settings/providers/models -H 'content-type: application/json' -d '{"provider":"claude"}' | jq '.models | length'`
   → non-zero; create a review with `"llm_provider":"claude"` and watch
   `/api/reviews/{id}/events` reach `done`.
6. DB ciphertext check:
   `psql resumaxxing -c "select claude_auth_mode, claude_oauth_account, claude_oauth_expires_at, length(claude_oauth_access_token), length(claude_oauth_refresh_token) from user_settings;"`
   → mode `oauth`, non-empty lengths, no plaintext.
7. Refresh check: force expiry (`update user_settings set claude_oauth_expires_at = now() - interval '1 hour'`), run a model list or review, confirm it succeeds and `claude_oauth_expires_at` moved forward (rotated refresh token persisted).
8. Browser at http://localhost:5174 (light + dark): connect/disconnect states,
   model dropdown, review run on subscription provider, API-key path, and
   mock-with-no-keys all behave as described; Network tab shows only masked
   keys and OAuth status, never tokens.
9. `cd frontend && npm run build` (or the repo's lint/build command) passes.

## Verification evidence — 2026-11-19

- Migration `650b8061ba72` applied; `alembic current` is `650b8061ba72 (head)`;
  `\d user_settings` shows `claude_auth_mode`, `claude_oauth_access_token`,
  `claude_oauth_refresh_token`, `claude_oauth_expires_at`,
  `claude_oauth_account`.
- `GET /api/settings` returned:
  `claude_auth_mode: "api_key"`, `claude_oauth_connected: false`,
  `claude_oauth_account: null`, `claude_oauth_expires_at: null`; no token keys.
- `POST /api/settings/claude/oauth/start` returned
  `https://claude.com/cai/oauth/authorize` with `code=true`,
  `client_id=9d1c250a-e61b-44d9-88ed-5944d1962f5e`, `response_type=code`,
  `redirect_uri=https%3A%2F%2Fplatform.claude.com%2Foauth%2Fcode%2Fcallback`,
  `scope=user%3Aprofile+user%3Ainference`, `code_challenge_method=S256`,
  a 64-char verifier and 32-char state.
- Bogus exchange (`code=bogus`) → HTTP **400**
  `{"detail":"Claude sign-in failed (HTTP 400): Invalid 'code' in request."}`;
  settings stayed disconnected and token columns stayed empty.
- Refresh simulation (expired fake token + monkeypatched token endpoint):
  `ensure_access_token` refreshed once, persisted `new-token`/`refresh-2`
  through the short-lived session, updated `claude_oauth_expires_at` into the
  future, and a second call reused the fresh token without another refresh.
- Header check via `llm._request_spec`: OAuth mode produced `Authorization:
  Bearer …`, `anthropic-beta: oauth-2025-04-20`, `x-app: cli` and **no**
  `x-api-key`; API-key mode still produced `x-api-key` and no `Authorization`.
- Settings UI verified with headless Chrome (1280×1400) in light and dark mode:
  Claude subscription panel, "Sign in with Claude", connected state
  (`dev@example.com`, expiry, Disconnect), provider card showing
  `subscription sign-in`, and the model-list error surfaced as
  "Claude rejected the subscription session…" for the seeded fake token.
- `isProviderConfigured` checked with node: true for OAuth-only and key-only
  Claude, false for none, and false when the OAuth flag is attached to another
  provider (New Review's availability logic).
- `npm run build` completed (142 modules, no errors); `compileall` on
  `backend/app` passed.
- DB restored after tests: `llm_provider=opencode_go`,
  `claude_auth_mode=api_key`, token lengths `0`, account null.
- **Pending (needs the user's Claude account):** real sign-in, model list on a
  real subscription token, and a full review run with `llm_provider=claude`.
  Re-run steps 5–8 above after signing in; those boxes stay unchecked until
  then.
