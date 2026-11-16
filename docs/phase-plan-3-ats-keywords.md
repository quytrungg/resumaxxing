# Phase Plan — Initiative 3: ATS keyword coverage panel

> Implements INITIATIVES.md #3.

## Goal

Turn the keyword matcher hidden inside `services/llm.py` into a deterministic,
provider-independent service that reports which JD keywords the current CV
covers and which are missing, with a coverage percentage. Recompute it on every
decision and display matched/missing chips plus coverage on the review page.

## Success criteria

- [ ] `app/services/keywords.py` exposes `coverage(cv_text, jd_text)` returning
      `{matched, missing, coverage}` with `coverage` = int 0-100 and stable
      ordering (JD frequency, descending).
- [ ] `llm.heuristic_score` / `heuristic_suggestions` consume the new service
      (no duplicated STOPWORDS/keyword logic left in `llm.py`).
- [ ] `GET /api/reviews/{id}` and PATCH responses include `matched_keywords`,
      `missing_keywords`, `keyword_coverage`.
- [ ] Coverage is computed for every provider (it never calls the LLM) and is
      based on the pending CV (accepted suggestions applied).
- [ ] Review page shows green "Covered" and red "Missing" chip lists plus a
      coverage bar; accepting a keyword suggestion moves that keyword.

## Phases

### Phase 1 — Keyword service
- Files: `backend/app/services/keywords.py` (new), `backend/app/services/llm.py`
- Changes: move `STOPWORDS`, `_keywords` here as `extract_keywords`;
  `coverage()` returns keyword lists + percentage; import in `llm.py`.
- Verify: unit-style `python -c` run against a sample CV/JD pair.

### Phase 2 — API surface
- Files: `backend/app/routers/reviews.py`, `backend/app/schemas.py`
- Changes: `KeywordCoverageOut`; `ReviewOut` gains the three fields;
  `ScoreOut` gains them too; `_pending_cv_text` used as the coverage input on
  GET/serialize and on PATCH.
- Verify: curl review + PATCH and inspect JSON.

### Phase 3 — UI
- Files: `frontend/src/components/KeywordPanel.jsx` (new),
  `frontend/src/pages/ReviewPage.jsx`
- Changes: panel under the score card with coverage bar and chip lists; state
  updated from every PATCH response.
- Verify: browser shows chips; accepting an ADD keyword suggestion moves it
  from Missing to Covered.

## Out of scope

- Stemming/synonyms/embeddings; per-provider keyword extraction by the LLM;
  persisting coverage columns (computed deterministically from stored text, so
  no schema change is needed).
- Changing the scoring formula used by real LLMs.

## Database impact

None.

## Verification

1. `curl localhost:8001/api/reviews/2 | jq '.keyword_coverage, .missing_keywords'`
2. Accept a keyword suggestion via PATCH → coverage rises, keyword moves lists.
3. Browser: KeywordPanel renders and agrees with the API JSON.
