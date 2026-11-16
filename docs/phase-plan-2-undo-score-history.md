# Phase Plan — Initiative 2: Undoable decisions & score history

> Implements INITIATIVES.md #2.

## Goal

Make every suggestion decision reversible from the UI (Undo returns the card to
PENDING through the existing PATCH endpoint) and record how the match score
evolved across decisions so the review page can draw a step/sparkline chart.

## Success criteria

- [ ] A decided suggestion card shows an "Undo" action that PATCHes status
      `PENDING`; the card returns to the pending list and the score updates.
- [ ] `score_events` rows are appended at review creation and on every
      status change, in order.
- [ ] `GET /api/reviews/{id}` returns `score_history: [{score, created_at}]`.
- [ ] The review page renders the history as an inline SVG step chart; with a
      single point it renders without error.
- [ ] Existing reviews (no history rows) still load (empty chart state).

## Phases

### Phase 1 — Model + migration
- Files: `backend/app/models.py`, Alembic revision
- Changes: `ScoreEvent` (`id`, `cv_review_id` FK cascade, `score`, `reason`,
  `created_at`) and `CVReview.score_events` relationship; index on
  `cv_review_id`.
- Verify: `alembic upgrade head`; `\d score_events` shows the table.

### Phase 2 — Write history + expose it
- Files: `backend/app/routers/reviews.py`, `backend/app/schemas.py`
- Changes: append event on review creation ("initial"), on decision
  ("ACCEPTED/REJECTED/undo <type> <target_section>"); `ScoreHistoryOut`; include
  `score_history` in `_serialize`; PATCH returns the new history entry.
- Verify: curl PATCH accept → then undo; `select score,reason from score_events`
  shows three rows.

### Phase 3 — UI
- Files: `frontend/src/components/SuggestionCard.jsx`,
  `frontend/src/components/ScoreHistory.jsx` (new),
  `frontend/src/pages/ReviewPage.jsx`, `frontend/src/api.js`
- Changes: Undo button on decided cards (re-enables while rescoring); fetch
  history after each PATCH; SVG step chart under the gauge.
- Verify: browser accept → undo → chart gains points and gauge moves back.

## Out of scope

- Arbitrary decision replay/branching, history pruning, analytics across
  reviews, or changes to the PATCH contract (status field stays the same).
- Backfilling synthetic history for pre-existing reviews.

## Database impact

Alembic migration: create `score_events`. Backfill: none (existing reviews keep
an empty history and the UI handles it).

## Verification

1. `curl -X PATCH .../{sid} -d '{"status":"ACCEPTED"}'` → score + history entry.
2. `curl -X PATCH .../{sid} -d '{"status":"PENDING"}'` → score restored, new
   event appended.
3. `psql resumaxxing -c "select * from score_events order by id"`.
4. Browser: decide/undo both directions, chart and gauge agree.
