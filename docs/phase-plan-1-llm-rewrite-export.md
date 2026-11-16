# Phase Plan — Initiative 1: LLM final rewrite & polished export

> Implements INITIATIVES.md #1. The user's instruction to implement all
> initiatives counts as confirmation of this plan (AGENTS.md rule 1).

## Goal

Replace the string-replace-only finalize with an LLM rewrite step that turns
the base CV plus accepted suggestions into a cohesive, structured document
(name/headline/contact + sections of bullets), then render it as a styled DOCX
and a layout-correct PDF with no truncation. The existing merge-only path stays
available as "quick export".

## Success criteria

- [ ] `POST /api/reviews/{id}/finalize?format=docx&mode=polished` returns a
      valid DOCX whose paragraphs include real heading styles and bullet lists.
- [ ] `POST /api/reviews/{id}/finalize?format=pdf&mode=polished` returns a PDF
      where no line is cut off at 110 characters (long bullet wraps).
- [ ] `mode=quick` still returns the merged-text document (pre-feature behavior)
      for both formats.
- [ ] The structured document is persisted on `cv_reviews.final_document` and
      reused on a repeat download without a second LLM call.
- [ ] With provider `mock` (no keys) the whole flow works via the deterministic
      structure fallback.

## Phases

### Phase 1 — Structured document model + deterministic structurer
- Files: `backend/app/services/document.py` (new), `backend/app/schemas.py`
- Changes: `StructuredCV` pydantic model (`name`, `headline`, `contact`,
  `sections[{heading, bullets}]`); `structure_text(cv_text)` heuristic that
  detects headings (known section names / ALL-CAPS short lines) and turns lines
  into bullets; `document_to_plain_text(doc)`.
- Verify: `python -c` on a sample CV prints sections.

### Phase 2 — LLM rewrite call
- Files: `backend/app/services/llm.py`
- Changes: `REWRITE_PROMPT` demanding the structured JSON; `rewrite_cv(...)`
  routing to Claude/Ollama/Opencode; `mock` returns `structure_text` of the
  merged CV. Any provider/parse failure raises, caller falls back.
- Verify: mock provider returns a valid `StructuredCV` for a sample CV.

### Phase 3 — Rendering
- Files: `backend/app/services/export.py`
- Changes: `to_docx_bytes_structured(doc)` (Title/Heading 2/List Bullet styles),
  `to_pdf_bytes_structured(doc)` via reportlab platypus (wrapping paragraphs,
  page breaks, margins). Rework `to_pdf_bytes(text)` to wrap instead of
  `line[:110]` truncation. Plain DOCX path unchanged in behavior.
- Verify: generated PDF extracted with pdfplumber shows the full long line.

### Phase 4 — Finalize endpoint + persistence
- Files: `backend/app/routers/reviews.py`, `backend/app/models.py`,
  `backend/app/schemas.py`, Alembic revision
- Changes: `mode` query param (`polished|quick`, default `polished`);
  polished persists `final_document` JSON and reuses it if already present;
  `ReviewOut.final_document`.
- Verify: curl both modes/formats; `\d cv_reviews` shows `final_document`.

### Phase 5 — UI
- Files: `frontend/src/pages/ReviewPage.jsx`, `frontend/src/api.js`
- Changes: export menu splits into "Polished CV" / "Quick merge" groups ×
  DOCX/PDF.
- Verify: browser click downloads a file; backend log shows one LLM call.

## Out of scope

- Changing the LLM models/endpoints already configured (Phase-3 work).
- Editable diff of the rewritten CV, templates/themes, cover letter (separate
  plan), or re-ordering sections by hand.
- Reworking `build_final_text` merge semantics.

## Database impact

One Alembic migration adds `cv_reviews.final_document` (JSON, nullable).
No ad-hoc DDL.

## Verification

1. `curl -X POST 'localhost:8001/api/reviews/2/finalize?format=docx&mode=polished' -o /tmp/cv.docx`
2. `python -c "from docx import Document; print([p.style.name for p in Document('/tmp/cv.docx').paragraphs])"`
3. Same with `format=pdf`, extract text with pdfplumber and assert a >110-char
   bullet is present in full.
4. Repeat finalize → no second rewrite (same stored doc).
5. Browser: Review page → Apply & Download → Polished Word; file downloads.
