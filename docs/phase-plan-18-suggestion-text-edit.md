# Phase Plan — Edit a suggestion's suggested text before accepting

> Required by AGENTS.md rule 1: this plan must exist and be confirmed by the
> user before any implementation code is written.

## Goal

Today a suggestion is all-or-nothing: the user either accepts the LLM's exact
wording or rejects it. Add an inline editor so the user can adjust the suggested
text of an **ADD** or **UPDATE** suggestion (the "added lines"), save it, and
then accept the adjusted version. The edit is persisted on the suggestion, so
every downstream path that already reads `suggested_text` — `build_final_text`,
scoring, the cover-letter input, and all three exports — uses the user's wording
with no extra plumbing.

Decisions confirmed with the user:

- Editable types: **ADD and UPDATE**. REMOVE has no replacement text → stays
  read-only.
- Affordance: **one pencil on the right of the suggested block** (a per-diff-line
  pencil does not map onto `react-diff-viewer`'s word-level diff).
- The AI wording is **kept for reset**: new nullable `original_suggested_text`
  column, set on the first edit, with a "Reset to AI text" action.
- **Save text only**: saving never changes `status`; the user still clicks
  Accept. Accepted suggestions keep `ACCEPTED` when their text is edited.

## Success criteria

- [ ] `PUT /api/reviews/{id}/suggestions/{sid}/text` with `{"suggested_text":"…"}`
      returns 200 and the full suggestion; the stored `suggested_text` is the new
      text and `original_suggested_text` holds the pre-edit AI text.
- [ ] A second edit overwrites `suggested_text` but leaves `original_suggested_text`
      at the *first* AI text (never re-captures an edited value).
- [ ] `DELETE /api/reviews/{id}/suggestions/{sid}/text` restores
      `suggested_text` from `original_suggested_text` and clears the column
      (200); a reset with nothing to restore returns 400.
- [ ] Both endpoints return 404 for a suggestion that belongs to another review.
- [ ] A REMOVE suggestion → 400 (no replacement text); blank/whitespace-only text
      → 422 (pydantic validation); a wrong-review suggestion id → 404.
- [ ] Editing clears `final_document` and `final_latex` (stored downloads are
      stale) but does **not** call the LLM, change `current_score`, or write a
      `score_events` row — matching the existing PATCH/Re-evaluate split.
- [ ] Accepting an edited UPDATE suggestion makes `build_final_text` contain the
      edited text (not the AI text), and an edited accepted ADD suggestion's
      appended line is the edited text.
- [ ] ADD and UPDATE cards show a pencil icon on the right edge of the suggested
      block; clicking it turns that block into a textarea pre-filled with the
      current text, with **Save** and **Cancel**; `Cmd/Ctrl+Enter` saves and
      `Esc` cancels.
- [ ] Save is disabled while the text is unchanged or blank, and while the
      request is in flight; the card shows the saved text and the diff re-renders
      against it without a page reload.
- [ ] A card whose suggestion has `original_suggested_text` shows **Reset to AI
      text** in the editor; the textarea and diff return to the AI wording.
- [ ] REMOVE cards show no pencil. The pencil lives in the card body, so a
      decided (ACCEPTED/REJECTED) card stays editable and editing it leaves its
      status untouched.
- [ ] `npm run build` passes; the app still works end-to-end with the `mock`
      provider and no API keys.

## Phases

### Phase 1 — Backend: persist the AI wording
- Files: `backend/app/models.py`, `backend/alembic/versions/<new>.py`
- Changes: add `Suggestion.original_suggested_text = Column(Text, nullable=True)`
  (documented as "first AI text, set on first user edit"). Generate the revision
  with `alembic revision --autogenerate -m "suggestion original suggested text"`
  and `alembic upgrade head`.
- Verify: `alembic current` = head; `\d suggestions` shows the new nullable Text
  column; existing rows unchanged.

### Phase 2 — Backend: endpoints + schema
- Files: `backend/app/schemas.py`, `backend/app/routers/reviews.py`
- Changes:
  - `SuggestionOut` gains `original_suggested_text: Optional[str]`.
  - `SuggestionTextUpdate { suggested_text: str }` — validator strips the value
    and rejects an empty result (or the router raises 400).
  - `PUT /{review_id}/suggestions/{suggestion_id}/text`: load review + suggestion
    (404s as today), reject `type == REMOVE` and REMOVE-with-status flows with
    400 `"This suggestion type has no replacement text"`, capture
    `original_suggested_text` only when it is null, assign the new text, clear
    `final_document` / `final_latex`, commit, return `SuggestionOut`.
  - `DELETE /{review_id}/suggestions/{suggestion_id}/text`: 400 when
    `original_suggested_text` is null; otherwise restore and clear it, invalidate
    the stored outputs, return `SuggestionOut`.
- Verify: curl the four cases in the success criteria against a `mock` review;
  `GET` the review and confirm the values; re-run `POST /finalize` and prove the
  edited accepted text lands in the export (inspect `final_document` bullets or
  the merged text via `services/export.build_final_text`).

### Phase 3 — Frontend: editor on the card
- Files: `frontend/src/api.js`, `frontend/src/components/SuggestionCard.jsx`
- Changes:
  - `api.js`: `updateSuggestionText(reviewId, suggestionId, text)` (PUT) and
    `resetSuggestionText(reviewId, suggestionId)` (DELETE), both returning JSON.
  - `SuggestionCard`: local `editing`, `draft`, `saving` state; a monochrome
    pencil SVG button (`currentColor`, `title`/`aria-label`
    "Edit suggestion"), absolutely positioned in the suggested block's top-right
    for ADD and UPDATE only. In edit mode the block renders a `textarea`
    (same font/padding language as the current `<pre>`), plus a footer row with
    **Save**, **Cancel**, and **Reset to AI text** when
    `suggestion.original_suggested_text` exists. New props: `onSaveText`,
    `onResetText`.
  - Keep the not-editing rendering exactly as today (diff for UPDATE, `<pre>`
    for ADD/REMOVE) so the change is additive.
- Verify: browser — pencil appears on ADD/UPDATE only, edit/save updates the
  card, Cancel discards, Esc/Cmd+Enter work.

### Phase 4 — Frontend: wiring and refresh
- Files: `frontend/src/pages/ReviewPage.jsx`
- Changes: `handleSaveText` / `handleResetText` call the api helpers, patch the
  returned suggestion into `review.suggestions`, then quietly re-`getReview(id)`
  (as `handleDecide` does) so ATS coverage/chips stay truthful for accepted
  suggestions. Errors go to the existing red error line; no status change.
- Verify: browser — save an edit on a pending card, accept it, press
  Re-evaluate; coverage/chips reflect the edited wording. Reload keeps the edit.

### Phase 5 — Docs
- Files: `DOCS.md`, `AGENTS.md`
- Changes: API table rows for the two new endpoints, the `suggestions` column
  list (add `original_suggested_text`), and an AGENTS convention note that the
  suggested text is user-editable, the AI original is preserved for reset, and an
  edit invalidates the stored downloads without re-scoring.
- Verify: read-back.

## Out of scope

- Per-diff-line editing or editing `original_text` (the "before" side).
- Changing `target_section`, `reasoning`, or the suggestion `type`.
- Editing REMOVE suggestions.
- Auto-rescoring or auto-accepting after a save (Re-evaluate stays explicit per
  phase plan 12).
- LLM "regenerate this suggestion" or an undo history of multiple edits.
- Any prompt/tolerance change in `services/llm.py`.

## Database impact

One Alembic migration: nullable `suggestions.original_suggested_text TEXT`.
No data backfill; existing rows keep `NULL` (never-edited). No ad-hoc DDL.

## Verification

Evidence recorded on 2026-11-18. Backend restarted on :8001 with the new code
(`.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001`, log in the session
temp dir); Alembic head is `9e44b4ed5fa0`. All API checks ran against throwaway
`mock` reviews that were deleted afterwards (`cv_reviews`, `suggestions`,
`score_events`, `job_descriptions`); review 41 was only read.

**Migration.** `alembic upgrade head` → `45af988a6a0d -> 9e44b4ed5fa0`;
`alembic current` reports `9e44b4ed5fa0 (head)`; the column is nullable Text.

**API (`verify_18.py`, 26 assertions, all PASS).**
- `PUT …/suggestions/{sid}/text` → 200; `"  Rewritten by hand  "` stored as
  `"Rewritten by hand"`; `original_suggested_text` = the pre-edit AI text;
  status stayed `PENDING`.
- A second PUT stored the new text and kept the **first** AI text.
- `DELETE …/text` → 200 restored the AI text and cleared
  `original_suggested_text`; a second DELETE → 400 "This suggestion has no
  edited text to reset".
- Negatives: blank text → 422 (pydantic), missing body → 422, unknown
  suggestion → 404, suggestion from another review → 404, REMOVE → 400 "This
  suggestion type has no replacement text to edit".
- Accepting the edited ADD then `POST /finalize?format=docx` produced a DOCX
  whose stored `final_document` bullets contain the hand-written line
  `Python and FastAPI at scale (hand-written)` and **not** the AI wording.
- A later edit cleared `final_document` and `final_latex`, left
  `current_score` and the `score_events` count unchanged.
- With the review pinned to keyless `claude`, the PUT still returned 200 while
  `POST …/rescore` returned 502 — proving the edit makes no provider call.

**Browser (system Chrome via `playwright-core`, throwaway review #45–#47, all
PASS, no console errors).**
- One pencil per ADD/UPDATE card (`pencils=7 editable=7`); ADD cards show it in
  the right-hand gutters of the text block.
- Editor pre-filled with the current text; **Save** disabled while unchanged and
  enabled after a change; Save PUT → 200, card re-renders the new text and shows
  `· edited`; server kept the AI original.
- Reload keeps the edit. **Reset to AI text** → DELETE 200, text and diff revert,
  `· edited` gone, `original_suggested_text` null.
- `Esc` discards a draft without a request; `⌘+Enter` saves.
- Accept → edit an accepted card → 200 and the status stays `ACCEPTED`; the
  keyword panel refreshes (quiet re-fetch) and the edit survives a reload.
- UPDATE card: the pencil sits in a reserved right gutter (`pr-10` wrapper), so it
  no longer overlaps diff text (checked in `5-update-card.png`).

**Build.** `npm run build` → `✓ 142 modules transformed`, built in 1.18s.

**Data left behind.** None: reviews 42–47 and their suggestions, score events and
job descriptions were deleted; `cv_reviews` newest ids are 41 and 40.

