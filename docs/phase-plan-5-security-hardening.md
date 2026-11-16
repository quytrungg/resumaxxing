# Phase Plan — Initiative 5: Security & multi-user hardening

> Implements INITIATIVES.md #5. Local-only app, so no account system; the
> optional password gate is opt-in via env.

## Goal

Stop leaking API keys to the browser, encrypt them at rest, make settings
updates truly partial, harden the JD URL scraper against SSRF/oversized
responses, and add an optional single-password gate for non-localhost use.

## Success criteria

- [ ] `GET /api/settings` returns no plaintext key; keys appear as
      `sk-ant-…wxyz`-style masks (empty string when unset).
- [ ] Keys are stored encrypted (Fernet) in Postgres; `psql` shows a
      `gAAAA...` token, and the LLM call still works after a restart.
- [ ] Legacy plaintext keys already in the DB keep working (decrypt falls back)
      and are re-encrypted on the next save.
- [ ] `PUT /api/settings` with only `{"linkedin_url": "..."}` leaves provider and
      keys untouched (`exclude_unset` semantics); blank key fields never wipe.
- [ ] `_scrape_url` rejects non-http(s), private/loopback/link-local/reserved
      hosts (including via redirects), caps response bytes and timeout.
- [ ] With `APP_PASSWORD` unset the app behaves exactly as before. With it set,
      every `/api` route except `/api/health` and `/api/auth` returns 401
      without the `X-App-Password` header; the UI shows a password prompt.

## Phases

### Phase 1 — Config + crypto
- Files: `backend/app/config.py`, `backend/app/services/crypto.py` (new),
  `backend/.env` + `backend/.env.example` (new)
- Changes: `secret_key` (Fernet key material), `app_password`,
  `scrape_max_bytes`, `scrape_timeout`; `encrypt()`/`decrypt()` helpers with
  legacy-plaintext fallback; generated `.env` with `SECRET_KEY`.
- Verify: `python -c` encrypt→decrypt round-trip; DB rows show ciphertext.

### Phase 2 — Settings hardening
- Files: `backend/app/routers/settings.py`, `backend/app/schemas.py`,
  `backend/app/services/llm.py`
- Changes: mask on read/write responses; encrypt non-blank keys on save;
  `exclude_unset=True` partial update; decrypt where providers use keys.
- Verify: curl GET masks; curl PUT partial does not wipe; `psql` ciphertext.

### Phase 3 — SSRF guard
- Files: `backend/app/services/scrape.py` (new),
  `backend/app/routers/reviews.py`
- Changes: scheme allowlist, DNS resolve + ipaddress guard (private, loopback,
  link-local, multicast, reserved, unspecified), manual redirect loop (max 3,
  each hop validated), streamed size cap, timeout, text/html check.
- Verify: curl JD URL `http://127.0.0.1:8001/api/health` and
  `http://localhost:...` → 400; a public URL still scrapes.

### Phase 4 — Optional password gate
- Files: `backend/app/main.py`, `frontend/src/api.js`, `frontend/src/App.jsx`,
  `frontend/src/components/PasswordGate.jsx` (new)
- Changes: middleware comparing `X-App-Password` to `app_password` (constant
  time) when configured; `GET /api/auth` reports `{required: bool}`; frontend
  stores the password in `localStorage`, attaches it to every `/api` request,
  and renders a prompt when the API answers 401.
- Verify: unset → no prompt; set → 401 without header, 200 with; browser prompt
  works and survives reload.

## Out of scope

- Multi-user accounts, sessions, OAuth, password hashing/rotation UI.
- Encrypting CV text or JD text at rest.
- TLS termination / deployment configuration.

## Database impact

No schema change (key columns stay `Text`; they now hold ciphertext). Existing
plaintext values are tolerated and upgraded on next save — no ad-hoc DDL.

## Verification

1. `psql resumaxxing -c "select length(claude_key), left(claude_key,4) from user_settings"`
   → ciphertext prefix, not `sk-a`.
2. `curl -s localhost:8001/api/settings | jq` → masked keys only.
3. `curl -X PUT -d '{"linkedin_url":"https://linkedin.com/in/x"}'` → provider
   and keys unchanged.
4. SSRF curls as in Phase 3 (localhost + a redirector) are rejected.
5. `APP_PASSWORD=test` restart → 401/200 matrix; browser prompt.
