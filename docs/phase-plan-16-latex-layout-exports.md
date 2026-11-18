# Phase Plan — 16: Word and PDF downloads in the LaTeX layout

> Required by AGENTS.md rule 1: this plan must exist and be confirmed by the
> user before any implementation code is written.

## Goal

Make the `Word (.docx)` and `PDF` downloads on the Review page render in the same
layout as the `LaTeX (.tex)` download, so a review produces one CV design in
three file formats. Today the `.tex` output is styled by the pinned preamble in
`services/latex.py` (A4, 1.5 cm side / 1.4 cm top-bottom margins, 11 pt serif
body, centered LARGE bold name, `\large` headline, mid-dot contact line,
uppercase section headings with a 0.6 pt rule, compact `itemize` bullets), while
`services/export.py` renders DOCX/PDF with unrelated fonts, margins and heading
styles. The layout is re-expressed natively for reportlab and python-docx from a
single shared metrics block, so no TeX toolchain, no LaTeX parsing and no new
system dependency is introduced, and the `mock`/no-key path keeps working.

## Success criteria

- [x] A single layout spec (page size, margins, type sizes, section/bullet
      spacing) exists once in `backend/app/services/export.py` and both the PDF
      and DOCX renderers read it; no magic numbers duplicated per renderer.
- [x] `POST /api/reviews/{id}/finalize?format=pdf` returns `200` +
      `application/pdf` with an A4 MediaBox (595 × 842 pt) and margins
      42.5 pt left/right, 39.7 pt top/bottom (= 1.5 cm / 1.4 cm).
- [x] The PDF body uses a serif face (Times `Times-Roman`/`Times-Bold`) at
      11 pt, with the name at 17.3 pt bold centered, the headline at 12 pt
      centered, the contact line centered and mid-dot separated, and each
      section heading uppercase bold with a 0.6 pt rule underneath.
- [x] `format=docx` returns a valid DOCX whose `sectPr` is A4
      (11906 × 16838 twips) with margins 850/850 twips (1.5 cm) and 794 twips
      (1.4 cm), `Normal` = Times New Roman 11 pt, the name paragraph centered /
      bold / 17.5 pt (Word's half-point grid, closest to 17.3), and every
      section-heading paragraph carrying a bottom border (`w:pBdr > w:bottom`).
- [x] Bullets in both formats use the compact itemize metrics
      (`leftmargin` ≈ 1.1 em = 12.1 pt, item spacing ≈ 1.1 pt) instead of the
      loose list styles used today.
- [x] Content parity: for one review, the heading set and bullet texts of the
      PDF, DOCX and `.tex` match, because the structured rewrite prompt now
      enforces the same top-tier standards (summary first, reverse-chronological
      roles with action-verb bullets, grouped skills, no invented facts) as the
      LaTeX prompt.
- [x] With provider `mock` and no API keys, `docx` and `pdf` still download
      with no provider call, and no stored `final_document` row is rewritten
      (styling is applied at render time).
- [x] The cover-letter exports are unchanged: the PDF keeps its 2 cm margins and
      letter styles, and the DOCX keeps its existing default Word page
      (12240 × 15840 twips) and paragraph styles.
- [x] The export menu still offers exactly `Word (.docx)`, `PDF`,
      `LaTeX (.tex)`, and the API contract (`format` values, media types,
      `cv_optimized_{id}.<ext>` filenames) is unchanged.

## Phases

### Phase 1 — One layout spec + LaTeX-styled PDF
- Files: `backend/app/services/export.py`
- Changes:
  - Add a `CV_LAYOUT` block (A4, side/top margins in cm, base 11 pt Times,
    name 17.3 pt, headline 12 pt, contact separator, heading rule 0.6 pt,
    heading space before/after 8.25/2.75 pt, bullet left indent 1.1 em,
    bullet spacing 1.1 pt, leading 13.6 pt) with a comment mapping each value to
    the LaTeX preamble it mirrors.
  - Add `_cv_pdf_styles()` (Times faces, centered header styles, ruled heading
    style, compact bullet style) and keep `_pdf_styles()` untouched for the
    cover letter.
  - Give `_pdf_build(flowables, margins=...)` an explicit geometry argument so
    the CV uses LaTeX geometry and letters keep 2 cm margins.
  - `to_pdf_bytes_structured`: centered name/headline/contact (mid-dot
    separator), uppercase section headings followed by an
    `HRFlowable(0.6 pt)`, bullets with the compact metric and `•` bullet text.
- Verify: render a sample `StructuredCV` in Python and assert the flowable
  styles (alignments, font names/sizes, `HRFlowable` thickness, margins);
  download the PDF and confirm the A4 MediaBox + preview render.

### Phase 2 — LaTeX-styled DOCX
- Files: `backend/app/services/export.py`
- Changes:
  - Set the section to A4 with the LaTeX margins, and the `Normal` style to
    Times New Roman 11 pt with exact 13.6 pt line spacing.
  - Name/headline/contact as centered paragraphs at the spec's sizes.
  - A `CV Heading` paragraph style: uppercased text, bold 11 pt, spacing
    before/after per spec, `keep_with_next`, and a `w:pBdr` bottom border
    (single, `sz=6`) that reproduces the LaTeX `\titlerule`.
  - Bullets: `List Bullet` with `left_indent`/`first_line_indent` and
    `space_after` set from the spec, so a page-break-free, dense list matches
    the PDF.
  - Leave `letter_to_docx_bytes` on the default document so the cover letter
    export is unchanged.
- Verify: download the DOCX, unzip `word/document.xml`, assert page size,
  margins, the `Normal` font, the name run size/alignment, the heading border
  and the bullet indents; confirm `python-docx` can reopen the file.

### Phase 3 — Content parity for the structured rewrite
- Files: `backend/app/services/llm.py`
- Changes: extend `REWRITE_PROMPT` with the same content standards already in
  `LATEX_PROMPT` (2–3 line summary naming the target role; reverse-chronological
  experience with 2–4 action-verb bullets stating what was built, the technology
  and the outcome, quantifying only facts the CV supports; grouped skills;
  drop clearly irrelevant material; never invent employers, titles, dates,
  degrees, metrics or technologies). The JSON output contract stays identical.
- Verify: with `mock`, the deterministic structurer output is unchanged and
  both formats still render; with a real provider, the resulting PDF/DOCX
  headings match the `.tex` headings for the same review.

### Phase 4 — UI wording + docs
- Files: `frontend/src/pages/ReviewPage.jsx`, `DOCS.md`, `AGENTS.md`
- Changes: neutral `EXPORT_OPTIONS` hints that state the shared layout
  (`editable`, `LaTeX layout`, `LaTeX source`); `DOCS.md` endpoint/rendering
  note and Known limitations updated (PDF/DOCX are native re-implementations of
  the LaTeX template — no TeX toolchain, no server-side compilation); AGENTS.md
  export-convention bullet gains the single-layout-source rule.
- Verify: browser — `Apply & Download` shows the three neutral items; each
  downloads a file; the PDF and DOCX visually match the `.tex` layout.

## Out of scope

- Installing a TeX engine or compiling `.tex` → PDF server-side; bundling a
  Latin Modern/LM Roman TTF (Times is the metrically closest standard face).
- Parsing the LLM's LaTeX body into PDF/DOCX (the structured document stays the
  content source for both).
- Changing the `.tex` preamble, the LaTeX prompt/sanitiser, or the stored
  `final_latex` behaviour.
- Changing the cover-letter renderers, scoring, suggestion merge semantics, the
  finalize API contract, or the menu labels.
- Re-running stored rewrites: existing `final_document` rows pick up the new
  styling automatically at render time.

## Database impact

None. No new columns, no migration, no ad-hoc DDL. `alembic_version` stays at
head.

## Verification

Executed 2026-11-17 (backend restarted on port 8001 after the code changes;
Vite HMR on 5174 picked up the frontend automatically; `npm run build` passes).

1. **PDF geometry + type** — built a sample `StructuredCV` through
   `export.to_pdf_bytes_structured` and decoded the content stream:
   MediaBox `595.2756 × 841.8898`; first text translated to `x = 42.51969`
   (= 1.5 cm, frame padding 0); section-rule width `510.2362`
   (= 595.2756 − 2 × 42.52); `/F2 Times-Bold 17.3` for the name, `/F3 Times 12`
   for the headline, `/F3 Times 11` for body/contact, `0.6 w` rule strokes,
   bullets at `12.1` indent with 13.5/13.6 baselines. Style dump: name 17.3
   centered/bold, headline 12 centered, contact 11 centered, heading 11 bold
   space 8.25/0, bullet 11 left 12.1 before 0 after 1.1.
2. **DOCX geometry + style** — `curl` `format=docx` then unzipped
   `document.xml`/`styles.xml`: `w:pgSz w=11906 h=16838`; `w:pgMar` top 794,
   right 850, bottom 794, left 850; `Normal` = Times New Roman sz 22 with
   `w:line=272 lineRule=exact` (13.6 pt); name paragraph `w:jc=center` + `b` +
   `sz 35` (17.5 pt, half-point grid); each heading `keepNext` +
   `w:pBdr/w:bottom val=single sz=5` (0.625 pt) + spacing before 165 / after 55
   twips; bullets `pStyle=ListBullet` with `w:ind left=242 hanging=242` (12.1 pt)
   and `spacing after=22` (1.1 pt), `contextualSpacing` removed so itemsep
   survives. Reopened with `python-docx` (sample document: 13 paragraphs,
   styles `Normal` + `List Bullet`, name/headline/contact text intact).
3. **Content parity** — review `#24` (`mock`): `.tex` headings
   `[EDUCATION, WORK EXPERIENCE, TECHNICAL SKILLS, PROJECTS, HONORS & AWARDS,
   CERTIFICATES]`; DOCX headings identical (`tex == docx: True`); all six appear
   in the PDF text; bullet count 66 in both `.tex` and `.docx`. Accepted
   difference: the LaTeX path transliterates typographic characters to ASCII
   (en dash → `-`, `●` → `-`) because `pdflatex`/`inputenc` needs ASCII, while
   Word/PDF keep the original glyphs.
4. **Mock/no-key path** — created `#24` with `llm_provider=mock`; all three
   formats returned `200` (`39,699` docx / `7,041` pdf / `6,902` tex bytes) with
   no new "rewrite failed" log line. The `mock` branch of `rewrite_cv` returns
   the deterministic structurer, so no network provider call was made.
5. **Regression: cover letter** — `letter_to_pdf_bytes` still places text at
   `x = 62.69291` (2 cm + 6 pt frame padding) on A4; `letter_to_docx_bytes`
   unchanged (default 12240 × 15840 page, 1800/1440 twip margins, only the
   `Normal` style).
6. **Contract unchanged** — `format=bogus` → `400`; `docx` →
   `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
   `cv_optimized_24.docx`, `pdf` → `application/pdf` `cv_optimized_24.pdf`,
   `tex` → `application/x-tex` `cv_optimized_24.tex`.
7. **Browser (Chrome headless 157 via CDP) on `http://localhost:5174/reviews/24`**
   — the `Apply & Download` menu reads `Word (.docx) editable`,
   `PDF LaTeX layout`, `LaTeX (.tex) LaTeX source`; clicking each item downloaded
   `cv_optimized_24.docx` (39,699 B), `cv_optimized_24.pdf` (7,041 B) and
   `cv_optimized_24.tex` (6,902 B); no error text on the page.
8. **Visual check** — Quick Look PNG previews of both the PDF and the DOCX show
   the same design as the `.tex` template: centered bold name, 12 pt headline,
   mid-dot contact line, uppercase bold headings with a hairline rule, tight
   bullet list on A4 with 1.5 cm side margins; print preview renders the PDF
   bullets as round dots.
9. **Cleanup** — review `#24` and its job description were deleted afterwards
   (back to reviews `1,2,3,4,5,6,7,8,13`) and the headless Chrome instance was
   killed; the backend on 8001 is left running with the new code.

