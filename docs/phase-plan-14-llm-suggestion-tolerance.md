# Phase Plan — Tolerate malformed LLM suggestion items

## Goal

A single malformed suggestion object from the LLM must not destroy an entire
review. Today `POST /api/reviews` fails with
`LLM request failed: 1 validation error for LLMSuggestion suggested_text Field
required` whenever the model omits `suggested_text` — which it does
intermittently for `REMOVE` items, where there is no new text to suggest.
The fix makes `suggested_text` optional for the LLM payload, normalises
`null`/missing to `""`, validates suggestions one by one so only the
malformed item is dropped (and logged), and tells the model in the prompt
what a `REMOVE` item actually needs.

## Success criteria

- [x] `LLMSuggestion(type="REMOVE", target_section="Skills",
      original_text="basic JS and React.", reasoning="…")` validates with
      `suggested_text == ""`.
- [x] `LLMSuggestion(... suggested_text=None)` coerces to `""` instead of
      raising.
- [x] A batch containing one malformed item (missing `suggested_text`,
      lowercase `type`, non-dict entry) keeps the valid items and logs the
      rejected ones; the request succeeds.
- [x] A batch where **no** item survives raises a readable `ValueError`
      (surfaced as a 502 with a short message, not a Pydantic dump).
- [x] `POST /api/reviews` with the `mock` provider still returns 200 with the
      usual heuristic suggestions (no regression).
- [x] `POST /api/reviews` against `opencode_go` / `deepseek-v4.1-flash`
      returns 200 and any `REMOVE` suggestion is stored with
      `suggested_text = ''`.
- [x] `suggestions.suggested_text` stays `NOT NULL` in Postgres; no migration.

## Phases

### Phase 1 — Schema tolerance
- Files: `backend/app/schemas.py`
- Changes: `LLMSuggestion.suggested_text` defaults to `""`; add
  `field_validator`/`BeforeValidator` so `None` becomes `""` and `type` is
  upper-cased (e.g. `"remove"` → `"REMOVE"`). `SuggestionOut.suggested_text`
  keeps `str` (DB column is `nullable=False`).
- Verify: python one-liner asserting the three validation cases above.

### Phase 2 — Per-item parsing in the LLM router
- Files: `backend/app/services/llm.py`
- Changes: replace the list comprehension with `_parse_suggestions(items)`:
  guard against non-list/non-dict entries, validate each item independently,
  log a warning `llm suggestion rejected: <reason>` per rejected item, keep
  the rest, and raise `ValueError("LLM returned no usable suggestions")` when
  nothing survives. Add module logger.
- Verify: monkeypatched `_chat_completion` returning a mixed batch; assert
  kept/dropped counts and that the bad batch raises the new error.

### Phase 3 — Prompt clarification
- Files: `backend/app/services/llm.py` (`SUGGESTION_PROMPT`)
- Changes: require `suggested_text` for `ADD`/`UPDATE`; for `REMOVE` require
  `original_text` + `reasoning` and allow `suggested_text` to be `""`; state
  that `type` is one of exactly `ADD`/`REMOVE`/`UPDATE`.
- Verify: prompt string differs and the end-to-end deepseek review in the
  Verification section returns a parseable batch.

## Out of scope

- Retrying the LLM call automatically (extra provider spend, separate concern).
- Increasing provider `temperature` control or model pinning.
- A `DELETE /api/reviews` endpoint, or any change to how the frontend renders
  `REMOVE` rows (`SuggestionCard.jsx` already shows `original_text`).
- Reworking `_extract_json`'s greedy regex or `LLMReviewResponse` (unused).
- Any UI copy change for 502 errors.

## Database impact

None. `suggestions.suggested_text` is already `NOT NULL` and accepts `''`.
No Alembic revision needed; `alembic_version` stays at head.

## Verification

Evidence recorded as each phase completes:

1. Python validation matrix (Phases 1–3) — all cases pass:
   ```
   missing suggested_text   -> type=REMOVE suggested_text=''
   null suggested_text      -> type=REMOVE suggested_text=''
   lowercase type           -> type=REMOVE suggested_text=''
   normal UPDATE            -> type=UPDATE suggested_text='new'
   mixed batch kept: [('REMOVE', ''), ('REMOVE', ''), ('ADD', '- Kafka')]
     (dropped: enum value 'MOVE', non-dict 'not-a-dict' — each logged as
      "dropping malformed LLM suggestion <i>: ...")
   [] / ['junk'] -> ValueError: LLM returned no usable suggestions
   'nope' / None -> ValueError: LLM response did not contain a suggestions array
   mock provider -> score 33 with heuristic ADD/UPDATE suggestions
   ```
2. `curl POST /api/reviews` with `llm_provider: "mock"` (temporary server on
   port 8002, same code, live DB): **HTTP 200**, review 19, score 40,
   3 ADD + 1 UPDATE — no regression.
3. Live `curl POST /api/reviews` pinned to `opencode_go` /
   `deepseek-v4.1-flash` with review 13's 13,876-char JD: **HTTP 200**,
   review 20, score 58, 15 UPDATE + 3 ADD (that particular sample contained no
   REMOVE item).
4. Exact original payload driven through the real HTTP route
   (`TestClient`, `llm._chat_completion` stubbed with the failing JSON — a
   REMOVE object with no `suggested_text`): **HTTP 200**, review 21,
   score 71, suggestions `[('UPDATE', 'Backend Engineer | Ruby on Rails'),
   ('REMOVE', '')]` — DB rows: `suggestions.id=126 UPDATE len 32`,
   `id=127 REMOVE len 0, original_text 'basic JS and React.'`. This is the
   request that used to return `502 LLM request failed: 1 validation error ...
   suggested_text Field required`.
5. Garbage batch (bad enum + non-dict string) through the same route:
   **HTTP 502** with `{"detail": "LLM request failed: LLM returned no usable
   suggestions"}` — readable, no Pydantic dump, nothing persisted.
6. Cleanup: test reviews 19–21, their suggestions (24 rows), score_events (3)
   and job_descriptions (3) deleted afterwards; DB back to the pre-existing
   9 reviews / 9 job descriptions. Sequences keep their gaps by design.
7. Frontend: no change. `SuggestionCard.jsx:72` already renders
   `original_text` for REMOVE rows, and review 13 (`suggestions.id=79`) is the
   existing proof that an empty `suggested_text` REMOVE renders correctly.

Note: the long-running uvicorn on port 8001 was started without `--reload`, so
it keeps serving the old code until it is restarted.
