# Phase Plan — "Use" button per saved provider in Model providers

> Required by AGENTS.md rule 1: this plan must exist and be confirmed by the
> user before any implementation code is written.

## Goal

Today a saved provider can only be made active by clicking anywhere on its row
in the Settings → Model providers list. That affordance is invisible: the row
looks like a static card, and only the `Test` link hints that the row is
interactive. Add an explicit **Use** button next to **Test** on every saved
provider row so switching the active API key is an obvious, discoverable
action. No backend change is needed — activation is already
`PUT /api/settings {"llm_provider": "<value>"}`, which the page calls through
`activateProvider()`; only the control that triggers it is new.

Current state (verified via `curl localhost:8001/api/settings`): two keys saved
(`ollama`, `opencode_go`), active provider `opencode_go` — enough to exercise
the button without adding credentials.

## Success criteria

- [ ] Every configured provider row shows a `Use` button immediately left of
      `Test`, inside the same right-hand button cluster.
- [ ] Clicking `Use` on a non-active row switches the active provider: that row
      gains the `✓ active` chip and indigo styling, the previous row loses it,
      and `GET /api/settings` reports the new `llm_provider`.
- [ ] The active row's button is disabled (still labelled `Use`, muted, with a
      tooltip) so the control cannot re-fire a no-op save — the label stays
      `Use` rather than `Active`.
- [ ] Clicking `Use` never also triggers the row's own click handler (no double
      `PUT`): observed as exactly one `PUT /api/settings` in devtools per click.
- [ ] While a switch is in flight the clicked button shows `Using…` and other
      `Use` buttons are disabled (no overlapping switches).
- [ ] Failure path: an injected 500 leaves the UI unchanged and shows the error
      in the existing notice line (no phantom active chip).
- [ ] Row click still activates the provider (existing shortcut kept), and
      `Test` / delete behave exactly as before.
- [ ] `npm run build` in `frontend/` passes; no backend files change.

## Phases

### Phase 1 — Use button in the provider row
- Files: `frontend/src/pages/SettingsPage.jsx`
- Changes:
  - New state `activating` (`string | null`) alongside `testing`.
  - `activateProvider(provider)`: early-return when the provider is already
    active or an activation/test is running; set `activating`, keep the
    existing `saveSettings({ llm_provider })` call and success/error notices,
    clear `activating` in `finally`.
  - Render a `Use` text button in the row's `ml-auto` cluster, before `Test`:
    `type="button"`, `e.stopPropagation()`, label `Active` (disabled) when the
    row is active, `Using…` while in flight, `Use` otherwise; `title`/`aria-label`
    naming the provider.
- Verify: browser at 5174 — switch between the `ollama` and `opencode_go` rows,
  watch the chip/styling move, confirm one `PUT /api/settings` per click and
  the new `llm_provider` in the network response.

## Out of scope

- Backend, schema, migration or `llm.py` changes — `llm_provider` switching
  already exists and is covered by `docs/phase-plan-7-provider-settings.md`.
- Removing the row-click shortcut, restyling the rows, or converting `Test`
  into a button (it stays a text action).
- Auto-testing a key before activating it, or blocking activation when `Test`
  fails — `Use` only changes which saved key is active.
- Per-review provider pinning, the New Review modal, model default selection.
- Any change to key storage, masking, encryption or the delete flow.

## Database impact

None. `user_settings.llm_provider` already exists (String 50); this feature only
writes a different value through the existing endpoint. No Alembic migration, no
ad-hoc DDL, `alembic_version` untouched.

## Verification

1. Backend on 8001 (already running): `curl -s localhost:8001/api/settings`
   before and after the UI click — `llm_provider` follows the clicked row.
2. Browser at 5174 (`npm run dev` already serving):
   - Row `ollama` → `Use` → chip moves, notice "Ollama Cloud is now the active
     provider."
   - Row `opencode_go` → `Use` → chip moves back.
   - Active row's button reads `Active` and is disabled.
   - One `PUT /api/settings` per click in the network panel.
   - `Test` on a row still returns "Connected · N models"; delete still
     confirms and removes the row.
   - Failure path: temporarily stub `request` to reject (or point the browser at
     a stopped backend briefly) → error notice, no chip change.
   - Restore `llm_provider` to `opencode_go` (its pre-test value).
3. `cd frontend && npm run build` → passes.
