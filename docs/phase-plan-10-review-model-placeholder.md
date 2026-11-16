# Phase Plan — Show the provider's default model in the New Review "Model (optional)" placeholder

> Required by AGENTS.md rule 1: this plan must exist and be confirmed by the
> user before any implementation code is written.

## Goal

In the New CV Review modal (step **3. Review model**), the `Model (optional)`
picker renders the literal text `Provider default` while nothing is selected,
even though the app already knows exactly which model that default resolves to
(`savedSettings[spec.modelField]`, else `spec.defaultModel` — e.g.
`deepseek-v4.1-flash` for Opencode Go, `claude-sonnet-4-5` for Claude). Show the
resolved default model in the placeholder instead, so the reviewer can see which
model will run before submitting, without opening the dropdown.

Pure display change: the submitted payload is unchanged (an empty selection still
omits `llm_model` and the backend falls back to the same saved/seed default), and
`ModelSelect` already renders the placeholder in a muted style, so the default
reads as a hint, not as a picked value.

## Success criteria

- [ ] With the active/converted provider's default known, the trigger of
      `Model (optional)` shows that model name (e.g. `deepseek-v4.1-flash`) in
      the muted placeholder style while nothing is selected.
- [ ] Choosing a model replaces the placeholder with that model, and re-selecting
      the `Default · <model>` row returns the trigger to the placeholder.
- [ ] Switching provider in the modal updates the placeholder to that provider's
      default (`claude` → `claude-sonnet-4-5`, `opencode_go` →
      `deepseek-v4.1-flash`).
- [ ] If the default cannot be resolved (provider not in the frontend map), the
      placeholder falls back to the existing `Provider default` text.
- [ ] Submitted payload unchanged: with no model chosen, `POST /api/reviews`
      carries `llm_provider` and no `llm_model`, and the review still runs with
      mock plus a keyed provider.
- [ ] `mock` selected → the Model field is still hidden entirely.
- [ ] `npm run build` in `frontend/` passes; no backend files change.

## Phases

### Phase 1 — Placeholder wiring
- Files: `frontend/src/components/NewReviewModal.jsx`
- Changes: pass `placeholder={providerDefault || 'Provider default'}` to the
  `ModelSelect` in the Review model section. `providerDefault` is already
  computed above from `savedSettings[spec.modelField]` / `spec.defaultModel`, and
  `defaultOption={providerDefault}` already keeps the dropdown's
  `Default · <model>` row in sync, so no other logic moves.
- Verify: browser at 5174 — open New Review, read the placeholder for the saved
  provider, switch providers, pick a model, re-pick the Default row, submit one
  review and confirm the created review's `llm_model` is null.

## Out of scope

- The Settings page's `Model (optional)`-style picker (`placeholder="Provider
  default"` there stays as-is — it edits the stored default itself, so naming a
  default in its own placeholder would be circular).
- `ModelSelect` component changes (its placeholder rendering is already the
  muted-text behaviour this relies on).
- Pre-selecting the default as a real value, sending `llm_model` automatically,
  or auto-picking the first model in the list.
- Backend, schema, migration, or review-creation validation changes.

## Database impact

None. No model/schema change; only the display text of one input.

## Verification

1. Backend on 8001 (already running), browser at 5174:
   - Open the New Review modal from Reviews → placeholder shows the active
     provider's default model (`opencode_go` → `deepseek-v4.1-flash`).
   - Switch the Provider select to `ollama` → placeholder becomes that
     provider's saved/seed default; switch back.
   - Open the dropdown: first row still reads `Default · <model>`; pick a real
     model → trigger shows it; re-pick `Default · <model>` → placeholder returns.
   - Select `mock` → Model field hidden.
   - Submit a review with no model picked; confirm via `GET /api/reviews/{id}`
     that `llm_model` is null and the review was created, then delete/ignore the
     test review (no schema change, so nothing to clean up beyond the review row
     created by the test).
2. `cd frontend && npm run build` → passes.
