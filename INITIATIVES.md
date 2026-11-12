# Resumaxxing — Initiatives

Five candidate features, ordered by value-to-effort. Each lists the problem it
solves (grounded in the code review of the current codebase), the scope, and a
rough effort estimate.

## 1. LLM-Powered Final Rewrite & Polished Export

**Problem.** The master spec (Phase 6) says the LLM should format accepted
changes into "a cohesive, professional CV document". Today
`backend/app/services/export.py:build_final_text` just string-replaces and
appends bullet lines, and the PDF renderer truncates lines at 110 characters.
Accepting six "+ skill" suggestions produces a disjointed bulge at the bottom
of the document.

**Scope.**
- On finalize, send base CV + accepted suggestions + JD to the configured LLM
  with a "rewrite into a cohesive CV, output structured JSON (sections/bullets)"
  prompt; keep a pure-text fallback for the `mock` provider.
- Render the structured result with a proper DOCX template (headings, styles)
  via python-docx and a layout-correct PDF via reportlab (no truncation).
- Keep the merge-only path as a "quick export" option.

**Effort.** Medium. High user-visible impact.

## 2. Undoable Decisions & Score History

**Problem.** The PATCH endpoint already supports flipping a suggestion's
status, but decided cards hide the buttons — a misclick on Accept/Reject is
permanent in the UI. There is also no record of how the score evolved across
decisions, which is half the fun of the tool.

**Scope.**
- Add "Undo" on decided cards (calls the existing PATCH, already supported).
- Persist a score-history table (or JSON column on CVReview) appended on every
  decision; render a small sparkline/step chart on the review page.
- Backfill Alembic migration for the new column/table.

**Effort.** Small. Mostly frontend + one migration.

## 3. ATS Keyword Coverage Panel

**Problem.** The `mock` provider already computes JD keyword overlap, but discards
the detail — users can't see *which* JD keywords their CV covers vs misses, which
is exactly what real ATS scanners report. With a real LLM provider configured
there is no deterministic signal at all.

**Scope.**
- Extract the keyword matcher (already in `services/llm.py`) into a first-class
  service returning `{matched: [...], missing: [...], coverage: %}`.
- Recompute on every accept/reject alongside the score; show as two chip lists
  (green covered / red missing) on the review page.
- Works identically for all providers since it's heuristic-only.

**Effort.** Small–medium. High informational value; complements rather than
duplicates the LLM score.

## 4. Cover Letter Generation

**Problem.** The app already stores the three inputs a cover letter needs
(tailored CV, JD, optional LinkedIn URL) — generating one is the natural next
artifact in a job application and reuses 100% of existing infrastructure.

**Scope.**
- New endpoint `POST /api/reviews/{id}/cover-letter` reusing the LLM service
  router with a cover-letter prompt; store the result on the review row.
- UI: "Generate Cover Letter" button on the review page (enabled after
  finalize), inline editor, download as DOCX/PDF via the existing export path.
- `mock` provider: template-based letter with JD keywords slotted in.

**Effort.** Medium. Unlocks a second deliverable from the same workflow.

## 5. Security & Multi-User Hardening

**Problem.** Review findings: `GET /settings` returns raw plaintext API keys;
keys sit unencrypted in Postgres; `save_settings` wipes non-key fields the
client omits (verified bug); URL scraping has no SSRF guard; there is no auth
at all (single hardcoded default user).

**Scope.**
- Mask keys in API responses (`"sk-ant-…wxyz"`), store them encrypted at rest
  (Fernet, key in `backend/.env`).
- Fix `save_settings` to true partial-update semantics (`exclude_unset=True`).
- Add response-size and host allowlist limits to `_scrape_url`; block
  link-local/private ranges.
- Optional: lightweight local auth (single user, password from env) or full
  multi-user accounts if the tool is ever hosted.

**Effort.** Medium. Prerequisite before any non-localhost deployment.

---

### Honorable mentions
Review management (rename/delete/archive reviews and CVs), LinkedIn profile
import to enrich the base CV, git init + pytest/vitest baseline + CI.
