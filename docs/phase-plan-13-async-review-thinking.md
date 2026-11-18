# Phase Plan — Async review with a live "thinking" view

> Required by AGENTS.md rule 1: this plan must exist and be confirmed by the
> user before any implementation code is written.

## Goal

Creating a review currently blocks `POST /api/reviews` for the whole pipeline:
JD scrape → suggestion call → scoring call (30–120 s with a real provider), so
the modal sits on "Analyzing…" and there is nowhere to look while it works.

Change the flow so the review row is created and returned immediately, the LLM
work continues in the background, and the browser navigates straight to
`/reviews/{id}` where a **thinking panel** streams what the model is doing —
numbered stages (job description → CV scan → drafting suggestions → scoring)
with the model's own streamed text nested under the active stage, mirroring how
coding agents show their work. When the run finishes the panel is replaced by
the normal review page: score gauge, keyword panel, score history and the
suggestion cards, without a manual reload.

Confirmed design decisions (from the design Q&A):

1. **Stages + live tokens.** Each stage is narrated with real information
   (matched/missing keywords for `mock`, provider/model, prompt sizes), and the
   model's streamed output/reasoning text is nested under the active stage.
2. **SSE over `fetch`** (`GET /api/reviews/{id}/events`) so the optional
   `X-App-Password` header still works; `EventSource` cannot send headers.
3. **Live only.** The transcript lives in an in-memory broker, survives page
   reloads/navigation, and is intentionally not persisted. Only the run state
   (`running`/`complete`/`failed`) and an error message are stored on the review
   row so a finished or broken review renders correctly later.

## Success criteria

- [x] `POST /api/reviews` returns **202** within ~1 s for a provider-backed
      review, with `run_state: "running"`, `current_score: 0`, `suggestions: []`
      and a real `id`; the JD scrape/LLM work happens after the response.
- [x] `GET /api/reviews/{id}` immediately after creation shows
      `run_state: "running"`; a later GET shows `run_state: "complete"`, a
      non-zero score, one `score_events` row (`initial review`) and the
      suggestions — with **no browser attached at all** (proves the run is not
      tied to the request/SSE connection).
- [x] `curl -N …/api/reviews/{id}/events` emits SSE frames: a `stage` frame per
      stage, `delta` frames with text under the active stage, and exactly one
      terminal `done` frame carrying the final score.
- [x] With `mock` and no API keys, the stream still shows real analysis lines
      (JD keyword count, coverage, missing keywords, suggestion count) and ends
      with `done` — no artificial sleeps are added.
- [x] With a real provider, `delta` frames arrive **before** the run finishes
      (token streaming), and reasoning-capable models surface their
      `reasoning_content`/`thinking` text as `thinking` deltas.
- [x] A provider failure yields HTTP 202 + `run_state: "failed"` on the next
      GET, a populated `run_error`, and an `error` SSE frame; no partial
      suggestions are written and `current_score` stays 0.
- [x] Opening `/reviews/{id}` while running (direct link, refresh, or the modal
      navigating immediately) shows the thinking panel, replays already-emitted
      events on reconnect, and switches to the full review page when `done`
      arrives.
- [x] Two reviews created back-to-back both run and stream independently.
- [x] While a run is in progress, `GET /api/health` and `GET /api/reviews`
      respond in under 1 s (no event-loop blocking).
- [x] A review stuck in `running` with no in-memory run (e.g. after a backend
      restart) is reconciled to `failed` with an "interrupted" message the next
      time its detail page or stream is requested — it never spins forever.
- [x] `npm run build` passes; the whole flow works end-to-end with `mock` and no
      API keys.

## Phases

### Phase 1 — Backend: create the review immediately

- Files: `backend/app/models.py`, `backend/app/schemas.py`,
  `backend/app/routers/reviews.py`, `backend/alembic/versions/<new>.py`
- Changes:
  - `CVReview` gains `run_state` (`String(20)`, not null, server default
    `'complete'`) and `run_error` (`Text`, null). Kept separate from the existing
    `status` enum so no Postgres enum surgery is needed and `draft`/`finalized`
    keep their meaning.
  - Alembic autogenerate + hand-check: `server_default='complete'` so existing
    rows stay valid; `alembic_version` stays at head.
  - `ReviewOut` gains `run_state` and `run_error`.
  - `POST /api/reviews` → `status_code=202`: scrape the JD synchronously (so bad
    URLs still fail in the modal with 400), persist `JobDescription` +
    `CVReview(run_state="running")`, commit, register the run, schedule the work
    with `asyncio.create_task`, and return the serialized review.
  - New `_run_review(review_id, cv_text, jd_text, provider, model)` background
    coroutine: own `SessionLocal()` in `try/finally`, writes suggestions,
    `current_score`, the `initial review` score event and `run_state="complete"`
    in one commit; on exception writes `run_state="failed"` + `run_error` and
    emits an `error` event.
- Verify: `curl -i -X POST /api/reviews -d '{"jd_text":"…","llm_provider":"mock"}'`
  → 202 + `run_state: "running"`; sleep 2; `GET /api/reviews/{id}` →
  `complete`, score, suggestions; `psql` shows `run_state`/`run_error` columns
  and `alembic_version` at head.

### Phase 2 — Backend: in-memory run broker

- Files: `backend/app/services/progress.py` (new)
- Changes:
  - `ReviewRun` = bounded event buffer (cap ~2 000 events / 256 KB, dropping
    oldest deltas first), ordered `seq`, `done`/`failed` flags, and a set of
    subscriber `asyncio.Queue`s.
  - Module API: `open_run(review_id)`, `emit(review_id, event)` (returns `seq`,
    fans out to subscribers), `get_run(review_id)`, `snapshot(review_id)`,
    `subscribe/unsubscribe`, `close_run(review_id)`, `active(review_id)`.
  - Events are plain dicts: `{seq, type: stage|delta|done|error|heartbeat, stage,
    label, text, score, message}`.
  - Keep a strong reference to each background `asyncio.Task` in the registry so
    it cannot be garbage-collected mid-run. Module docstring records the
    single-process assumption.
- Verify: unit-style check via a temporary Python snippet — open a run, emit
  three events from a task, snapshot from the "main" coroutine returns them in
  order; buffer cap drops oldest entries.

### Phase 3 — Backend: stream provider output

- Files: `backend/app/services/llm.py`
- Changes:
  - `_stream_chat_completion(provider, settings, system, user, model, session,
    emit) -> str`: `httpx.AsyncClient.stream` (replaces the sync `httpx.post`
    for this path only).
    - OpenAI-compatible (`ollama`, `opencode`, `opencode_go`): `"stream": true`,
      parse `data:` frames, forward `delta.content` as `output` and
      `delta.reasoning_content` / `delta.reasoning` as `thinking`; keep the
      `x-opencode-session` header.
    - `claude`: `"stream": true`, parse `content_block_delta` frames —
      `thinking_delta` → `thinking`, `text_delta` → `output`. No extended-thinking
      parameters are added (they 400 on models that don't support them); the
      handler exists so reasoning text is surfaced when present.
    - Returns the concatenated `output` text, so JSON parsing is unchanged.
  - `llm_review_streaming(cv_text, jd_text, settings, provider, model, emit) ->
    (score, suggestions)`: emits stages `jd`, `cv`, `suggestions`, `score`, then
    delegates to the same parsing/validation as today. `llm_review` becomes a
    thin wrapper (`emit=None`) so there is one code path. `mock` emits real
    heuristic narration (keyword counts, coverage, missing keywords, suggestion
    count) and returns the existing heuristic results.
  - Prompts ask for a short prose analysis before the JSON (`SUGGESTION_PROMPT`,
    `SCORING_PROMPT`) so the thinking panel has something human-readable to
    stream; `_extract_json` switches to `json.JSONDecoder().raw_decode` from the
    first `{`/`[` (falling back to today's regex) so leading prose cannot break
    parsing.
  - Deltas before the first `{`/`[` are tagged `thinking`; once the payload
    starts, subsequent deltas are tagged `output` and the UI shows a
    "composing…" indicator for that stage instead of raw JSON.
- Verify: a temporary script awaits `llm_review_streaming(...)` with `mock` and
  prints the emitted events; with a real key, `curl -N` on the SSE endpoint shows
  prose deltas arriving over several seconds, and the final suggestions parse.

### Phase 4 — Backend: SSE endpoint + reconciliation

- Files: `backend/app/routers/reviews.py`
- Changes: `GET /api/reviews/{review_id}/events` →
  `StreamingResponse(media_type="text/event-stream", headers={"Cache-Control":
  "no-cache", "X-Accel-Buffering": "no"})`:
  - If `run_state != "running"` → one terminal frame (`done` with the current
    score, or `error` with `run_error`) and close.
  - If `running` but no live run exists → reconcile: set `failed` +
    `run_error="Interrupted (backend restarted)"`, commit, emit `error`, close.
  - Otherwise replay the buffer (`id: <seq>` + `data: <json>` frames), then
    subscribe and stream new events, heartbeating (`: ping`) every 15 s while
    polling `request.is_disconnected()`; unsubscribe in `finally`. Client
    disconnects must never cancel the background task.
- Verify: `curl -N …/events` on a fresh mock review → stage frames then one
  `done`; repeat on a completed review → single terminal frame; kill the
  connection mid-run → `GET /api/reviews/{id}` still reaches `complete`.

### Phase 5 — Frontend: streaming client

- Files: `frontend/src/api.js`
- Changes: `streamReviewEvents(id, { onEvent, signal, onError })` using
  `fetch('/api/reviews/' + id + '/events', { headers: authHeaders(), signal })`,
  reading `res.body.getReader()` with `TextDecoder`, splitting on blank lines,
  parsing `data:` payloads as JSON and dispatching each event. Returns a
  promise that settles on `done`/`error`. Missing-body/parse failures surface
  via `onError` so the page can fall back to polling `getReview` once.
- Verify: temporary `console.log` in the browser while a mock review runs shows
  the frames in order.

### Phase 6 — Frontend: thinking panel + instant navigation

- Files: `frontend/src/pages/ReviewPage.jsx`,
  `frontend/src/components/ThinkingPanel.jsx` (new),
  `frontend/src/components/NewReviewModal.jsx`,
  `frontend/src/pages/HomePage.jsx`
- Changes:
  - `NewReviewModal.handleSubmit` → `createReview`, then `navigate` immediately
    (the modal's busy state only covers the POST, which now returns in ~1 s).
  - `ReviewPage`: branch on `review.run_state`.
    - `running` → render header + `ThinkingPanel` (stage timeline with
      done/active/pending markers, elapsed timer, provider/model, nested
      monospace transcript that auto-scrolls unless the user scrolled up,
      blinking caret on the active delta, "composing…" indicator during the
      `output` phase). Subscribe on mount; on `done` → `getReview(id)` and swap
      to the normal view; on `error` → red message + `run_error` +
      "Create a new review" hint; reconnect with capped backoff (×3) and then
      poll `getReview` every 2 s.
    - `complete`/`failed` → today's page, plus a small red banner when
      `run_state === "failed"`.
  - `HomePage`: running reviews show `Analyzing…` instead of `0%` and a subtle
    in-progress badge; the link goes to the detail page which streams.
- Verify: browser at :5174 with `mock` → modal navigates instantly, panel shows
  stages and finishes into the review; direct link into a running review
  replays the transcript; refresh after completion shows the normal page.

### Phase 7 — Docs

- Files: `DOCS.md`, `AGENTS.md`
- Changes: API table (POST is 202 + background run, new SSE endpoint, event
  shapes), schema list (`run_state`, `run_error`), LLM section (streaming,
  reasoning-first prompts), Known limitations (single-worker in-memory broker,
  transcript not persisted, run results lost if the process dies mid-run).
  `AGENTS.md` conventions gain one line: review creation is asynchronous —
  never move LLM work back into the POST handler.
- Verify: read-back.

## Amendment (confirmed before implementation)

Analysis of review #25 showed a second defect that the original plan only
partially covered: the LLM calls run synchronously inside `async def` handlers
(`llm.py` used `httpx.post`, `scrape.fetch_jd` used `httpx.Client`), which blocks
the single uvicorn event loop. Reproduced: a review creation in flight made
`GET /api/health` and `GET /api/reviews` time out after 10 s. That means even a
manual navigation to `/reviews/{id}` could not be served while a run was in
progress.

So phase 3 is widened: **every** provider call and the JD scrape must be
non-blocking, not just the review path. Concretely:

- `_chat_completion` becomes `async` using `httpx.AsyncClient` (fixes
  `rescore`, `finalize`, `cover-letter` too).
- `fetch_jd` stays synchronous but the router awaits it via
  `asyncio.to_thread`.
- New success criterion: while a review run is in progress,
  `GET /api/health` and `GET /api/reviews` respond within 1 s.

## Out of scope

- Streaming `rescore`, `finalize`, or `cover-letter` (they keep their current
  synchronous behaviour).
- Persisting transcripts (no `review_events` table), review replay history, or
  a "view thinking again" view for finished reviews.
- Cancel/retry endpoints, queueing, concurrency limits, or multi-worker support
  (the broker assumes one uvicorn process).
- A dedicated `/reviews/:id/live` route — the existing detail route branches on
  `run_state`.
- Redesigning the suggestion cards, score gauge, keyword panel or history chart.
- Enabling provider extended-thinking parameters (`thinking.budget_tokens`).

## Database impact

Yes — one Alembic migration adds two nullable/defaulted columns to
`cv_reviews`:

- `run_state VARCHAR(20) NOT NULL DEFAULT 'complete'`
- `run_error TEXT NULL`

Existing rows backfill to `complete`. No other table changes; `status` stays
`draft|finalized` and the enum is untouched.

## Verification## Verification

Executed on 2026-11-17 against local postgres, uvicorn on :8001 and vite on
:5174. Throwaway reviews created during the checks were deleted afterwards
(ids 26–34); review 25 (the reported case) is untouched.

1. **Migration.** `.venv/bin/alembic upgrade head` →
   `727e64c979b4`; `\d cv_reviews` shows `run_state varchar(20) NOT NULL
   DEFAULT 'complete'` and `run_error text`; `alembic_version` is at head.
2. **Fast create.** `POST /api/reviews` with `llm_provider: "mock"` →
   **202 in 0.115 s**, `run_state: "running"`, `current_score: 0`,
   `suggestions: []`; with `opencode_go`/`deepseek-v4.1-flash` → **202 in
   0.054 s**.
3. **SSE pipeline.** `curl -N /api/reviews/27/events` emitted `stage` frames
   for `jd`, `cv`, `suggestions`, `score`; ~1 250 `delta` frames of reasoning
   text arriving progressively (t=0.0 s → 42.2 s), `output` deltas only after
   the JSON `[`, and exactly one `done` with `score: 73`. The review row
   finished `complete` with 73, 8 suggestions and one `initial review` score
   event.
4. **Disconnect does not cancel.** Killing the `curl -N` stream mid-run left
   the run running; a later `GET` returned `complete` with the full result.
5. **Provider failure.** `POST` pinned to a non-existent model → 202; next
   `GET` → `run_state: "failed"`, readable `run_error` (provider 400),
   `current_score: 0`, 0 suggestions, 0 score events; `GET /events` returns one
   `error` frame.
6. **No event-loop blocking.** While a real 42 s run was in flight:
   `/api/health` 3.7–5.1 ms, `/api/reviews` 35–44 ms, `/api/reviews/27` 7–8 ms.
   Before the change the same scenario timed out at 10 s.
7. **Browser.** Chrome (headless, playwright-core) against vite :5174:
   - the modal flow landed on `/reviews/{id}` while the run was still going;
   - the thinking panel showed the four stages, provider/model, an elapsed
     timer and a growing transcript (1 602 chars after 4 s);
   - Home listed the run as "Analyzing…", and clicking it navigated to the
     detail page's panel;
   - a mid-run refresh replayed 1 129 chars of transcript;
   - on completion the panel was replaced by the review view (Match Score 72%,
     6 pending suggestions) with no reload.
   The timer initially read `25206s`: `created_at` is naive UTC and JS parsed
   it as local time. Normalised to UTC in `ThinkingPanel`; re-verified 4 s after
   3 s.
8. **Concurrency.** Two back-to-back `POST`s returned 202 (ids 29, 30); both
   completed independently with one score event each.
9. **Interrupted run.** Created a real run, restarted uvicorn mid-run; the next
   `GET` reconciled it to `failed` with "Interrupted (the backend restarted
   while this review ran)" and the SSE endpoint returned that `error` frame.
10. **Build.** `cd frontend && npm run build` passes.

Known limitation confirmed in practice: the broker is per-process, so a
restart loses partial results (row reconciled to `failed`).
