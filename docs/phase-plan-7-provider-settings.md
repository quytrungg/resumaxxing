# Phase Plan — Model provider credentials & model prefetch

> Required by AGENTS.md rule 1: this plan must exist and be confirmed by the
> user before any implementation code is written.

## Goal

Replace the single-key Settings form with a "Model providers" panel: one row per
configured provider (Claude, Ollama Cloud, Opencode Zen) showing a masked key,
an `active` badge, a Test action and a delete action, plus an add/update form
(provider, API key, optional base URL, default model). After a key is entered,
the backend lists that provider's models and the form's Default Model field
becomes a dropdown of those models. The same prefetched catalog feeds the
per-review Model picker in the New Review modal, so users pick from real model
IDs instead of typing them. The panel keeps the app's existing light/dark
Tailwind styling while matching the structure of the reference screenshots.

Assumption: one credential per provider (the three providers can coexist, as
the reference copy says). Multiple keys for the *same* provider are out of scope
for this plan; that would need a separate credentials table and review pinning
by credential id.

## Success criteria

- [ ] `alembic upgrade head` adds `user_settings.{claude,ollama,opencode}_base_url`
      and `user_settings.{claude,ollama,opencode}_model`; existing rows unaffected.
- [ ] `GET /api/settings` returns the new fields, keys still masked only.
- [ ] `PUT /api/settings` saves key/base URL/default model for the chosen
      provider; blank key or an echoed `…` preview never overwrites a stored key.
- [ ] `POST /api/settings/providers/models` returns `{"models": [...]}` from the
      provider's model-list endpoint using either the pasted key or the saved key
      (blank `api_key`); a bad key returns HTTP 400 with a readable message and
      never echoes the key.
- [ ] `DELETE /api/settings/providers/{provider}` clears that provider's key, base
      URL and default model; if it was active, `llm_provider` falls back to `mock`.
- [ ] Settings page renders one row per configured provider with masked preview,
      green `active` badge, Test result ("Connected · N models" / error) and a
      trash button; clicking a row makes that provider active.
- [ ] The add/update form prefetches models ~500 ms after a key (or base URL)
      stops changing, offers them in the Default Model dropdown, and the add
      button persists and refreshes the list.
- [ ] New Review modal's Model field is a dropdown populated from the prefetched
      catalog for the effective provider (with free-text fallback) and the chosen
      model is pinned on the created review.
- [ ] `llm.py` uses the saved base URL for chat calls and the saved default model
      when the review has no per-review model override.
- [ ] Full flow verified in a browser at http://localhost:5174 with the mock
      provider and no real API keys; model listing verified against a local stub
      OpenAI-compatible server.
- [ ] `npm run build` passes.

## Phases

### Phase 1 — Schema and settings API
- Files: `backend/app/models.py`, `backend/app/schemas.py`,
  `backend/app/routers/settings.py`, `backend/alembic/versions/<new>.py`
- Changes:
  - Add six nullable `String` columns to `UserSettings`: three base URLs
    (`String(500)`) and three default models (`String(100)`).
  - Autogenerate the Alembic revision and upgrade to head.
  - `SettingsIn`/`SettingsOut` gain the six optional fields; `_settings_out`
    passes them through. PUT keeps `exclude_unset` partial-update semantics;
    empty string clears a base URL/model (keys keep the existing blank/masked
    guard).
  - Add `DELETE /api/settings/providers/{provider}` (validated provider set,
    clears key/base/model, resets active provider to `mock` when needed).
- Verify: curl GET/PUT/DELETE against :8001, inspect DB columns with psql, confirm
  `alembic_version` is the new head.

### Phase 2 — Provider model catalog service and endpoint
- Files: `backend/app/services/model_catalog.py` (new),
  `backend/app/routers/settings.py`, `backend/app/services/llm.py`
- Changes:
  - `model_catalog.py` holds a provider spec: key field, default base URL,
    models path and auth headers. Listing rules:
      - Claude → `GET {base}/v1/models?limit=1000`, `x-api-key` +
        `anthropic-version: 2023-06-01`, read `data[].id`.
      - Ollama → `GET {base}/v1/models`, `Authorization: Bearer`, read
        `data[].id`; default base `https://ollama.com`. A local daemon works by
        setting `http://localhost:11434` as base URL.
      - Opencode → `GET {base}/models`, bearer auth, default base
        `https://opencode.ai/zen/v1`, read `data[].id`.
    `httpx.AsyncClient` timeout 20 s; non-2xx and malformed payloads raise a
    provider-labelled error without the key; base URLs must be http(s).
  - `POST /api/settings/providers/models` takes
    `{provider, api_key?, base_url?}`, falls back to the decrypted stored key
    when `api_key` is blank/masked, and returns `{models: [...sorted...]}`.
  - `llm.py` chat calls use `settings.{provider}_base_url` when set, and
    `resolve_choice` falls back to `settings.{provider}_model` before the
    hardcoded default.
- Verify: curl the endpoint with a missing key (expect a clean 400), then point
  the Ollama base URL at the local stub server and confirm the returned model
  list.

### Phase 3 — Shared provider metadata and model combobox
- Files: `frontend/src/llmProviders.js` (new),
  `frontend/src/components/ModelSelect.jsx` (new),
  `frontend/src/api.js`
- Changes:
  - `llmProviders.js`: provider value/label/key field/base URL field/model
    field/default model/default base URL, plus `loadCatalog`/`saveCatalog`
    helpers backed by `localStorage['modelCatalog']`.
  - `ModelSelect.jsx`: button + popup listbox. Shows `model · Provider` rows,
    checkmark on the selected value, a filter input, Arrow/Enter/Escape
    handling, click-outside close, `max-h` internal scroll, and free-text
    fallback when the typed value matches no option. Theme-aware Tailwind.
  - `api.js`: `listProviderModels({provider, api_key, base_url})` and
    `deleteProvider(provider)`.
- Verify: build passes; component exercised through the Settings page in
  Phase 4 (no probe left behind).

### Phase 4 — Settings page redesign
- Files: `frontend/src/pages/SettingsPage.jsx`
- Changes:
  - "Model providers" card: icon + title + explanatory copy, then one row per
    provider with a saved key: provider pill, masked preview, green `active`
    badge, Test button, trash button. Row click activates the provider
    (`PUT {llm_provider}`); Test and delete stop propagation.
  - Dashed add/update panel matching the reference layout: PROVIDER select,
    API KEY password input, BASE URL (OPTIONAL), DEFAULT MODEL (ModelSelect),
    `+ Add key` button. Selecting a provider that already has a key shows
    "saved — leave blank to keep"; saving updates base URL/model without
    touching the key. Debounced (500 ms) prefetch drives the model dropdown;
    Test reuses the same endpoint and reports model count or the error.
  - Delete asks for confirmation, then clears the row. Keep the LinkedIn URL
    card and existing save/error feedback. Light and dark styles both use the
    app's existing palette (gray/indigo, rounded-lg cards).
- Verify: browser at :5174 (dark and light) — add a key against the stub base
  URL, see prefetched models, save, row appears with mask, activate another
  provider, delete, reload and confirm persistence.

### Phase 5 — New Review model picker
- Files: `frontend/src/components/NewReviewModal.jsx`
- Changes: replace the free-text Model input with `ModelSelect`; on modal open,
  use the cached catalog and silently refetch models for the effective provider
  via the saved key; show loading/error inline; keep "provider default" when
  empty; submit still sends `llm_model`.
- Verify: open New Review, switch provider, confirm options appear, create a
  review with a selected model, check the pinned `llm_model` on the review page.

### Phase 6 — Docs
- Files: `DOCS.md`
- Changes: update the settings API table, schema list, provider section (base
  URL/default model, model listing), and known limitations.
- Verify: the full matrix below.

## Out of scope

- Multiple API keys for the same provider, key rotation/aliases, per-key labels.
- Adding OpenAI/Codex, Gemini or a separate local-Ollama provider entry (local
  Ollama is reachable through the Ollama base URL).
- Model metadata beyond IDs (pricing, context length, capabilities), streaming,
  token accounting, or automatic periodic refresh.
- Changing review creation, scoring, rewrite or export behavior; no prompt or
  provider-routing changes beyond base URL/default model plumbing.

## Database impact

One Alembic migration on `user_settings` adding six nullable columns. No ad-hoc
DDL and no data backfill; `alembic_version` stays at the new head.

## Verification

1. `backend/.venv/bin/alembic upgrade head`; `psql -c '\d user_settings'` shows
   the six columns.
2. Stub provider: run a tiny HTTP server on `127.0.0.1:8899` serving
   `/v1/models` → `{"data":[{"id":"stub-a"},{"id":"stub-b"}]}`; save Ollama base
   URL `http://127.0.0.1:8899`, then `POST /api/settings/providers/models`
   returns both IDs; with a bad URL/key it returns 400 and no key material.
3. curl PUT/GET/DELETE settings round-trips: masked key, base URL, default
   model, active fallback to `mock` after deleting the active provider.
4. Browser: Settings dark + light, add/update/prefetch/activate/test/delete;
   New Review dropdown lists the stub models and pins the selection.
5. `npm run build` in `frontend/`; backend still healthy at `/api/health`.
