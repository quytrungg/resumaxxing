# Phase Plan — Manual re-evaluation instead of scoring on every decision

> Required by AGENTS.md rule 1: this plan must exist and be confirmed by the
> user before any implementation code is written.

## Goal

Accepting or rejecting a suggestion currently calls the LLM synchronously
(`llm.llm_score`) to produce a new score on every click. That is slow and burns
tokens for a decision that may be one of many. Change the flow so:

1. A decision is purely local and instant — only the suggestion's status changes.
   The CV score, ATS keyword coverage and history all stay untouched until the
   user asks for a re-evaluation.
2. A new **Re-evaluate** button (retry icon) next to **Show Job Description**
   re-scores the CV from the current accepted/rejected/pending set in a single
   LLM call, refreshes the keyword panel and appends one score-history entry.

The final document is still invalidated on a decision (its accepted set changed)
as today; re-evaluation does not touch it because it does not change inputs.

## Success criteria

- [ ] `PATCH /api/reviews/{id}/suggestions/{sid}` no longer calls the LLM, writes
      no `score_events` row, leaves `cv_reviews.current_score` unchanged and does
      not compute keyword coverage. With the review pinned to `claude` but no key
      saved, the PATCH still returns 200 (proving no provider call), while
      `POST …/rescore` returns 502.
- [ ] The PATCH response carries only the new suggestion `status`; score,
      coverage and history are untouched. (Coverage stays derived at read time
      in `_serialize`, so a later GET or page reload reflects the new statuses —
      existing behaviour, not computed by the decision request.)
- [ ] Clicking Accept/Reject/Undo in the UI flips the card immediately and does
      **not** move the gauge, change the ATS keyword chips, change the score
      history, or show `rescoring…`.
- [ ] `POST /api/reviews/{id}/rescore` recomputes coverage and calls
      `llm.llm_score` once with the pending text (accepted applied, rejected and
      pending ignored), sets `current_score`, appends exactly one `ScoreEvent`
      with reason `re-evaluated (A accepted, R rejected, P pending)`, and
      returns `ScoreOut`.
- [ ] The **Re-evaluate** button sits left of **Show Job Description**, renders a
      monochrome retry icon + text, is disabled while the request is in flight,
      shows `Re-evaluating…`, and on success updates the gauge, keyword panel and
      score history from the response.
- [ ] A provider failure on re-evaluate surfaces the existing red error line and
      leaves the previous score/history intact.
- [ ] `GET /api/reviews/{id}` after re-evaluate reflects the new score and history
      after a reload.
- [ ] `npm run build` passes; the mock provider still works end-to-end with no
      keys.

## Phases

### Phase 1 — Backend: decision becomes local
- Files: `backend/app/schemas.py`, `backend/app/routers/reviews.py`
- Changes:
  - Add `SuggestionStatusOut { status }`.
  - `update_suggestion` drops the `llm.llm_score` call, the `ScoreEvent` insert,
    the score update and the `keywords.coverage(...)` recomputation; it keeps
    `suggestion.status` and the `final_document = None` invalidation, and returns
    the new schema.
- Verify: curl PATCH on a mock review → 200 with only `status`; `current_score`,
  `score_events` count and the review's keyword coverage are all unchanged.

### Phase 2 — Backend: explicit re-evaluate endpoint
- Files: `backend/app/routers/reviews.py`
- Changes: `POST /api/reviews/{review_id}/rescore` → compute `pending_text`,
  coverage and `new_score` via `llm.llm_score` (pinned provider/model), update
  `current_score`, insert one `ScoreEvent` with the counts-based reason, commit,
  return `ScoreOut` (score + coverage + history entry); provider exceptions
  become 502 `LLM request failed: …`.
- Verify: curl rescore → 200 with refreshed coverage and a new `history_entry`;
  a review pinned to a keyless provider → 502 and no score change.

### Phase 3 — Frontend: instant decisions
- Files: `frontend/src/api.js`, `frontend/src/pages/ReviewPage.jsx`
- Changes:
  - `setSuggestionStatus` unchanged in transport; `handleDecide` applies only the
    returned `status` to the matching suggestion — no score, coverage or
    history update, no `scoring` indicator.
  - Add `rescoreReview(id)` calling `POST /reviews/{id}/rescore`.
- Verify: browser — Accept/Reject updates the cards instantly; gauge, keyword
  chips and chart do not move.

### Phase 4 — Frontend: Re-evaluate control
- Files: `frontend/src/pages/ReviewPage.jsx`,
  `frontend/src/components/ScoreHistory.jsx`
- Changes:
  - `rescoring` state + `handleRescore`: call `rescoreReview`, then apply
    `score`, coverage and `history_entry` the way `handleDecide` used to.
  - Button left of **Show Job Description**: monochrome circular-arrow SVG
    (`currentColor`), `Re-evaluate` / `Re-evaluating…`, bordered style matching
    the adjacent button, disabled while in flight, `title`/`aria-label`
    explaining it re-scores the current choices.
  - Score-history empty state copy → "re-evaluate to start the chart".
- Verify: browser — decide a few suggestions, press Re-evaluate → gauge, ATS
  panel and chart update once; history shows one new step.

### Phase 5 — Docs
- Files: `DOCS.md`, `AGENTS.md`
- Changes: API table (PATCH no longer scores; new POST `/rescore`) and the
  AGENTS "All suggestion status changes … re-scores synchronously" convention.
- Verify: read-back.

## Out of scope

- Batch/auto scoring, debounce, or scoring after N decisions.
- Changing the scoring prompt, `heuristic_score`, or how `_pending_cv_text`
  applies accepted/rejected suggestions.
- Persisting a "score is stale" flag or disabling export when stale; the gauge
  simply keeps the last computed score until the user re-evaluates.
- The cover-letter endpoint, finalize flow, and the LLM provider settings.
- Per-suggestion score deltas or a score-preview.

## Database impact

None. No schema change; the only data change is that `score_events` now gets a
row on review creation and on explicit re-evaluation, not on every decision.
Existing history rows are untouched.

## Verification

1. Create a throwaway review with `mock`; record `current_score`, the
   `score_events` count and `GET /api/reviews/{id}`.
2. `PATCH` one suggestion to `ACCEPTED` → 200 with only the new status; assert
   `current_score` and the `score_events` count are unchanged. A subsequent GET
   reflects the new statuses in coverage (derived, no LLM).
3. Point that throwaway review's `llm_provider` at `claude` (no key) via SQL;
   `PATCH` another suggestion → 200 instantly; `POST …/rescore` → 502
   `LLM request failed` and the score is unchanged. Restore/remove the row.
4. With `mock` again, `POST …/rescore` → 200, score and keyword coverage
   recomputed from the accepted set, exactly one new `score_events` row whose
   reason is `re-evaluated (A accepted, R rejected, P pending)`.
5. Browser at :5174: Accept two suggestions → cards change instantly, key
   chips/gauge/chart do not move, no `rescoring…`; press **Re-evaluate** → gauge,
   chips and chart update once; history shows the new step.
6. Reload the page → `GET /api/reviews/{id}` returns the same score/history.
7. Delete the throwaway review and its rows.
8. `cd frontend && npm run build` passes.
