# Phase Plan — Initiative 4: Cover letter generation

> Implements INITIATIVES.md #4.

## Goal

Generate a tailored cover letter from the already-stored tailored CV, job
description, and optional LinkedIn URL; let the user edit it inline; persist the
text on the review; and download it as DOCX or PDF through the export service.

## Success criteria

- [ ] `POST /api/reviews/{id}/cover-letter` returns `{text}` for provider
      `mock` and for configured providers, and stores it on
      `cv_reviews.cover_letter`.
- [ ] `PUT /api/reviews/{id}/cover-letter` saves edits.
- [ ] `POST /api/reviews/{id}/cover-letter/export?format=docx|pdf` returns a
      valid file containing the saved letter.
- [ ] The UI button is disabled until the review is finalized; after
      generation an inline editor with Save and DOCX/PDF buttons appears.
- [ ] `mock` output is a template letter that slots in JD keywords and the CV's
      first line; it never needs an API key.

## Phases

### Phase 1 — Model + migration
- Files: `backend/app/models.py`, Alembic revision
- Changes: `CVReview.cover_letter` (Text, nullable).
- Verify: `\d cv_reviews`.

### Phase 2 — LLM + export service
- Files: `backend/app/services/llm.py`, `backend/app/services/export.py`
- Changes: `COVER_LETTER_PROMPT`, `generate_cover_letter(cv_text, jd_text,
  linkedin_url, settings)`; mock template using keywords + candidate name;
  `letter_to_docx_bytes(text)` / `letter_to_pdf_bytes(text)` (paragraph per
  blank-line-separated block).
- Verify: `python -c` on mock output; open generated files.

### Phase 3 — Endpoints + schemas
- Files: `backend/app/routers/reviews.py`, `backend/app/schemas.py`
- Changes: `CoverLetterOut`, `CoverLetterUpdate`; three endpoints above; 409
  when the review is not finalized; input CV is the pending (accepted-changes)
  text.
- Verify: curl generate/save/export before and after finalize.

### Phase 4 — UI
- Files: `frontend/src/pages/ReviewPage.jsx`, `frontend/src/api.js`
- Changes: "Cover letter" card with Generate / Save / Download DOCX / Download
  PDF, textarea bound to state, disabled-until-finalized hint.
- Verify: browser generate → edit → save → reload page → text persists.

## Out of scope

- PDF letterheads, signature images, multiple letter variants/templates.
- Auto-generating on finalize (explicit user action only).
- Changes to how the tailored CV itself is produced.

## Database impact

Alembic migration: add `cv_reviews.cover_letter` (Text, nullable). No backfill.

## Verification

1. `curl -X POST localhost:8001/api/reviews/2/cover-letter`.
2. `curl -X PUT ... -d '{"text":"..."}'` then `GET /api/reviews/2` shows it.
3. `curl -X POST '.../cover-letter/export?format=pdf' -o /tmp/letter.pdf` and
   extract text to confirm content.
4. Browser round-trip generate/edit/save/download.
