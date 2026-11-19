# Phase Plan — Move ATS requirement extraction off the critical path, and fold the initial score into the suggestion call

> Required by AGENTS.md rule 1: this plan must exist and be confirmed by the
> user before any implementation code is written.

## Goal

Creating a review is serial today: JD/CV read → **LLM requirement extraction** →
suggestion drafting → scoring. The extraction call is the only stage that is
(a) non-streaming, so the thinking panel shows "Waiting for the model…" with no
feedback, and (b) not an input to stages 4–5 (`SUGGESTION_PROMPT` and
`SCORING_PROMPT` receive only `cv_text` + `jd_text`). It is used solely for the
keyword-coverage panel (`job_descriptions.jd_requirements` → `_serialize`).

Two changes cut the wait:

1. **Overlap the requirement extraction** with suggestion drafting and scoring,
   so wall time becomes `max(requirements, suggestions + score)` instead of
   `requirements + suggestions + score`. Also reduce that call's output burden
   (drop the verbatim `quote`, which the backend derives from the JD for free)
   and reuse a stored `jd_requirements` list when the same posting text was
   already extracted for the same provider.
2. **Merge the initial score into the suggestion response** — the suggestion
   call already reads the CV + JD and writes an analysis, so asking it for a
   `score` alongside the suggestion array removes a whole sequential round-trip.
   This applies **only to the initial review**; `POST /api/reviews/{id}/rescore`
   keeps its own standalone scoring call because the user can re-evaluate
   independently after accepting/rejecting suggestions.

Net effect for a real provider: one concurrency-overlapped extraction plus a
single generation call, instead of three sequential calls.

## Success criteria

- [x] `GET /api/reviews/{id}/events` shows the `requirements` stage `stage`
      frame **before** the `suggestions` stage frame, and the requirements
      completion `delta` frame arrives **after** suggestion drafting has
      started — proving the two calls overlap rather than run back to back.
- [x] With a real provider, total time from run start to the terminal `done`
      frame drops by roughly the requirement extraction time **plus** one
      scoring round-trip versus the current serial order (measured on the same
      JD/CV/provider and reported in Verification).
- [x] An initial review with a real provider issues **one** generation request
      after the extraction: the streamed `suggestions` stage carries both the
      suggestion array and the score, the `score` stage detail says the score
      came from that response, and no second scoring request is made.
- [x] The scoring rubric is one shared constant used by both the combined
      prompt and `SCORING_PROMPT`, so an initial score and a `/rescore` of the
      same review state are comparable. `/rescore` still performs its own
      standalone call and still appends one score-history entry.
- [x] If the combined payload has no usable `score` (or the model returns a
      legacy top-level array), the backend falls back to the existing
      standalone scoring call, so the review still completes with a score.
- [x] A requirements call failure no longer changes when the review finishes:
      the run still reaches `complete` with the heuristic list, a logged
      warning, and no traceback surfaced to the user.
- [x] `jd_requirements` rows still contain `{label, canonical, aliases,
      importance, category, quote}` and every `quote` is a verbatim JD line
      (derived locally when the model omits it).
- [x] Re-running a review on the same JD text with the same `llm_provider`
      reuses the stored list: the requirements delta appears immediately
      ("reused from an earlier review") and no extraction call is made.
- [x] Re-running the same JD text with a **different** provider still performs
      a fresh extraction (no cross-provider reuse, so `mock`'s heuristic list is
      never mistaken for LLM output).
- [x] Malformed individual suggestion objects are still dropped without failing
      the review, and keyword coverage after completion is computed from the
      same requirement list that was persisted.
- [x] With `mock` and no API keys the whole flow still works end-to-end with
      unchanged narration.
- [x] `npm run build` passes.

## Phases

### Phase 1 — Lighten the extraction call

- Files: `backend/app/services/llm.py`,
  `backend/app/services/requirements.py`
- Changes:
  - `REQUIREMENTS_PROMPT`: 8–20 items (was 10–25), aliases "up to four" (was
    six), and remove `quote` from the requested JSON keys along with its rule.
    Keep `label`, `canonical`, `aliases`, `importance`, `category`.
  - `requirements.py`: promote the existing `_quote_for(text, term)` to a public
    `quote_for(jd_text, label)` (single implementation; `from_heuristic` uses
    it too). No matching behaviour changes.
  - `llm.extract_requirements`: after `parse_requirements`, fill any missing
    `quote` with `requirements.quote_for(jd_text, r.label)`. Older stored rows
    keep their LLM-authored quotes; `parse_requirements` already tolerates a
    missing `quote`.
- Verify: run extraction against a sample JD with a real provider; confirm the
  model output has no `quote` key, the persisted list still has verbatim JD
  quotes, and `mock` output is unchanged.

### Phase 2 — Run extraction concurrently with the generation call

- Files: `backend/app/services/llm.py`
- Changes:
  - Add an internal coroutine `_requirements_or_fallback(...)` that wraps
    `extract_requirements` in the existing try/except (heuristic fallback +
    warning), emits the result narration delta under the `requirements` stage,
    and always returns a list — so awaiting it later can never raise.
  - `llm_review_streaming`:
    - `provider == "mock"`: unchanged — await the (instant, local) list
      immediately so narration and the mock score keep their current text.
    - Otherwise: emit the `requirements` stage with `parallel=True` and a detail
      such as `"{provider} · {model} · in parallel with suggestions"`, start
      `asyncio.create_task(_requirements_or_fallback(...))`, then run the
      generation call (Phase 3), and `await` the task before returning the
      tuple. In a `finally`, `cancel()` the task if the run failed before
      awaiting it (a provider error must not leave a dangling request).
  - `_stage(...)` gains an optional `parallel` flag that is forwarded in the
    event dict (existing callers unchanged).
- Verify: `curl -N .../events` on a real-provider run; check frame order (stage
  `requirements` → stage `suggestions` → deltas → requirements result delta →
  `done`) and that a forced extraction failure still ends in `complete`.

### Phase 3 — Fold the initial score into the suggestion response

- Files: `backend/app/services/llm.py`
- Changes:
  - Extract the scoring rubric into one constant (e.g. `SCORE_RUBRIC`) and
    append it to **both** the combined prompt and `SCORING_PROMPT`, so the
    initial score and `/rescore` stay on the same scale. The rubric instructs
    the model to score the CV **as provided, before applying its own
    suggestions**, 0–100.
  - `SUGGESTION_PROMPT` now asks for the prose analysis followed by a single
    JSON object: `{"score": <int 0-100>, "suggestions": [ …same keys as today… ]}`.
    `_json_splitter` needs no change (prose before the first `{` stays
    `thinking`; the payload streams as `output`).
  - `llm_review_streaming` (non-mock): replace the two generation calls with
    one. Parse `_extract_json(raw)` and accept all three shapes:
    - object with `suggestions` + valid `score` → both, no extra call;
    - object without a usable `score`, or a legacy top-level array →
      `_parse_suggestions` as today, then run the existing standalone
      `SCORING_PROMPT` call as a fallback so the run still ends with a score.
    Coerce the score to a clamped `int` (0–100) and treat non-numeric values as
    missing.
  - Emit the `score` stage after parsing, with detail "included in the
    suggestion response" (or "separate scoring call — no score in the payload"
    on the fallback path) and a `delta` carrying the number, so the panel's
    stage order and narration are preserved.
  - `llm_score` (used by `/rescore`) and the `mock` branch are untouched.
- Verify: with a real provider, `curl -N .../events` shows a single streamed
  generation with prose → JSON, then the `score` stage from that payload; a
  server log check shows one generation request after the extraction. Force the
  fallback by calling `llm_review_streaming` with a stubbed payload that omits
  `score` and confirm the standalone scoring call runs. Immediately `/rescore`
  the finished review, record both scores, and compare.

### Phase 4 — Reuse a stored requirement list for the same JD + provider

- Files: `backend/app/routers/reviews.py`, `backend/app/services/llm.py`
- Changes:
  - `create_review`: before creating the `JobDescription`, look up the newest
    `JobDescription.jd_requirements` joined to a `CVReview` with
    `user_id == user.id`, `llm_provider == provider`, `run_state == "complete"`
    and `JobDescription.raw_text == jd_text`. Copy a non-empty list onto the new
    `JobDescription` row (no schema change).
  - `llm_review_streaming` gains an optional `requirements_hint: list[Requirement] | None`.
    When provided, skip the LLM call, emit the requirements delta immediately
    with a "reused from an earlier review" note, and still run
    `match_requirements` so mock-style narration stays coherent. When absent,
    behave as Phase 2.
  - `_run_review`: pass
    `requirements.parse_requirements(review.job_description.jd_requirements)`
    as the hint when the create-time copy populated it, and keep persisting the
    final list on the JD row as today.
- Verify: create two reviews with the same `jd_text` and the same provider —
  the second one's requirements delta appears immediately with the reuse note
  and no extraction request is made (check provider request logs / timings).
  Create a third with a different provider and confirm a fresh extraction runs.

### Phase 5 — Show the parallel stage honestly in the thinking panel

- Files: `frontend/src/components/ThinkingPanel.jsx`
- Changes: `buildStages` remembers the `parallel` flag from the `stage` event
  and keeps a parallel stage that has not emitted its result `delta` marked
  active (spinner) even after a later stage becomes `activeKey`; once its delta
  arrives (or the run terminates) it renders as done. `STAGES` order and
  numbering are unchanged.
- Verify: in the browser during a real-provider run, the
  "Extracting ATS requirements" row keeps spinning while "Drafting suggestions"
  is live, then flips to a check when the result line lands; completed reviews
  are unaffected.

### Phase 6 — Docs

- Files: `DOCS.md`, `AGENTS.md`
- Changes: record that requirement extraction runs concurrently with the
  generation call and must stay independent of the suggestion/scoring prompts;
  document that an initial review takes its score from the suggestion payload
  while `/rescore` remains a standalone scoring call on the shared rubric;
  document the lighter payload (locally derived `quote`) and the same-JD +
  same-provider reuse rule. `AGENTS.md` conventions gain one line: the ATS
  requirement list must never become an input to the suggestion or scoring
  prompts, or the parallel run stops being valid.
- Verify: read-back.

## Out of scope

- Moving extraction fully after `done` (review completes before extraction and
  the panel upgrades later). The user chose parallel + lighten, which keeps a
  single terminal event and consistent data.
- Changing `/rescore` itself, its endpoint, score-history behaviour, or its
  prompt beyond sharing `SCORE_RUBRIC` wording.
- Merging finalize/cover-letter generation into any other call.
- Replacing LLM extraction with the heuristic extractor, or changing matching,
  weights, alias data, the keyword panel UI or the score gauge.
- A cross-review requirement cache keyed by JD hash with its own table/provenance
  column; the Phase 4 lookup is a query, not a new store.
- UI changes to the suggestion cards or score history.

## Database impact

None. No migration; `job_descriptions.jd_requirements` already exists and is
reused as-is.

## Risks / notes

- Some providers serialize or rate-limit concurrent requests; if the
  requirements request is slowed or 429s, the review still succeeds and the
  keyword list degrades to the heuristic fallback. Verify with the pinned
  provider before claiming the win.
- Asking one call for both suggestions and a score can shift the number versus
  the standalone prompt (the model has just written its own suggestions). The
  shared rubric plus the "score the CV as provided" instruction mitigates this;
  the plan records the initial-vs-rescore delta as evidence and flags it if it
  is large.
- A model that returns two JSON values (array, then a score object) loses the
  second one to `_extract_json`'s first-payload rule; the fallback scoring call
  covers it at the cost of the old round-trip.
- Phase 4 reuse matches on provider only (not model), so switching models
  within one provider keeps the cached list; switching providers re-extracts.
- If extraction fails on a completed run, the heuristic list is what gets
  persisted (existing behaviour), so a later review of the same JD + provider
  reuses it. That equals what a retry's fallback would produce; only a later
  provider recovery would have upgraded it.

## Verification

Executed on 2026-11-19 against local postgres, uvicorn restarted on :8001 and
vite on :5174. The saved provider is `opencode_go`; its default model
`glm-5.3` currently returns 403 from the provider, so real-provider runs pinned
`deepseek-v4.1-flash` (the model review 41 already used). Throwaway reviews
49–54 were deleted afterwards; the user's review 41 is untouched.

1. **Parallel extraction (real provider, review 51).** `curl -N` timing of the
   SSE stream:
   - `0.01s` stage `requirements` … "in parallel with suggestions"
     (`parallel: true`);
   - `0.01s` stage `suggestions` (generation starts immediately);
   - `3.11s` first suggestion `thinking` delta;
   - `7.47s` requirements result delta ("12 requirements identified …") while
     suggestions were still streaming;
   - `54.55s` stage `score` … "score from the suggestion response";
   - `54.55s` terminal `done` (score 2), i.e. **0.00 s** between the score
     stage and the end — no second scoring call happened.
2. **Timing.** The overlapped extraction cost 7.5 s of wall clock (it was ready
   at 7.47 s) and the removed scoring round-trip measured **7.2 s** as a
   standalone call (`POST /api/reviews/51/rescore`, HTTP 200 in 7.226 s). Serial
   time would therefore have been ≈69 s versus **54.6 s** observed, ~21% faster
   on this input. The suggestion call itself was unchanged (~51 s of the 54.6 s).
3. **Initial vs re-score consistency.** Review 51 finished with score **2**; an
   immediate `/rescore` on the unchanged state returned **1** (1-point delta),
   and `/rescore` still wrote its own `score_events` row (history went 1 → 2,
   reason "re-evaluated (0 accepted, 0 rejected, 5 pending)").
4. **Reuse (review 52).** Same JD text + same provider: stage
   `requirements` detail "reused from an earlier review" and the result delta at
   `0.01s` (no extraction request), the same 12 labels
   (`Python, PostgreSQL, Kafka, Kubernetes, Redis, AWS, Terraform, CI/CD,
   data pipelines, Go, GraphQL, OpenTelemetry`), run `complete`.
5. **No cross-provider reuse (review 53).** Same JD text with `mock` did **not**
   reuse the LLM list: labels were the heuristic set (`Backend`, `build`,
   `data`, `use`, …), proving the provider filter in `_stored_requirements`.
6. **Derived quotes.** Every persisted requirement from review 51 had a
   non-null `quote` (12/12), and a multi-line JD unit check returned the right
   line per term: `PostgreSQL → "- 5+ years with Python and PostgreSQL"`,
   `Kubernetes → "- Kubernetes in production"`, `Go → "Nice to have: Go"`.
7. **Fallbacks (offline harness with stubbed provider calls).**
   - Combined `{score, suggestions}` → one call (`['SUGGESTION']`), score 81
     used, no scoring call.
   - Legacy top-level array and `{suggestions: [...]}` without a score → one
     suggestion call + one standalone scoring call, score 74 from the fallback,
     stage detail "separate scoring call".
   - `extract_requirements` raising → warning logged, heuristic list used,
     review still returned score 66 / 2 requirements.
   - Generation raising → exception propagates and the extraction task is
     cancelled (never completed after the failure).
   - `mock` end-to-end: stages `jd, cv, requirements, suggestions, score`,
     unchanged narration, review 49/53 completed with suggestions and one
     score event.
8. **Parallel-stage panel (real browser, Chrome headless against vite :5174).**
   A screenshot at 9 s into a real run (review 54, fresh 814-char JD) shows
   stage 3 "Extracting ATS requirements" with its spinner and the detail
   "… · in parallel with suggestions" **and** stage 4 "Drafting suggestions"
   with a spinner and its live transcript simultaneously — the premature
   checkmark is gone. After completion the normal review page renders with the
   ATS panel built from the LLM list (completed review 51 screenshot).
9. **End-to-end completion (review 54).** Long JD: run reached `complete` with
   score 3, 7 suggestions, 1 score-history entry, 20 requirements — the merged
   payload parsed and persisted normally.
10. **Build.** `cd frontend && npm run build` → `✓ built in 1.22s`.

