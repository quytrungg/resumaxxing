# Resumaxxing

Upload your CV, paste a Job Description, and get Git-style diff suggestions
(ADD / REMOVE / UPDATE) to tailor the CV to the role. Accept or reject each
suggestion while a match score updates live, then export the optimized CV as
DOCX or PDF.

## Highlights

- **Git-style suggestion UI** — every LLM suggestion renders as a colored diff
  card (green additions, red deletions, word-level inline diffs for rewrites)
  with Accept / Reject buttons.
- **Live match score** — a score gauge re-evaluates the CV against the JD after
  every decision.
- **Pluggable LLM providers** — Claude, Ollama Cloud, and Opencode (Zen); plus a
  built-in `mock` keyword-heuristic provider so the whole app works with no API
  keys.
- **JD from text or URL** — paste the description or point the backend at a
  posting URL to scrape.
- **One-click export** — final CV with all accepted changes, as DOCX or PDF.

## Architecture

```
frontend/  React (Vite) + Tailwind CSS + react-diff-viewer-continued
              │  /api proxy (port 5174 in dev)
              ▼
backend/   FastAPI + SQLAlchemy + Alembic
              ├── routers/    settings, cv upload, reviews/suggestions/finalize
              ├── services/   LLM router, CV parsing, scoring, export
              └── models.py   users, settings, CVs, JDs, reviews, suggestions
              │
              ▼
           PostgreSQL (database: resumaxxing)
```

Flow: Upload CV → paste JD → LLM returns score + suggestions → accept/reject
(live rescore) → finalize → download tailored CV.

## Requirements

- PostgreSQL (developed against homebrew postgresql@15)
- Python 3.12 via [uv](https://docs.astral.sh/uv/)
- Node 18+

## Quick start

```bash
createdb resumaxxing

cd backend
uv venv .venv --python 3.12
uv pip install -r requirements.txt --python .venv/bin/python
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --port 8001

# in a second shell
cd frontend && npm install && npm run dev
```

Open the printed Vite URL (http://localhost:5174). No configuration is needed
to try it — the default `mock` LLM provider runs fully offline; add real API
keys later on the Settings page.
