# Detailed Documentation

## Full setup

```bash
# Database (once)
createdb resumaxxing

# Backend
cd backend
cp .env.example .env                # set SECRET_KEY (see Configuration)
uv venv .venv --python 3.12
uv pip install -r requirements.txt --python .venv/bin/python
.venv/bin/alembic upgrade head      # apply migrations
.venv/bin/uvicorn app.main:app --port 8001

# Frontend
cd frontend
npm install
npm run dev                         # http://localhost:5174 (next free port if taken)
```

The Vite dev server proxies `/api` to `http://localhost:8001` (see
`frontend/vite.config.js`). CORS is also open for localhost:5173/5174 for
direct calls.

## Configuration

`backend/app/config.py` (override via `backend/.env`, see `backend/.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://localhost:5432/resumaxxing` | SQLAlchemy URL |
| `UPLOAD_DIR` | `uploads` (relative to backend CWD) | uploaded CV files |
| `DEFAULT_USER_EMAIL` | `local@resumaxxing.dev` | single-user identity |
| `SECRET_KEY` | dev placeholder | derives the Fernet key that encrypts API keys and Claude OAuth tokens at rest |
| `APP_PASSWORD` | empty (disabled) | optional single-password gate for every `/api` route |
| `SCRAPE_MAX_BYTES` | `2000000` | JD URL response size cap |
| `SCRAPE_TIMEOUT` | `15` | JD URL request timeout (seconds) |

`SECRET_KEY` must stay stable: changing it makes previously stored API keys and
Claude OAuth tokens undecryptable (re-enter the key or sign in again on the
Settings page). Generate one with
`python -c "import secrets; print(secrets.token_urlsafe(48))"`.

## API reference

| Method | Path | Purpose |
|---|---|---|
| GET / PUT | `/api/settings` | LLM provider, API keys (masked in responses), base URLs, default models, LinkedIn URL. PUT is a true partial update. |
| POST | `/api/settings/providers/models` | `{provider, api_key?, base_url?}` → `{models: [...]}` from the provider; a blank key uses the saved one. |
| DELETE | `/api/settings/providers/{provider}` | Clear that provider's key, base URL and default model (active provider falls back to `mock`). For `claude` this also signs out the subscription session. |
| POST | `/api/settings/claude/oauth/start` | Begin Claude subscription sign-in → `{authorize_url, state, code_verifier}` (PKCE; open the URL, then paste the code back). |
| POST | `/api/settings/claude/oauth/exchange` | `{code, state, code_verifier}` → store encrypted tokens, switch Claude to OAuth mode, return settings. Bogus codes are 400. |
| DELETE | `/api/settings/claude/oauth` | Sign out of the subscription session (clears tokens, mode back to API key; provider falls back to `mock` when no key remains). |
| POST | `/api/cv/upload` | multipart `file` (pdf/docx/txt) → parse + store |
| GET | `/api/cv/latest` | most recent CV |
| POST | `/api/reviews` | `{jd_text}` or `{jd_url}`, optional `llm_provider` (`mock\|claude\|ollama\|opencode\|opencode_go`) + `llm_model` → **202** with `run_state: "running"`; the JD is scraped first (bad URLs still 400), then the LLM review runs in the background. The choice is pinned on the review. |
| GET | `/api/reviews` / `/api/reviews/{id}` | list / detail (suggestions, ATS requirements + coverage, score history, final document, cover letter, `jd_title`/`jd_company`, `run_state`/`run_error`) |
| GET | `/api/reviews/{id}/events` | SSE stream for a running review: `stage`, `delta` (`kind: thinking\|output`), then one `done` or `error` frame. Replays buffered events on connect; a finished review yields one terminal frame. |
| PATCH | `/api/reviews/{id}/suggestions/{sid}` | `{status: ACCEPTED\|REJECTED\|PENDING}` → status only; no LLM call, score/coverage unchanged. `PENDING` is Undo. |
| PUT | `/api/reviews/{id}/suggestions/{sid}/text` | `{suggested_text}` → save the user's own wording for an ADD/UPDATE suggestion. The first AI text is kept in `original_suggested_text`; status is untouched, no LLM call, stored downloads are cleared. REMOVE and blank text are 400/422. |
| DELETE | `/api/reviews/{id}/suggestions/{sid}/text` | restore the AI wording saved in `original_suggested_text` and clear it; 400 when there is nothing to restore. |
| POST | `/api/reviews/{id}/rescore` | re-score from current accepted/rejected/pending choices (one LLM call) → score, ATS requirements + coverage, new history entry |
| POST | `/api/reviews/{id}/finalize?format=docx\|pdf\|tex` | rewrite the CV (stored, reused on repeat): `docx`/`pdf` render the structured document in the LaTeX template's layout, `tex` returns a LaTeX source file. Any suggestion decision or text edit clears the stored outputs. |
| POST | `/api/reviews/{id}/cover-letter` | generate from your CV with accepted suggestions + JD; no finalize needed |
| PUT | `/api/reviews/{id}/cover-letter` | save edits `{text}` |
| POST | `/api/reviews/{id}/cover-letter/export?format=docx\|pdf` | download the saved letter |
| GET | `/api/auth` | `{required: bool}` — whether a password is configured |
| GET | `/api/health` | liveness (never password-protected) |

Interactive docs at `http://localhost:8001/docs` while the backend runs.

### Async review runs

Creating a review no longer blocks on the model. `POST /api/reviews` persists the
row (`run_state="running"`), schedules `_run_review` on the running event loop
and returns immediately, so the modal navigates straight to
`/reviews/{id}`. That page subscribes to `GET /api/reviews/{id}/events` and
renders a thinking panel: five stages (job description → CV scan → ATS
requirements → drafting suggestions → scoring), each with the model's own
streamed text nested under the active one. Requirement extraction is not an
input to the suggestion/scoring prompt, so it runs **concurrently** with the
generation call (the panel keeps its stage row spinning until its result lands);
the initial review needs only one generation call because the score is part of
the suggestion payload. Reasoning-capable models surface
`reasoning_content`/`thinking` deltas; once the JSON payload starts, the panel
shows a "composing" state instead of dumping raw JSON. On `done` the page
re-fetches the review and swaps to the normal view with no reload.

The run finishes with one of:

- `complete` — suggestions and score committed together with the `initial
  review` score event;
- `failed` — `run_error` holds a readable message, no partial suggestions and
  `current_score` stays 0.

Run state is persisted (`cv_reviews.run_state`, `run_error`); the transcript is
not. The event buffer lives in `services/progress.py`, in this process only, so
the backend must run as a single uvicorn worker. A review left `running` after a
restart is reconciled to `failed` ("Interrupted…") the next time its detail page
or stream is requested, so it never spins forever.

All provider I/O is async (`httpx.AsyncClient`), so a language-model call never
blocks other requests; JD scraping runs in a worker thread.

## Database schema

Alembic-managed (`backend/alembic/`; revisions `78c3f4a7ed00` → `650b8061ba72`):
`users`, `user_settings` (provider + encrypted keys + base URLs + default models
+ LinkedIn URL + encrypted Claude OAuth session: `claude_auth_mode`,
`claude_oauth_access_token`, `claude_oauth_refresh_token`,
`claude_oauth_expires_at`, `claude_oauth_account`),
`base_cvs` (file path + parsed text),
`job_descriptions` (URL + raw text + resolved `title`/`company`),
`cv_reviews` (score, draft/finalized, pinned `llm_provider`/`llm_model`,
`final_document` JSON, `final_latex` source, `cover_letter`, background-run
`run_state`/`run_error`),
`suggestions` (ADD/REMOVE/UPDATE × PENDING/ACCEPTED/REJECTED; `original_suggested_text`
holds the first AI wording once the user edits `suggested_text`),
`score_events` (score history: one row per review creation and per decision).

Migrations: edit `backend/app/models.py`, then
`.venv/bin/alembic revision --autogenerate -m "<msg>"` and
`.venv/bin/alembic upgrade head`.

## LLM providers

`backend/app/services/llm.py` routes on the review's pinned provider
(`cv_reviews.llm_provider`, chosen in the New Review modal) and falls back to
`user_settings.llm_provider` for reviews created before this existed. Model
resolution is per-review `llm_model` → provider default saved in Settings →
built-in default (`claude-sonnet-4-5`, `gpt-oss:120b-cloud`, `grok-code`,
`deepseek-v4.1-flash`). Keep the built-in defaults in step with each provider's
current model catalog: a retired model makes every review that does not pin one
fail (OpenCode Go removed `glm-5.3`, so it is no longer the default).

- `mock` (default) — deterministic keyword-overlap heuristic, no keys needed
- `claude` — Anthropic Messages API; use `claude_key` or sign in with a Claude
  subscription (OAuth). When `claude_auth_mode = 'oauth'` and a refresh token is
  stored, OAuth wins over the key: requests send `Authorization: Bearer …` with
  `anthropic-beta: oauth-2025-04-20` and no `x-api-key`. Access tokens refresh
  automatically; the rotated refresh token is persisted.
- `ollama` — Ollama Cloud, OpenAI-compatible `/v1` (`ollama_key`); point the base
  URL at `http://localhost:11434` to use a local daemon instead
- `opencode` — Opencode Zen, OpenAI-compatible (`opencode_key`)
- `opencode_go` — Opencode Go subscription, OpenAI-compatible
  (`opencode_go_key`, base `https://opencode.ai/zen/go`); Go keys are separate
  from Zen keys and every request carries a stable `x-opencode-session` header
  (a hash of the CV + JD) because the endpoint rejects requests without one

Each provider row in Settings can override its base URL and default model. The
Settings page lists models from `{base}/v1/models` with the typed or saved key
(or the Claude OAuth bearer token when the subscription is connected;
`services/model_catalog.py`) and caches the result in `localStorage`; the New
Review modal reuses that catalog for its model picker.

Review prompts ask for a short prose analysis *before* the JSON so the thinking
panel has something human-readable to stream; `_extract_json` tolerates leading
prose. The payloads stay structured: one initial-review call returning
`{"score": 0-100, "suggestions": [{"type", "target_section", "original_text",
"suggested_text", "reasoning"}]}`, a standalone scoring call returning
`{"score": 0-100}` for `/rescore` (both share `SCORE_RUBRIC`, which asks the
model to score the CV *as provided*), and a finalize rewrite returning
`{name, headline, contact[], sections[{heading, bullets[]}]}`. A payload without
a usable score (or a legacy top-level suggestion array) falls back to one
standalone scoring call, so the review never ends scoreless. The structured
rewrite applies the same top-tier content standards as the LaTeX rewrite
(summary first, reverse-chronological action-verb bullets, grouped skills, no
invented facts) so Word, PDF and LaTeX read alike. Cover letters are
plain text. The `.tex` download asks the model to rewrite the CV to top-tier
software-engineer standards and to keep the pinned preamble; the backend keeps
only the document body from that response, re-applies the known-good preamble
from `services/latex.py` (so the layout never depends on the model), rejects
unbalanced or unsafe source (file-reading/shell primitives) and falls back to
the deterministic template otherwise. `services/export.py` owns the single
layout spec (`CV_LAYOUT`) that the Word and PDF renderers share with that
template. If the structured rewrite call fails the backend falls back to the
deterministic structurer in `services/document.py`, so finalize never breaks.

### ATS requirements and coverage

`services/requirements.py` owns the ATS signal, split into two halves:

- **Extraction** (`llm.extract_requirements`) runs once per review with the
  pinned provider, in parallel with the suggestion/score generation call, and
  stores `{label, canonical, aliases, importance, category, quote}` on
  `job_descriptions.jd_requirements`. The model is asked for 8–20 atomic labels
  with up to four aliases; `quote` is derived locally from the JD
  (`requirements.quote_for`) instead of being returned by the model, and is
  shown as evidence in the panel. A review whose posting text and provider match
  a completed earlier review reuses that stored list instead of calling the
  model again. `importance` is `must` or `nice`; alias lists let a category
  ("front-end frameworks") be satisfied by a concrete tool ("React").
- **Matching** is deterministic and provider-independent: word-boundary regexes
  plus the surface forms in `services/skills_aliases.py`. `java` never matches
  inside `javascript`, and CJK-free skills like `C++`/`C#`/`.net` are matched
  exactly. Ambiguous terms (`Go`, `React`, `Flask`) are matched case-sensitively
  so prose does not count as a skill.

`GET /api/reviews/{id}` returns `requirements[]` with per-item `matched`, a
weighted `keyword_coverage` (must-have is worth three nice-to-haves) and the
`must_have_coverage` / `nice_to_have_coverage` split. Rows created before the
column existed fall back to `requirements.from_heuristic()` at read time, so no
backfill is needed.

`services/keywords.py` still owns the word-frequency extractor: it backs the
`mock`/offline fallback list, the `mock` score and the template cover letter.
The `mock` score is exactly that old coverage number.

## Security

- API keys are encrypted at rest with Fernet (`services/crypto.py`, key derived
  from `SECRET_KEY`) and never returned in plaintext — `GET /api/settings` shows
  masks like `sk-ant…wxyz`. Legacy plaintext values still decrypt and are
  re-encrypted on the next save.
- Claude OAuth access/refresh tokens use the same encryption and are never
  returned by the API; settings only expose connection state, account label and
  access-token expiry. Refresh tokens rotate, so the new pair is persisted
  immediately and guarded against overwriting a newer sign-in.
- `PUT /api/settings` uses `exclude_unset` semantics, and blank/masked key
  fields never overwrite a stored key.
- Model-list lookups accept a transient key for the request only; the key is
  never returned or logged. Base URLs must be http(s), and provider errors are
  mapped to readable messages without echoing credentials.
- JD scraping (`services/scrape.py`) allows only http(s), rejects hosts that
  resolve to private/loopback/link-local/reserved addresses (revalidated on
  each redirect, max 3), caps the body size and timeout.
- Set `APP_PASSWORD` to require an `X-App-Password` header on every `/api`
  route except `/api/health` and `/api/auth`; the UI prompts for it and stores
  it in `localStorage`. Empty (default) = no gate.

## Known limitations

- No multi-user accounts or sessions — a single default user is auto-provisioned.
- Claude subscription sign-in reuses Claude Code's undocumented OAuth client and
  endpoints (`services/claude_oauth.py`); Anthropic can change or restrict this
  at any time, and subscription usage limits still apply. The API-key path is
  the supported fallback.
- No automated tests yet; verification is manual (curl + browser).
- Review runs are single-process only: the progress broker is in-memory, so the
  app must be served by one uvicorn worker. The thinking transcript is not
  persisted and a run interrupted by a restart loses its partial results (the
  row is marked `failed` on the next read).
- Requirement extraction needs a real provider: with `mock` (or when the call
  fails) the list degrades to the word-frequency fallback, which still contains
  single-word noise.
- Matching is literal plus the curated alias table — no stemming, embeddings or
  semantic category inference. A synonym missing from `skills_aliases.py` reads
  as a miss.
- The heuristic ADD suggestions for `mock` still come from the old keyword list,
  so they can propose filler such as `- Deep`; real providers do not.
- Reviews cannot be renamed, archived or deleted yet.
- LaTeX downloads are served as source only — nothing is compiled server-side,
  so a local TeX toolchain (`pdflatex`) is needed to produce a PDF from the
  `.tex` file. The `pdf` and `docx` downloads re-implement that template's
  layout natively (`services/export.py`), using Times as the closest available
  stand-in for Latin Modern.
