# Detailed Documentation

## Full setup

```bash
# Database (once)
createdb resumaxxing

# Backend
cd backend
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

`backend/app/config.py` (override via `backend/.env`):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://localhost:5432/resumaxxing` | SQLAlchemy URL |
| `UPLOAD_DIR` | `uploads` (relative to backend CWD) | uploaded CV files |
| `DEFAULT_USER_EMAIL` | `local@resumaxxing.dev` | single-user identity |

## API reference

| Method | Path | Purpose |
|---|---|---|
| GET / PUT | `/api/settings` | LLM provider, API keys, LinkedIn URL |
| POST | `/api/cv/upload` | multipart `file` (pdf/docx/txt) → parse + store |
| GET | `/api/cv/latest` | most recent CV |
| POST | `/api/reviews` | `{jd_text}` or `{jd_url}` → scrape, LLM review, score + suggestions |
| GET | `/api/reviews` / `/api/reviews/{id}` | list / detail (incl. suggestions) |
| PATCH | `/api/reviews/{id}/suggestions/{sid}` | `{status: ACCEPTED|REJECTED|PENDING}` → returns new score |
| POST | `/api/reviews/{id}/finalize?format=docx|pdf` | merge accepted changes, mark finalized, download file |
| GET | `/api/health` | liveness |

Interactive docs at `http://localhost:8001/docs` while the backend runs.

## Database schema

Alembic-managed (`backend/alembic/`, initial revision `78c3f4a7ed00`):
`users`, `user_settings` (provider + keys + LinkedIn URL), `base_cvs`
(file path + parsed text), `job_descriptions` (URL + raw text),
`cv_reviews` (score, draft/finalized), `suggestions` (ADD/REMOVE/UPDATE ×
PENDING/ACCEPTED/REJECTED).

Migrations: edit `backend/app/models.py`, then
`.venv/bin/alembic revision --autogenerate -m "<msg>"` and
`.venv/bin/alembic upgrade head`.

## LLM providers

`backend/app/services/llm.py` routes on `user_settings.llm_provider`:

- `mock` (default) — deterministic keyword-overlap heuristic, no keys needed
- `claude` — Anthropic Messages API (`claude_key`)
- `ollama` — Ollama Cloud, OpenAI-compatible `/v1` (`ollama_key`)
- `opencode` — Opencode Zen, OpenAI-compatible (`opencode_key`)

Prompts enforce structured JSON: suggestions (`type`, `target_section`,
`original_text`, `suggested_text`, `reasoning`) and a scoring call returning
`{"score": 0-100}`. Blank key fields in the Settings UI never overwrite
saved keys server-side.

## Known limitations

Review findings live in `INITIATIVES.md`; the short list:

- `GET /api/settings` returns raw API keys; keys are unencrypted at rest
  (Initiative 5).
- Finalize merges by string replacement — no LLM rewrite yet (Initiative 1);
  PDF export truncates long lines.
- No auth — a single default user is auto-provisioned.
- `_scrape_url` has no size/host guard — localhost use only.
- No tests yet; repo is not git-initialized.
