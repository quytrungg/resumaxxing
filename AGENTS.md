# AGENTS.md — Resumaxxing

Rules and repo knowledge for any agent working in this repository.

## Repo map

- `backend/` — FastAPI + SQLAlchemy + Alembic + PostgreSQL
  - `app/models.py` — all ORM models and enums (single file by design)
  - `app/routers/` — settings.py, cv.py, reviews.py
  - `app/services/` — llm.py (provider router + heuristic), parsing.py, export.py
  - `alembic/` — migrations; `prepend_sys_path = .` is set in alembic.ini
- `frontend/` — React 18 + Vite + Tailwind v3 + react-diff-viewer-continued
  - `src/api.js` — every backend call goes through this module
  - `src/components/NewReviewModal.jsx` — review creation is a modal on the
    Reviews page, not a standalone route
- `MASTER_PROMPT.md` — original product spec; consult before changing behavior
- `INITIATIVES.md` — review findings and the 5 planned features
- `DOCS.md` — setup, config, API reference, schema, known limitations

## Rules

1. **Phase plan before implementation.** Before implementing any new feature,
   write a phase-plan markdown file in `docs/` using
   `docs/phase-plan-template.md`. A plan has: goal, success criteria (verifiable),
   phased steps with file-level scope, and a verification section. No code until
   the plan exists and the user has confirmed it.

2. **Database changes.** Schema changes go through Alembic
   (`alembic revision --autogenerate` → `upgrade head`). Exception: one-off
   repairs to a drifted local DB are applied as ad-hoc DDL and recorded in the
   feature's phase plan — never as an Alembic migration. Keep
   `alembic_version` at head.

3. **Surgical changes.** Touch only what the task needs. Match existing style:
   Python uses pydantic v2 schemas and dependency-injected sessions; frontend
   is functional components + hooks, no TypeScript, Tailwind utility classes
   for all styling.

4. **Secrets.** Never hardcode keys. API keys live in the DB and enter only via
   the Settings page; never log or echo them (Hermes redacts secret-looking
   values in tool output — don't mistake `***` in terminal output for stored
   data; verify with `length()`/`md5()` instead).

5. **Verify before claiming done.** Backend changes: keep uvicorn running and
   exercise the endpoint with curl. Frontend changes: verify in a real browser
   (vite HMR picks changes up; no restart needed). The app must work end-to-end
   with the `mock` provider and no API keys.

## Environment facts

- Backend runs on port **8001** (8000 is occupied by another local service).
- Frontend dev port is **5174** (5173 is occupied — another app, not this one).
- Vite proxies `/api` → 8001; CORS additionally allows 5173/5174.
- PostgreSQL is the local homebrew postgresql@15; database name `resumaxxing`.
- Single-user local mode: `get_default_user()` auto-provisions
  `local@resumaxxing.dev` — there is no auth.
- The repo is not git-initialized yet.

## Conventions worth knowing

- Settings: the UI shows exactly one API-key field matching the selected
  provider; blank key fields never overwrite saved keys server-side.
- All suggestion status changes go through the PATCH endpoint, which
  re-scores synchronously and returns the new score.
- Export: `build_final_text(base_text, suggestions)` merges ACCEPTED changes;
  keep it the single merge path for both DOCX and PDF.
