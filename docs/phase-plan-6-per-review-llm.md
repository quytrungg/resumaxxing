# Phase Plan — Per-review LLM provider & model selection

> Requested by the user: choose the LLM used to review a CV when creating a
> review. Implements INITIATIVES-style behavior on top of the existing provider
> router. Plan written before code per AGENTS.md rule 1.

## Goal

Let the "New CV Review" modal choose which LLM provider (and optionally which
model name) reviews that CV. The choice is pinned on the review row and used for
every later LLM call for that review — initial review, rescoring on each
decision, the polished finalize rewrite, and the cover letter — instead of
always following the global Settings provider.

## Success criteria

- [ ] `POST /api/reviews` accepts optional `llm_provider` (`mock|claude|ollama|opencode`)
      and optional `llm_model`; an unknown provider returns 400.
- [ ] The effective provider/model is stored on `cv_reviews.llm_provider` /
      `llm_model` and returned by every review response.
- [ ] `PATCH .../suggestions/{id}`, `POST .../finalize` (polished) and
      `POST .../cover-letter` use the review's pinned provider/model, falling
      back to Settings when the columns are null (pre-existing reviews).
- [ ] A custom `llm_model` string is passed through to the provider instead of
      the built-in default.
- [ ] The modal offers "Default (saved setting)" plus the four providers and, for
      real providers, a model field pre-hinted with the provider default; with
      `mock` the model field is hidden.
- [ ] A provider failure during review creation returns 502 with a readable
      message instead of an unhandled 500.
- [ ] The review page shows the provider/model that produced the review.

## Phases

### Phase 1 — Data model + migration
- Files: `backend/app/models.py`, Alembic revision
- Changes: `CVReview.llm_provider` (String 50, nullable), `CVReview.llm_model`
  (String 100, nullable).
- Verify: `alembic upgrade head`; `\d cv_reviews`.

### Phase 2 — LLM router accepts an override
- Files: `backend/app/services/llm.py`
- Changes: `DEFAULT_MODELS` map; `_chat_completion(..., model=None)`; thread
  `provider`/`model` overrides through `llm_review`, `llm_score`, `rewrite_cv`,
  `generate_cover_letter` (None = saved setting / provider default).
- Verify: mock review via override; `python -c` that `_chat_completion` payload
  uses the passed model (monkeypatched httpx call).

### Phase 3 — API
- Files: `backend/app/schemas.py`, `backend/app/routers/reviews.py`
- Changes: `ReviewCreate` + `ReviewOut` fields; validate provider; pin effective
  choice at creation; pass the review's choice to all later LLM calls; map
  generation failures to 502.
- Verify: curl with `llm_provider: mock`, with an invalid provider, and with
  `llm_provider: claude` + no key (expect 502, review not created).

### Phase 4 — UI
- Files: `frontend/src/components/NewReviewModal.jsx`,
  `frontend/src/pages/ReviewPage.jsx`
- Changes: "3. LLM" section (provider select defaulting to the saved setting,
  model input for real providers); review header badge showing provider/model.
- Verify: browser create a review with mock → page shows `mock`; create with
  invalid/custom selection behavior visible; existing reviews still load.

## Out of scope

- Per-suggestion model choice, streaming, temperature/token controls.
- Changing the Settings page default provider behavior.
- Listing live models from each provider's API (the model field is free text
  with a default hint).
- Re-running an existing review with a different model (create a new review).

## Database impact

Alembic migration: two nullable columns on `cv_reviews`. Existing rows keep
working via fallback to `user_settings`.

## Verification

1. `curl -X POST /api/reviews -d '{"jd_text":"...","llm_provider":"mock"}'` → 200,
   response `llm_provider: "mock"`, DB row pinned.
2. `curl ... -d '{"jd_text":"...","llm_provider":"bogus"}'` → 400.
3. `curl ... -d '{"jd_text":"...","llm_provider":"claude"}'` (no key) → 502 with
   detail, no review row created.
4. PATCH/finalize/cover-letter on a mock review still work (provider from row).
5. Browser: modal select + model field, created review header shows the choice.
