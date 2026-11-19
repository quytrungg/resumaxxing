# Phase Plan — Cover letter: single download dropdown + generate before finalize

> Required by AGENTS.md rule 1: this plan must exist and be confirmed by the
> user before any implementation code is written.
>
> Amends `docs/phase-plan-4-cover-letter.md`: the 409-until-finalized gate and
> the two separate download buttons are superseded here.

## Goal

Two related fixes to the cover letter panel:

1. Replace the separate **Download Word** and **Download PDF** buttons with one
   **Download ▾** dropdown offering Word and PDF, matching the existing
   "Apply & Download ▾" control on the review header.
2. Let the user generate a cover letter at any time — even when the CV has not
   been applied/finalized — by feeding the generator the latest CV with the
   accepted suggestions applied (`_pending_cv_text`, the same merge path used by
   scoring and finalize). Generation no longer depends on the stored
   `final_document`.

The stored letter is still just text on the review, and downloads still go
through the existing export service.

## Success criteria

- [x] `POST /api/reviews/{id}/cover-letter` returns `{text}` for a review whose
      `status` is `draft` (no 409), including after accepting a suggestion:
      the generated text reflects the accepted suggestion.
- [x] `GET /api/reviews/{id}` on a draft review shows the generated
      `cover_letter`, and `POST /api/reviews/{id}/cover-letter/export?format=docx`
      / `?format=pdf` still return valid files for it.
- [x] Finalizing the CV afterwards still works unchanged (no dependency on the
      letter; regenerate is available).
- [x] The cover letter panel shows exactly one download control: a
      **Download ▾** dropdown with **Word (.docx)** and **PDF** options; each
      option downloads the expected file and closes the dropdown.
- [x] **Generate** is enabled before the CV is finalized; the helper text no
      longer says "Finalize the CV first", and instead states the letter is
      built from the CV with accepted suggestions + this job description.
- [x] Whole flow works end-to-end with the `mock` provider and no API keys.

## Phases

### Phase 1 — Backend: drop the finalize gate
- Files: `backend/app/routers/reviews.py`
- Changes: in `generate_cover_letter`, remove the
  `review.status != ReviewStatus.finalized` → 409 guard. Keep
  `_pending_cv_text(review)` as the CV input (base CV + ACCEPTED suggestions,
  newest edits included) and keep the existing settings/LLM/provider plumbing
  and `review.cover_letter = text` persistence.
- Verify: with uvicorn on 8001, on a review with `status == "draft"`:
  `curl -sS -X POST localhost:8001/api/reviews/<id>/cover-letter` → 200
  `{"text": ...}`; `curl -sS localhost:8001/api/reviews/<id> | jq .cover_letter`
  non-empty; export `?format=docx` and `?format=pdf` → 200 with correct
  content types.

### Phase 2 — Frontend: single Download dropdown + unlocked generate
- Files: `frontend/src/components/CoverLetterPanel.jsx`,
  `frontend/src/pages/ReviewPage.jsx`
- Changes:
  - `CoverLetterPanel`: replace the two export buttons with one
    **Download ▾** dropdown (local `open` state, same markup/closing pattern as
    the existing `EXPORT_OPTIONS` dropdown in `ReviewPage`): Word (.docx) and
    PDF entries, each calling `onExport(fmt)` and closing the menu. Disabled
    when there is no letter or the panel is busy. Remove the `finalized` prop
    from the generate-button disabled state; drop the "Finalize the CV first"
    copy in favour of "Built from your CV with accepted suggestions and this job
    description. Regenerate after changing suggestions."
  - `ReviewPage`: stop passing `finalized` to the panel.
- Verify: in the browser on a draft review — Generate is clickable, dropdown
  shows both options, Word and PDF both download, and re-accepting a suggestion
  then Regenerating picks the change up.

### Phase 3 — Docs
- Files: `DOCS.md` (API table line for `POST /cover-letter`, any limitation
  wording), this plan's Verification section.
- Changes: document that generation uses the CV with accepted suggestions and
  needs no finalize; note the single download dropdown.
- Verify: read-back; `grep -n "409 until finalized" DOCS.md` returns nothing.

## Out of scope

- Changing the finalize/"Apply & Download" control or `final_document`.
- Auto-generating or auto-refreshing the letter when suggestions change
  (explicit Regenerate only) — no staleness tracking.
- New export formats, letterheads, templates, or PDF styling for the letter.
- Any schema or migration change (the letter is already stored as text).
- Backend caching/dedup of letter generation calls.

## Database impact

None. No Alembic migration; `cv_reviews.cover_letter` already exists. No DDL
repair needed.

## Verification

Evidence recorded 2026-11-18. Backend restarted on 8001 (it runs without
`--reload`), vite HMR served 5174.

1. Backend (uvicorn 8001, review 37 = `draft`, provider `mock`, one ACCEPTED
   suggestion "− Docker" on Skills):
   - `curl -X POST localhost:8001/api/reviews/37/cover-letter` → **200** with
     `{"text": "Dear Hiring Manager, …"}` (previously 409). The row now has a
     stored `cover_letter`.
   - Accepted-suggestion wiring proved through the real endpoint in-process
     (`TestClient` + stubbed LLM, transaction rolled back so nothing persisted):
     the CV string handed to `llm.generate_cover_letter` contains `Docker`,
     i.e. the endpoint passes base CV + ACCEPTED suggestions — not
     `final_document`.
   - `POST …/cover-letter/export?format=docx` → 200
     `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
     (`file` = Microsoft OOXML, 37 012 bytes), first paragraph
     "Dear Hiring Manager,".
   - `POST …/cover-letter/export?format=pdf` → 200 `application/pdf` (1 page),
     pdfplumber extracts "Dear Hiring Manager,".
   - Same in-process run then called
     `POST …/finalize?format=docx` → 200, detail afterwards shows
     `status: "finalized"` with the letter still stored, then rolled back — so
     generating first does not block finalize.
2. Frontend (Chromium via Playwright against `localhost:5174/reviews/37`, a
   `draft` review that was never applied/downloaded):
   - `Generate`/`Regenerate` enabled, hint text = "Built from your CV with
     accepted suggestions and this job description. Regenerate after changing
     suggestions."
   - Panel contains exactly **1** `Download` control, **0** legacy
     "Download Word"/"Download PDF" buttons. Opening it lists
     `Word (.docx)` and `PDF`; clicking the button again closes it.
   - Word option → download `cover_letter_37.docx` (37 012 bytes), PDF option →
     `cover_letter_37.pdf` (2 030 bytes); menu closed after each pick.
   - Reload → generated letter still in the textarea.
   - Finalized review 40 renders the same single `Download ▾` control.
   - No console/page errors.
3. Docs: `DOCS.md` line for `POST /cover-letter` now reads "generate from your
   CV with accepted suggestions + JD; no finalize needed";
   `grep -n "409 until finalized" DOCS.md` → no matches.

