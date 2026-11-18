# Phase Plan — 15: Drop quick merge, add a LaTeX download

> Required by AGENTS.md rule 1: this plan must exist and be confirmed by the
> user before any implementation code is written.

## Goal

Simplify the CV download menu to a single behaviour — an LLM rewrite of the CV
tailored to the job description — and add LaTeX as a third output format next
to Word and PDF. The LaTeX output is a standalone `.tex` file whose content is
rewritten to top-tier software-engineer CV standards (one page, quantified
impact, ATS-friendly, no invented facts). The export menu shows no internal
jargon: no "LLM rewrite", no "quick merge".

## Success criteria

- [x] The export menu on the Review page contains exactly three items —
      `Word (.docx)`, `PDF`, `LaTeX (.tex)` — and no occurrence of "quick",
      "merge" or "LLM".
- [x] `POST /api/reviews/{id}/finalize?format=docx` returns a styled DOCX, and
      `format=pdf` a PDF (unchanged rendering), with no `mode` parameter.
- [x] `format=quick` / `mode=quick` no longer exist: the endpoint rejects any
      unsupported `format` with HTTP 400.
- [x] `POST /api/reviews/{id}/finalize?format=tex` returns
      `application/x-tex` with a filename ending `.tex` whose body starts with
      `\documentclass` and contains balanced `\begin{document}`/`\end{document}`.
- [x] The `.tex` source is persisted on `cv_reviews.final_latex`, reused on a
      repeat download (no second generation), and cleared when any suggestion
      status changes.
- [x] With provider `mock` and no API keys, all three formats work: docx, pdf,
      and `tex` via the deterministic LaTeX renderer.
- [x] Every generated `.tex` compiles with a stock `pdflatex` run (or, when no
      LaTeX toolchain is installed, passes structural + escape checks and the
      limitation is recorded in this plan's Verification section).

## Phases

### Phase 1 — LaTeX service
- Files: `backend/app/services/latex.py` (new)
- Changes:
  - `escape_latex(text)` — escapes `\ & % $ # _ { } ~ ^`.
  - `render_document(cv: StructuredCV) -> str` — deterministic, single-column,
    ATS-friendly template (`article`, `geometry`, `enumitem`, `titlesec`,
    `hyperref`, `fontenc`/`lmodern`), name/headline/contact header, ruled
    section headings, `itemize` bullets.
  - `sanitize_latex(source)` — strip markdown fences, keep only the document
    body, and re-apply the template preamble; drop risky primitives
    (`\write18`, `\input`, `\include`, `\openout`, `\immediate`, `\catcode`,
    `\newwrite`, `shellesc`).
  - `is_valid_latex(source)` — requires `\documentclass`, `\begin{document}`,
    `\end{document}`, balanced environments/braces and no risky primitives.
- Verify: `python -c` renders a sample `StructuredCV` and prints a document
  containing all three markers; `is_valid_latex` is False for garbage input.

### Phase 2 — Top-tier rewrite prompt + provider call
- Files: `backend/app/services/llm.py`
- Changes:
  - `LATEX_PROMPT`: full, compilable LaTeX with the pinned preamble; one page;
    reverse-chronological; action-verb bullets with metrics *only* where the CV
    supports them; grouped skills; no invented employers/dates/degrees; escape
    special characters; output LaTeX only (no fences, no commentary); no
    images, columns or icons.
  - `rewrite_cv_latex(cv_text, accepted_changes, jd_text, settings, provider,
    model) -> str` — routes through `_chat_completion`; `mock` returns
    `latex.render_document(structure_text(cv_text))`; raises on invalid output
    so the caller can fall back.
- Verify: with `provider=mock`, `rewrite_cv_latex` returns a valid document for
  a sample CV.

### Phase 3 — Model column + endpoint
- Files: `backend/app/models.py`, `backend/app/routers/reviews.py`,
  new Alembic revision
- Changes:
  - `cv_reviews.final_latex` (`Text`, nullable).
  - `finalize_review(review_id, format)` — drop `mode`; validate
    `format in ("docx", "pdf", "tex")` (400 otherwise); build the polished
    structured document exactly as today for docx/pdf; for `tex` generate (or
    reuse persisted) LaTeX, falling back to `latex.render_document(...)` on any
    provider/validation failure; respond with `application/x-tex` and
    `cv_optimized_{id}.tex`.
  - Invalidate `final_latex` alongside `final_document` in
    `update_suggestion`.
  - Remove the now-dead plain-text renderers `to_pdf_bytes` / `to_docx_bytes`
    from `backend/app/services/export.py` (keep `build_final_text`, still used
    by scoring and the cover letter).
- Verify: curl `format=tex`, `docx`, `pdf`, and a bogus format; check the DB
  column after the first tex download and after a suggestion PATCH.

### Phase 4 — UI + docs
- Files: `frontend/src/api.js`, `frontend/src/pages/ReviewPage.jsx`,
  `DOCS.md`, `README.md`, `AGENTS.md`
- Changes: `finalizeReview(id, format)` (no mode); `EXPORT_OPTIONS` reduced to
  the three formats with neutral hints ("editable", "print-ready",
  "top-tier layout"); stale `.docx`/`.pdf` download filename derived from the
  response format; docs updated to the new endpoint contract and the LaTeX
  option; AGENTS.md export convention line updated.
- Verify: browser — Review page → Apply & Download shows three neutral items;
  each downloads a valid file; page source contains no "LLM rewrite" hint.

## Out of scope

- Verifying/shipping a PDF *preview* of the LaTeX output, Overleaf integration,
  or server-side `pdflatex` compilation (no toolchain in this environment).
- Changing the DOCX/PDF structure, the cover letter, scoring, or the merge
  semantics of `build_final_text`.
- Migrating or backfilling existing rows beyond the nullable column.
- Reworking `INITIATIVES.md` / older phase plans (historical records).

## Database impact

One Alembic migration adds `cv_reviews.final_latex` (`Text`, nullable).
No ad-hoc DDL. `alembic_version` stays at head.

## Verification

Executed 2026-11-17 (backend restarted on port 8001 after the code changes;
Vite HMR on 5174 picked up the frontend automatically).

1. **Migration** — `.venv/bin/alembic revision --autogenerate -m "cv_reviews
   final_latex"` produced revision `7ae4d6981221` (down_revision
   `319d33f05a24`); `.venv/bin/alembic upgrade head` applied it. Schema check:
   `cv_reviews` now has `final_latex text` (nullable). `alembic heads` =
   `7ae4d6981221`.
2. **`format=tex`** — `POST /api/reviews/8/finalize?format=tex` →
   `200`, `content-type: application/x-tex`,
   `content-disposition: attachment; filename="cv_optimized_8.tex"`, 6902
   bytes, all three LaTeX markers present.
3. **Reuse** — set `final_latex = 'MARKER-ONLY'` directly in the DB, downloaded
   the `.tex` again: the response body was exactly `MARKER-ONLY`, proving the
   stored source is served without regeneration.
4. **Invalidation** — `PATCH /api/reviews/8/suggestions/46 {"status":
   "REJECTED"}` → `final_latex is null` (SQL NULL) and `GET /api/reviews/8`
   reports `final_document: null`; the pending status was restored afterwards.
5. **Removed modes** — `format=quick` → `400`, `format=bogus` → `400`.
6. **Unchanged formats** — `format=docx` → `200` +
   `application/vnd.openxmlformats-officedocument.wordprocessingml.document`,
   74 paragraphs with `Title`/`Heading 2`/`List Bullet` styles; `format=pdf` →
   `200` + `application/pdf` starting with `%PDF-1.4`.
7. **Mock provider end-to-end** — created review `#22` with
   `llm_provider=mock`; docx/pdf/tex all downloaded successfully with no
   provider call (no new "rewrite failed" log lines) and the `.tex` is pure
   ASCII with 7 `\cvsection` headings. The review and its job description
   were deleted afterwards so the local DB is back to its prior state.
8. **Escaping** — a sample CV containing `& % $ # _ { } ~ ^`, Vietnamese
   diacritics, en/em dashes and a `•` bullet renders to ASCII-only LaTeX with
   `\&`, `\%`, `\$`, `\#`, `\_`, `\textasciitilde{}`, `\textasciicircum{}` and
   `\{`/`\}`; `is_valid_latex` rejects garbage and file-reading primitives
   (`\input`), and `sanitize_latex` strips markdown fences plus prose before
   `\documentclass`.
9. **Real browser (Chrome 157 headless, CDP)** on
   `http://localhost:5174/reviews/22` (and repeated on review `#13` after the
   final backend changes) — "Apply & Download" opened a menu with exactly
   `Word (.docx) editable`, `PDF ready to send`,
   `LaTeX (.tex) top-tier layout`; each item downloaded the expected file
   (`cv_optimized_<id>.docx` / `.pdf` / `.tex`, the tex carrying all three
   markers); the page text contains no "LLM", "quick" or "merge".
10. **Known limitation** — no TeX toolchain is installed here (`pdflatex`,
    `latexmk`, `tectonic` all absent), so the `.tex` file was validated
    structurally (markers, ASCII-only output, escaping of every LaTeX special
    character) rather than compiled. Recorded in DOCS.md → Known limitations.
11. **Real-LLM path** — the first attempts hit transient entitlement errors
    (`403 Forbidden` on `opencode_go`, `402 Payment Required` on `ollama`) and
    correctly fell back to the deterministic template (one
    `LaTeX rewrite failed, using template: ...` log line). A later call on
    review `#13` (`opencode_go` / `deepseek-v4.1-flash`) succeeded end to end:
    5933-byte `.tex`, `is_valid_latex` true, ASCII-only, 7 `\cvsection`
    headings, and the pinned preamble re-applied verbatim even though the model
    had echoed a slightly broken copy of it (`\titlespacing*{section}`) —
    exactly the failure the body-only sanitiser exists to absorb. A
    deliberately unbalanced response (`\begin{itemize}` without `\end{itemize}`)
    is rejected and falls back.

