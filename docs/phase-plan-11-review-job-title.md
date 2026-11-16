# Phase Plan — Title each CV review with its job-description title

> Required by AGENTS.md rule 1: this plan must exist and be confirmed by the
> user before any implementation code is written.

## Goal

The Reviews list currently labels every item `Review #<id>`, which says nothing
about what the review is for. Label each review with the job instead —
`Review for Senior Frontend Engineer at Acme Corp` — falling back to
`Review #<id>` only when no credible title can be extracted. The same heading is
shown on the review detail page.

Titles come from three sources, in order:

1. A title captured from the source page (`<h1>`, else `<title>`) when the JD was
   submitted as a URL.
2. An explicit label in the JD text (`Job Title:`, `Position:`, `Role:`,
   `Title:`), which also works for one-line scraped text.
3. The first non-empty line of a pasted, multi-line JD when it looks like a
   heading (short, no trailing sentence punctuation, not boilerplate such as
   `About us`), or the URL path slug.

A company is included only when the JD says so: an explicit
`Company:`/`Employer:`/`Organisation:` label, or an `at <Company>` form on the
heading line (`Senior Engineer at Acme`). No guessing from body paragraphs and
no URL-host guessing (job boards like `jobs.lever.co` are platforms, not
employers).

The resolved title/company are stored on `job_descriptions.title` /
`job_descriptions.company` at creation time so they stay stable, and existing
rows resolve lazily through the same extractor at serialization time (no data
backfill required).

## Success criteria

- [ ] Creating a review from pasted multi-line JD text whose first line is
      `Senior Frontend Engineer` returns `jd_title = "Senior Frontend Engineer"`
      and the row shows `Review for Senior Frontend Engineer`.
- [ ] A heading line `Senior Engineer at Acme Corp` yields
      `jd_title = "Senior Engineer"`, `jd_company = "Acme Corp"`, and the row
      shows `Review for Senior Engineer at Acme Corp`.
- [ ] An explicit `Company: Acme` / `Employer: Acme` line sets `jd_company`
      even when the heading has no `at` form; the rendered label appends
      ` at Acme` exactly once (no duplication when the heading already has it).
- [ ] Creating a review from text labelled `Job Title: Staff Data Engineer`
      returns `jd_title = "Staff Data Engineer"` even when it is not the first
      line.
- [ ] Creating a review from a URL whose page has `<h1>Product Designer</h1>`
      returns `jd_title = "Product Designer"` (title tag used when no `<h1>`,
      job-board suffixes such as `| LinkedIn` dropped).
- [ ] A JD with no credible title returns `jd_title = null` and the UI falls
      back to exactly `Review #<id>` — no guessing from body paragraphs.
- [ ] Pre-existing reviews (no stored title) still display a usable title when
      the raw text yields one, or the `Review #<id>` fallback otherwise.
- [ ] `jd_title`/`jd_company` are present in `ReviewOut` for `POST /api/reviews`,
      `GET /api/reviews` and `GET /api/reviews/{id}`; no other response field
      changes.
- [ ] The detail page shows the same `Review for …` heading (fallback
      `Review #<id>`), with the score gauge and actions unchanged.
- [ ] `alembic upgrade head` adds the two nullable columns and `downgrade -1`
      removes them, leaving `alembic_version` at the new head.
- [ ] `npm run build` in `frontend/` passes; the app still works end-to-end with
      the `mock` provider and no API keys.

## Phases

### Phase 1 — Title/company extractor
- Files: `backend/app/services/jd.py` (new)
- Changes: pure, dependency-free helpers
  - `clean_title(raw)` — collapse whitespace, strip bullets/markdown `#`,
    trim dangling separators, reject empty / >120 chars / sentence-like text.
  - `extract_title_from_text(text)` — labelled patterns first
    (`^\s*(job\s*title|position|role|title)\s*[:\-–—]\s*(.+)$`), then the first
    non-empty line when it is 3–120 chars, ≤15 words, no trailing `.`, and not
    boilerplate (`about us`, `job description`, `responsibilities`, …); an
    `at <Company>` suffix on that line is split off.
  - `extract_company_from_text(text)` — `Company:`/`Employer:`/`Organisation:`
    labels, else the `<Company>` part of the heading's `at` form.
  - `title_from_url(url)` — last meaningful path segment, `-`/`_` → spaces,
    title-cased; `None` for bare hosts and numeric ids.
  - `title_from_html(html)` — first `<h1>` text, else `<title>` with a trailing
    ` | Site` / ` - Site` segment dropped.
- Verify: `python -c` one-liners against the sample JD strings; print each
  result. No app wiring yet.

### Phase 2 — Capture and persist the title/company
- Files: `backend/app/models.py`, `backend/app/services/scrape.py`,
  `backend/app/routers/reviews.py`,
  `backend/alembic/versions/<rev>_job_description_title.py` (generated)
- Changes:
  - `JobDescription.title` / `.company` = `String(255)`, both nullable.
  - `scrape.py` keeps `fetch_jd_text(url)` for compatibility and adds
    `fetch_jd(url) -> (text, title)` reusing the same SSRF/redirect/size guards;
    the page is parsed once for text and `title_from_html`.
  - `create_review` resolves title (URL: scraped title, else text/URL heuristic;
    paste: text heuristic) and company (text heuristic) and stores both on the
    new `JobDescription` row.
  - Alembic revision adds the two nullable columns (up/down verified).
- Verify: `alembic upgrade head` on the local Postgres, then `POST /api/reviews`
  with pasted text and with a URL, reading `job_descriptions.title/company` and
  the response; `alembic downgrade -1` then `upgrade head` on a scratch DB.

### Phase 3 — Expose the title/company
- Files: `backend/app/schemas.py`, `backend/app/routers/reviews.py`
- Changes: add `jd_title: Optional[str] = None` and
  `jd_company: Optional[str] = None` to `ReviewOut`; `_serialize` sets them from
  the stored columns or, when null, from the text extractor (and URL slug for
  the title).
- Verify: `curl /api/reviews` and `/api/reviews/{id}` show the title/company for
  new and pre-existing rows; an untitled JD returns `null`.

### Phase 4 — Show the title in the UI
- Files: `frontend/src/pages/HomePage.jsx`,
  `frontend/src/pages/ReviewPage.jsx`
- Changes:
  - Shared label: `Review for <title>[ at <company>]`, fallback `Review #<id>`.
  - List card headline uses it; the muted `jd_text` preview and score/status
    badges stay as they are.
  - Detail page: the same heading above the score/actions card.
- Verify: browser on :5174 with the mock provider — list and detail show the JD
  title/company; a JD with no title falls back to `Review #<id>`.

### Phase 5 — Docs
- Files: `DOCS.md`
- Changes: add `jd_title`/`jd_company` to the review response/API and schema
  notes.
- Verify: read-back of the edited sections.

## Out of scope

- Editing or renaming a review title (no PATCH endpoint, no inline edit).
- LLM-generated titles, or changing the provider/prompt payloads — the title is
  a deterministic local extraction.
- Company inference from the URL host or from body prose.
- Backfilling historical rows via a data migration; the read-time fallback
  covers them.
- Sidebar copy, page titles, exports (`cv_optimized_*` filenames) and the cover
  letter.
- Any sorting, filtering or search change on the Reviews list.

## Database impact

One Alembic revision: nullable `title` and `company` `String(255)` columns on
`job_descriptions`, with the matching `drop_column` downgrade. Nullable, so no
backfill and no locking concern on the local DB. No ad-hoc DDL.
`alembic_version` stays at head.

## Verification

1. `cd backend && alembic upgrade head`; confirm the columns with a `psql`
   `\d job_descriptions`.
2. With uvicorn on :8001 and the `mock` provider (no keys):
   - `POST /api/reviews {jd_text: "Senior Frontend Engineer\nAcme Corp\n..."}`
     → `jd_title == "Senior Frontend Engineer"`, `jd_company == null`.
   - `POST /api/reviews {jd_text: "Senior Engineer at Acme Corp\n..."}` →
     `jd_title == "Senior Engineer"`, `jd_company == "Acme Corp"`.
   - `POST /api/reviews {jd_text: "About us\n...\nCompany: Acme\nJob Title:
     Staff Data Engineer\n..."}` → `jd_title == "Staff Data Engineer"`,
     `jd_company == "Acme"`.
   - `POST /api/reviews {jd_url: <page with <h1>Product Designer</h1>>}` →
     `jd_title == "Product Designer"`.
   - `POST /api/reviews {jd_text: "We are a fast-growing company..."}` (one
     paragraph, no heading) → `jd_title == null`.
   - `GET /api/reviews` → every row carries both fields; existing rows resolve
     from raw text or return null.
3. `psql resumaxxing -c "select id, title, company from job_descriptions order
   by id desc limit 3"` matches the API.
4. Browser on :5174: the list reads `Review for <title> at <company>` (fallback
   `Review #<id>`) and the detail page shows the same heading; score,
   suggestions and export flows unchanged.
5. `cd frontend && npm run build` passes.
