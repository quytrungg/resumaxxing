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
| `SECRET_KEY` | dev placeholder | derives the Fernet key that encrypts API keys at rest |
| `APP_PASSWORD` | empty (disabled) | optional single-password gate for every `/api` route |
| `SCRAPE_MAX_BYTES` | `2000000` | JD URL response size cap |
| `SCRAPE_TIMEOUT` | `15` | JD URL request timeout (seconds) |

`SECRET_KEY` must stay stable: changing it makes previously stored API keys
undecryptable (they can be re-entered on the Settings page). Generate one with
`python -c "import secrets; print(secrets.token_urlsafe(48))"`.

## API reference

| Method | Path | Purpose |
|---|---|---|
| GET / PUT | `/api/settings` | LLM provider, API keys (masked in responses), base URLs, default models, LinkedIn URL. PUT is a true partial update. |
| POST | `/api/settings/providers/models` | `{provider, api_key?, base_url?}` → `{models: [...]}` from the provider; a blank key uses the saved one. |
| DELETE | `/api/settings/providers/{provider}` | Clear that provider's key, base URL and default model (active provider falls back to `mock`). |
| POST | `/api/cv/upload` | multipart `file` (pdf/docx/txt) → parse + store |
| GET | `/api/cv/latest` | most recent CV |
| POST | `/api/reviews` | `{jd_text}` or `{jd_url}`, optional `llm_provider` (`mock\|claude\|ollama\|opencode\|opencode_go`) + `llm_model` → scrape, resolve the JD title/company, LLM review, score + suggestions. The choice is pinned on the review. |
| GET | `/api/reviews` / `/api/reviews/{id}` | list / detail (suggestions, keyword coverage, score history, final document, cover letter, `jd_title`/`jd_company`) |
| PATCH | `/api/reviews/{id}/suggestions/{sid}` | `{status: ACCEPTED\|REJECTED\|PENDING}` → status only; no LLM call, score/coverage unchanged. `PENDING` is Undo. |
| POST | `/api/reviews/{id}/rescore` | re-score from current accepted/rejected/pending choices (one LLM call) → score, keyword coverage, new history entry |
| POST | `/api/reviews/{id}/finalize?format=docx\|pdf&mode=polished\|quick` | polished: LLM rewrite + structured render (stored, reused on repeat); quick: merge-only |
| POST | `/api/reviews/{id}/cover-letter` | generate from the finalized CV + JD (409 until finalized) |
| PUT | `/api/reviews/{id}/cover-letter` | save edits `{text}` |
| POST | `/api/reviews/{id}/cover-letter/export?format=docx\|pdf` | download the saved letter |
| GET | `/api/auth` | `{required: bool}` — whether a password is configured |
| GET | `/api/health` | liveness (never password-protected) |

Interactive docs at `http://localhost:8001/docs` while the backend runs.

## Database schema

Alembic-managed (`backend/alembic/`; revisions `78c3f4a7ed00` → `319d33f05a24`):
`users`, `user_settings` (provider + encrypted keys + base URLs + default models
+ LinkedIn URL),
`base_cvs` (file path + parsed text),
`job_descriptions` (URL + raw text + resolved `title`/`company`),
`cv_reviews` (score, draft/finalized, pinned `llm_provider`/`llm_model`,
`final_document` JSON, `cover_letter`),
`suggestions` (ADD/REMOVE/UPDATE × PENDING/ACCEPTED/REJECTED),
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
`glm-5.3`).

- `mock` (default) — deterministic keyword-overlap heuristic, no keys needed
- `claude` — Anthropic Messages API (`claude_key`)
- `ollama` — Ollama Cloud, OpenAI-compatible `/v1` (`ollama_key`); point the base
  URL at `http://localhost:11434` to use a local daemon instead
- `opencode` — Opencode Zen, OpenAI-compatible (`opencode_key`)
- `opencode_go` — Opencode Go subscription, OpenAI-compatible
  (`opencode_go_key`, base `https://opencode.ai/zen/go`); Go keys are separate
  from Zen keys and every request carries a stable `x-opencode-session` header
  (a hash of the CV + JD) because the endpoint rejects requests without one

Each provider row in Settings can override its base URL and default model. The
Settings page lists models from `{base}/v1/models` with the typed or saved key
(`services/model_catalog.py`) and caches the result in `localStorage`; the New
Review modal reuses that catalog for its model picker.

Prompts enforce structured JSON: suggestions (`type`, `target_section`,
`original_text`, `suggested_text`, `reasoning`), a scoring call returning
`{"score": 0-100}`, and a finalize rewrite returning
`{name, headline, contact[], sections[{heading, bullets[]}]}`. Cover letters are
plain text. If a rewrite call fails the backend falls back to the deterministic
structurer in `services/document.py`, so finalize never breaks.

`services/keywords.py` owns JD keyword extraction and ATS coverage
(`{matched, missing, coverage}`). It is heuristic-only, so coverage is identical
for every provider and needs no key; the `mock` score is exactly that coverage.

## Security

- API keys are encrypted at rest with Fernet (`services/crypto.py`, key derived
  from `SECRET_KEY`) and never returned in plaintext — `GET /api/settings` shows
  masks like `sk-ant…wxyz`. Legacy plaintext values still decrypt and are
  re-encrypted on the next save.
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
- No automated tests yet; verification is manual (curl + browser).
- Keyword matching is literal (no stemming/synonyms), so ATS coverage is a
  heuristic signal.
- Reviews cannot be renamed, archived or deleted yet.
