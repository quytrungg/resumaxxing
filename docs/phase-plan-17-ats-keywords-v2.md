# Phase Plan — Initiative 17: ATS keyword coverage v2 (LLM requirements + alias matching)

> Required by AGENTS.md rule 1: this plan must exist and be confirmed by the
> user before any implementation code is written.
>
> Supersedes the extraction half of `phase-plan-3-ats-keywords.md`. Scope chosen
> by the user: **B + C only** — LLM requirement extraction, plus alias-aware
> matching. Heuristic extractor improvements (option A) are explicitly excluded.

## Goal

Replace the current "30 most frequent single words from the JD, substring-matched"
signal with a real ATS report. On review creation the configured LLM extracts the
JD's actual requirements with importance, category and the JD sentence that
justifies each one; deterministic alias-aware matching then decides which of
those the current (pending) CV covers. The panel shows real terms like
`Kubernetes` and `PostgreSQL`, split into must-have vs nice-to-have, with the JD
quote as evidence — instead of filler like `nice`, `deep`, `hands`, `building`.

### Why the current panel is unhelpful (measured)

`keywords.extract_keywords()` ranks single tokens by raw frequency over the whole
JD, with a 44-word stoplist, then matches with plain substring `in`.

```
$ python3 -c "... extract_keywords(jd, 30)"     # Senior Backend JD
['backend', 'pipelines', 'platform', 'actions', 'architecture', 'aws',
 'building', 'collaborate', 'deep', 'designers', 'designing', 'docker',
 'driven', 'endpoints', 'engineers', 'event', 'familiarity', 'gcp', 'github',
 'grafana', 'graphql', 'hands', 'kafka', 'kubernetes', 'learning', 'machine',
 'managers', 'mentor', 'nice']
```

Four independent failure modes, all addressed by this plan:

1. **Requirements are absent, filler is present.** `PostgreSQL`, `Terraform`,
   `Redis`, `Prometheus`, `OpenTelemetry`, `CI/CD`, `Go` each appear once and are
   dropped by the `top_n` cutoff; `nice`, `deep`, `hands`, `building` survive.
2. **Multi-word and punctuated terms are shredded.** `CI/CD` → `ci` + `cd`
   (both below the 3-char floor, lost entirely); `machine learning` → two words;
   `REST APIs` → `apis`.
3. **Matching is substring, so it is wrong in both directions.** Verified
   false positive: a CV containing only "JavaScript" reports
   `matched: ['java']`. False negative: "capital" does not satisfy `API`.
4. **No importance weighting.** Coverage is `matched/30` over an arbitrary bag,
   so the percentage carries no actionable meaning.

## Success criteria

- [x] Creating a review persists a `jd_requirements` JSON list on the
      `JobDescription` row, each entry shaped
      `{label, canonical, aliases, importance, category, quote}` with
      `importance ∈ {must, nice}` and `label` in the JD's original casing
      (`PostgreSQL`, `CI/CD`, `OpenTelemetry`).
- [x] For the sample Senior Backend JD above, the extracted labels include
      `PostgreSQL`, `Kubernetes`, `Terraform`, `Redis`, `Kafka`, `GraphQL`,
      `CI/CD`, `OpenTelemetry`, `Prometheus` — and include **none** of
      `nice`, `deep`, `hands`, `building`, `collaborate`, `designers`.
- [x] Regression: CV text `"Expert in JavaScript and TypeScript."` against a JD
      requiring `Java` yields `matched: []` (the `java` requirement stays
      missing). A CV containing both "JavaScript" and "Java" yields
      `matched: ['Java']`.
- [x] Alias regression: a CV saying `K8s` covers a `Kubernetes` requirement;
      `Postgres` covers `PostgreSQL`; `RESTful API` covers `REST`.
- [x] `GET /api/reviews/{id}` returns `requirements[]` with per-item
      `matched`, plus `keyword_coverage` (weighted), `must_have_coverage` and
      `nice_to_have_coverage`. Legacy `matched_keywords` / `missing_keywords` /
      `keyword_coverage` remain populated and agree with the new fields.
- [x] Accepting an ADD suggestion moves that requirement from missing to matched
      on the next GET (coverage is still computed from `_pending_cv_text()`).
- [x] `POST /api/reviews/{id}/requirements/refresh` re-extracts and returns the
      updated requirement list.
- [x] Provider failure during extraction downgrades to the heuristic list with a
      logged warning; the review does not fail.
- [x] `mock` provider still runs with zero API keys end to end (see Out of scope
      for its expected quality).
- [x] Review page renders must-have and nice-to-have groups, a split coverage
      bar, and the JD quote behind each requirement.

## Phases

### Phase 1 — Requirement model, alias table, matcher (pure Python, no DB, no LLM)

- Files: `backend/app/services/requirements.py` (new),
  `backend/app/services/skills_aliases.py` (new, data only)
- Changes:
  - `skills_aliases.py`: `ALIASES: dict[str, list[str]]` keyed by canonical
    lowercase skill (`kubernetes -> [k8s]`, `postgresql -> [postgres]`,
    `javascript -> [js]`, `rest -> [restful api, rest api]`, …). Data only, so
    it can grow without touching logic.
  - `requirements.py`: `Requirement` pydantic model; `normalize(text)`;
    `match_requirements(cv_text, requirements) -> {matched, missing, coverage,
    must_have_coverage, nice_to_have_coverage}`. Matching uses word-boundary
    regexes (`(?<![a-z0-9+#])java(?![a-z0-9+#])`) and lets `-`/`/`/whitespace`
    vary inside multi-word terms (`ci/cd`, `ci cd`, `ci-cd` all match).
  - `from_heuristic(jd_text)` adapts today's `keywords.extract_keywords()`
    output into `Requirement` objects (`importance="must"`, quote = the JD line
    containing the term, canonical via `ALIASES`). This is the mock/offline
    fallback and is deliberately **not** an improvement over current extraction.
- Verify: `python3 -c` against the sample Senior Backend JD + a toy CV, asserting
  the two regression criteria (Java/JavaScript, K8s/PostgreSQL/RESTful aliases).
  Output pasted into Verification.

### Phase 2 — LLM extraction + persistence

- Files: `backend/app/services/llm.py`, `backend/app/services/requirements.py`,
  `backend/app/models.py`, `backend/app/schemas.py`,
  `backend/alembic/versions/<new>_jd_requirements.py`
- Changes:
  - `REQUIREMENTS_PROMPT`: return only a JSON array of
    `{label, canonical, importance, category, quote}`; 10–25 items; hard/soft
    split driven by the JD's own wording; `quote` must be a verbatim JD
    sentence; no invented requirements.
  - `llm.extract_requirements(jd_text, settings, provider, model)` via the
    existing non-streaming `_chat_completion()` + `_extract_json()`; `mock`
    short-circuits to `requirements.from_heuristic()`.
  - `models.py`: `JobDescription.jd_requirements = Column(JSON, nullable=True)`
    — stored on the JD because the requirement set is a property of the posting
    text, which never changes, and a future JD-dedupe/import gets it for free.
  - `routers/reviews.py::_run_review`: call `extract_requirements` alongside the
    suggestion call, store it on `review.job_description.jd_requirements` in the
    same commit. Wrapped in try/except → `from_heuristic()` fallback + warning.
  - `schemas.py`: `RequirementOut`; `ReviewOut.requirements`,
    `ReviewOut.must_have_coverage`, `ReviewOut.nice_to_have_coverage`.
- Verify: create a review with a real provider, then
  `psql -c "select jsonb_pretty(jd_requirements) from job_descriptions ..."` and
  eyeball the labels. Repeat with `mock`: review still completes, requirements
  are the heuristic set.

### Phase 3 — API surface

- Files: `backend/app/routers/reviews.py`, `backend/app/schemas.py`
- Changes:
  - `_serialize`: prefer `job.jd_requirements`; when null (rows predating the
    migration) fall back to `from_heuristic(job.raw_text)` so old reviews still
    render. Derive `matched/missing/coverage` from `match_requirements()` over
    `_pending_cv_text()`, and keep writing the legacy keyword fields for
    backward compatibility.
  - `POST /{review_id}/requirements/refresh` → re-extract, overwrite the JD
    column, return `ReviewOut`.
  - `rescore` response (`ScoreOut`) gains `requirements` so the panel stays in
    sync after a decision, matching how it already returns coverage.
- Verify: `curl` GET review, POST refresh, POST rescore; `jq` the three coverage
  numbers and confirm `matched + missing` partitions the requirement list.

### Phase 4 — UI

- Files: `frontend/src/components/KeywordPanel.jsx`,
  `frontend/src/pages/ReviewPage.jsx`, `frontend/src/api.js`
- Changes:
  - Panel: split coverage bar (must-have solid, nice-to-have light), two groups
    ("Must have (n/m)" / "Nice to have (n/m)"), chips carrying the JD quote as a
    `title` tooltip plus an expandable per-chip line, and a "Refresh keywords"
    action wired to the new endpoint.
  - `ReviewPage`: pass the requirement list through; update state from both the
    rescore response and refresh response. Keep Tailwind utility classes and the
    existing chip colour language (green covered / red missing).
- Verify: browser at `localhost:5174` — group counts match the API JSON, tooltip
  shows the JD sentence, accept-and-refresh moves a chip.

## Out of scope

- **Option A (heuristic extractor improvements)** — n-gram keyphrases,
  section-aware weighting, better stoplist. Consequence to accept: the `mock`
  provider's requirement list stays roughly as noisy as today (it now goes
  through alias matching but is still frequency-derived). Real providers get the
  good list. Revisit as Initiative 18 if mock quality matters.
- `heuristic_suggestions()` emitting junk ADD entries (`"- Nice"`, `"- Deep"`)
  into the Skills section. Same root cause, ~5-line follow-up; separate change.
- Semantic/embedding matching and synonym discovery beyond the alias table.
- Auto-generating CV suggestions from missing requirements for real providers.
- Changing the score formula. `heuristic_score()` keeps its current behaviour;
  real-provider scoring is untouched.
- Stemming beyond the alias table.

## Database impact

One Alembic revision (`--autogenerate` → `upgrade head`) adding
`job_descriptions.jd_requirements JSON NULL`. No backfill needed: null means
"not extracted yet" and `_serialize` falls back to the heuristic list.
`alembic_version` stays at head. No ad-hoc DDL expected.

## Verification

Evidence recorded during implementation, in order.

### 1. Matcher (Phase 1) — junk filtered, real requirements kept

Sample Senior Backend JD through `requirements.parse_requirements()` with a
model-shaped payload (including deliberate junk entries `deep` and `nice`):

```
LLM LABELS (after junk filter): 20
['Python', 'Go', 'PostgreSQL', 'Kubernetes', 'Docker', 'Terraform', 'REST APIs',
 'GraphQL', 'Kafka', 'Redis', 'event-driven architecture', 'CI/CD',
 'GitHub Actions', 'Prometheus', 'Grafana', 'OpenTelemetry', 'AWS', 'GCP',
 'machine learning', 'windows server 2003']
JUNK PRESENT? []          REQUIRED PRESENT? True
```

### 2. False-positive regression — Java vs JavaScript

```
JavaScript-only CV -> []
JS + Java CV       -> ['Java']
```

### 3. Ambiguous term (`Go`) is not prose

```
prose 'go to market' -> []
'Languages: Go'      -> ['Go']
```

### 4. Alias / multi-word matching

Same CV (`Skills: Python, K8s, Postgres, RESTful APIs, CI CD pipelines, ...`)
against the same list:

```
COVERAGE 56 (must 59, nice 0)
MATCHED: Python, Go, PostgreSQL, Kubernetes, REST APIs, Kafka, Redis,
         event-driven architecture, CI/CD, Grafana
```

`K8s`->`Kubernetes`, `Postgres`->`PostgreSQL`, `RESTful APIs`->`REST APIs`,
`CI CD`->`CI/CD`, `event driven`->`event-driven architecture`.

### 5. Weighting

```
mixed (1/2 must + 1/2 nice): cov 50, must 50, nice 50
nice-only list:              cov 0,  must None, nice 0
```

### 6. Persistence + real provider (review 36, `opencode_go`)

Three prompt iterations on the same live review, same CV/JD:

| extraction version | items | coverage | notes |
| --- | --- | --- | --- |
| v1 | 21 | 57% | phrase-shaped labels ("cloud-based applications") |
| v2 (atomic-term rules + qualifier stripping) | 20 | 45% | labels atomic, categories still unmatched |
| v3 (categories get concrete `aliases`) | 22 | 82% | `Front-end Frameworks` covers via `React` |

Final stored list (abridged) — the panel's actual content:

```
COVER must | Front-end Frameworks | aliases: React, Vue, Angular, Svelte, Next.js, Nuxt
COVER must | testing frameworks  | aliases: Jest, Vitest, Mocha, Jasmine, Cypress, Playwright
COVER must | semantic HTML       | aliases: HTML semantics, semantic markup
MISS  must | prototyping         | aliases: interactive prototypes, ...
```

Row check: `select jd_requirements from job_descriptions where id = …` is
non-null and holds the JSON above; `alembic current` = `45af988a6a0d (head)`.

### 7. API surface

`GET /api/reviews/36` → `"82% of JD requirements"`, `requirements[]` length 22,
`matched + missing` partitions the list.

`POST /api/reviews/37/rescore` (mock):

```
score 27 | cov 28 | must 28 | nice None | reqs 25 | matched 7
history entry: re-evaluated (1 accepted, 0 rejected, 6 pending)
partition ok: True
```

`POST /api/reviews/36/requirements/refresh` → 200, rewrites the JD column.

### 8. Mock end-to-end (no API keys)

Review 37 created with `llm_provider: "mock"` → 202, `run_state: complete`, 25
heuristic requirements with quotes. Accepting suggestion `- Docker` moved that
requirement from missing to covered on the next GET (`24%` → `28%`), proving
coverage is still computed from `_pending_cv_text()`.

### 9. Browser (Chrome via CDP, `localhost:5174`)

Review 36: header `ATS keyword coverage`, `82% of JD requirements`, `Refresh`
button, group `Must have (18/22)`, 22 chips of which 18 are green, and clicking
the red `prototyping` chip reveals:

> “Constructs quick interactive prototypes that illustrate UI design: …”

Review 37 with a seeded 3-must/2-nice list: groups `Must have (0/3)` and
`Nice to have (0/2)` plus the two split bars. Screenshots: `ats-panel2.png`,
`ats-split.png` in the session temp folder.

### 10. Build/health

`npm run build` → 142 modules, clean. `python -m compileall app` → clean.
No unused imports in the touched modules.

### Notes

- Extraction adds one serial LLM call to each review run (~80 s against
  `opencode_go` with a LinkedIn-length JD). It runs before the suggestion
  pipeline, so total run time grows by roughly that amount.
- `heuristic_suggestions()` still builds ADD entries from the old keyword list,
  so `mock` reviews can propose `- Deep` / `- Pipelines` even though the panel
  now filters those out. Recorded as out of scope above.
