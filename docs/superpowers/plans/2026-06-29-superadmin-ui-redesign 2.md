# Super Admin UI/UX Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Super Admin panel consistent and professional by extracting a shared token/CSS layer, deleting leftover dark-theme CSS, and converting ad-hoc inline styles to reusable component classes — with zero color changes.

**Architecture:** Add one stylesheet `static/css/superadmin.css` (tokens + migrated shell styles + component classes), linked ONLY from `templates/superadmin/base.html`. Delete dead per-page `<style>` blocks that redefine core classes with an old dark palette. Convert heavy inline `style="…"` clusters to component classes page by page. Optionally drop `!important` once conflicts are gone.

**Tech Stack:** Django templates (server-rendered), plain CSS (CSS custom properties). No JS, no build step, no new dependencies.

## Global Constraints

- Scope is **Super Admin only** — never modify Employee Admin (`templates/employeeadmin/`, `.ea-*`), the public site (`static/css/style.css`, `tt-*`), or Django admin.
- **No color/palette changes.** Every token value is copied verbatim from the existing light theme in `templates/superadmin/base.html`. Colors must look identical before/after.
- `static/css/superadmin.css` is referenced ONLY by `templates/superadmin/base.html`.
- Templates and CSS only — no view/model/URL/logic changes.
- No new JS dependencies. Row actions stay inline (no `⋮` dropdown).
- Static files are served from `static/` (`STATICFILES_DIRS = [BASE_DIR / "static"]`); load with `{% load static %}` + `{% static 'css/superadmin.css' %}`.
- Verification is code-based: grep + load the page in a running dev server. No screenshot baselines.

---

## File Structure

- **Create** `static/css/superadmin.css` — single source of truth for the Super Admin panel: `:root` tokens, migrated shell styles (from base.html's inline `<style>`), and component classes.
- **Modify** `templates/superadmin/base.html` — replace the inline `<style>` block with a `<link>` to `superadmin.css`.
- **Modify (delete `<style>` blocks)** 8 pages: `rooms.html`, `properties.html`, `guests.html`, `loyalty_config.html`, `tax_config.html`, `audit_log.html`, `room_images.html`, `event_images.html`.
- **Modify (inline → component classes)** all 17 pages, heaviest first.

---

## Task 1: Foundation — create `superadmin.css` and link it from the shell

**Files:**
- Create: `static/css/superadmin.css`
- Modify: `templates/superadmin/base.html` (the `<head>` and its inline `<style>` block, lines ~6–421)

**Interfaces:**
- Produces: the token names (`--c-*`, `--fs-*`, `--sp-*`, `--ff`, `--radius*`) and ALL existing `.sa-*` classes, now served from `superadmin.css`. Later tasks consume these.

- [ ] **Step 1: Copy the existing inline shell CSS into the new file verbatim.**

Open `templates/superadmin/base.html`, copy everything **between** `<style>` (line ~9) and `</style>` (line ~420) exactly as-is into a new file `static/css/superadmin.css`. Do not change any values yet — a verbatim copy guarantees identical rendering.

- [ ] **Step 2: Prepend the token block to `superadmin.css`.**

Add this at the very top of `static/css/superadmin.css`, above the copied rules:

```css
:root{
  /* Color — today's live palette, named (no new colors) */
  --c-bg:#FAFAF9;        --c-surface:#FFFFFF;
  --c-border:#E7E5E4;    --c-border-strong:#D6D3D1;   --c-hover:#F5F5F4;
  --c-text:#1C1917;      --c-text-muted:#78716C;      --c-text-faint:#A8A29E;
  --c-accent:#0F766E;    --c-accent-hover:#0D645D;    --c-accent-soft:rgba(15,118,110,.15);
  --c-ok-bg:#DCFCE7;  --c-ok-fg:#15803D;  --c-ok-bd:#BBF7D0;
  --c-warn-bg:#FEF3C7; --c-warn-fg:#B45309; --c-warn-bd:#FDE68A;
  --c-bad-bg:#FEE2E2; --c-bad-fg:#B91C1C; --c-bad-bd:#FCA5A5;

  /* Type scale — sizes already in use */
  --fs-display:28px; --fs-h1:20px; --fs-h2:15px; --fs-body:14px;
  --fs-sm:13px; --fs-xs:12px; --fs-label:11px; --fs-eyebrow:10px;
  --ff:'Inter',-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;

  /* Spacing — 4px base */
  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:20px; --sp-6:24px; --sp-8:32px;
  --radius:6px; --radius-lg:8px;
}
```

- [ ] **Step 3: Replace the inline `<style>` in base.html with a link.**

In `templates/superadmin/base.html`: ensure the very first template line is `{% load static %}` (add it above `<!DOCTYPE html>` if absent). Delete the entire `<style>…</style>` block (lines ~9–420) and in its place, inside `<head>`, add:

```html
<link rel="stylesheet" href="{% static 'css/superadmin.css' %}">
```

- [ ] **Step 4: Verify the shell renders identically.**

Run the dev server, log into Super Admin, open `/super-admin/dashboard/`.
```bash
python manage.py runserver
```
Expected: dashboard looks exactly as before (light bg, teal accents, sidebar intact). Confirm in browser devtools that `superadmin.css` loaded (200, not 404). If 404, run `python manage.py collectstatic --noinput` is NOT needed in dev (DEBUG serves from `STATICFILES_DIRS`) — recheck the `{% static %}` path.

- [ ] **Step 5: Verify scope isolation.**

Run: `grep -rln "superadmin.css" templates/`
Expected: exactly one line — `templates/superadmin/base.html`. No other template references it.

- [ ] **Step 6: Commit.**

```bash
git add static/css/superadmin.css templates/superadmin/base.html
git commit -m "refactor(superadmin): extract shell CSS to superadmin.css with design tokens"
```

---

## Task 2: Tokenize the migrated shell rules

Replace hardcoded hex/size values in `superadmin.css` with `var()` references. Purely mechanical; output must render identically.

**Files:**
- Modify: `static/css/superadmin.css`

- [ ] **Step 1: Swap color hex for tokens.**

In `static/css/superadmin.css`, replace each hardcoded value with its token (find/replace, case-insensitive on hex). Map:
`#FAFAF9`→`var(--c-bg)`, `#FFFFFF`→`var(--c-surface)`, `#E7E5E4`→`var(--c-border)`, `#D6D3D1`→`var(--c-border-strong)`, `#F5F5F4`→`var(--c-hover)`, `#1C1917`→`var(--c-text)`, `#78716C`→`var(--c-text-muted)`, `#A8A29E`→`var(--c-text-faint)`, `#0F766E`→`var(--c-accent)`, `#0D645D`→`var(--c-accent-hover)`, `#DCFCE7`→`var(--c-ok-bg)`, `#15803D`→`var(--c-ok-fg)`, `#BBF7D0`→`var(--c-ok-bd)`, `#FEF3C7`→`var(--c-warn-bg)`, `#B45309`→`var(--c-warn-fg)`, `#FDE68A`→`var(--c-warn-bd)`, `#FEE2E2`→`var(--c-bad-bg)`, `#B91C1C`→`var(--c-bad-fg)`, `#FCA5A5`→`var(--c-bad-bd)`.
Leave the values inside the `:root` block itself as literal hex. Leave one-off shades not in the token list (e.g. `#991717`, `#126631`, `#0D645D` hovers already mapped) as literal hex — do not invent tokens.

- [ ] **Step 2: Do NOT tokenize inside `:root`.**

Confirm the `:root{…}` declarations still hold literal hex (tokens must resolve to real colors). Only rules *below* `:root` use `var()`.

- [ ] **Step 3: Verify no color drift via grep.**

Run: `grep -nE "#0f172a|#334155|#2563eb|#1e293b|#e2e8f0|#64748b" static/css/superadmin.css`
Expected: no matches (those are the OLD dark palette and must never appear in the shared file).

- [ ] **Step 4: Verify render unchanged.**

Reload `/super-admin/dashboard/` and `/super-admin/bookings/`. Expected: identical appearance to Task 1.

- [ ] **Step 5: Commit.**

```bash
git add static/css/superadmin.css
git commit -m "refactor(superadmin): point shell rules at design tokens"
```

---

## Task 3: Add component classes

Add the reusable layout/component classes that later page conversions consume.

**Files:**
- Modify: `static/css/superadmin.css` (append at end)

**Interfaces:**
- Produces: `.sa-toolbar`, `.sa-filter`, `.sa-filter-label`, `.sa-actions`, `.sa-field`, `.sa-field-row`, `.sa-empty`. Consumed by Tasks 4–10.

- [ ] **Step 1: Append the component classes.**

Add to the end of `static/css/superadmin.css`:

```css
/* ---- Component classes (shared layout primitives) ---- */
.sa-toolbar{
  display:flex; align-items:flex-end; flex-wrap:wrap;
  gap:var(--sp-3); margin-bottom:var(--sp-4);
}
.sa-toolbar .sa-toolbar-end{ margin-left:auto; display:flex; gap:var(--sp-2); align-items:flex-end; }

.sa-filter{ display:flex; flex-direction:column; gap:var(--sp-1); min-width:160px; }
.sa-filter-label{
  font-size:var(--fs-label); font-weight:500; color:var(--c-text-muted);
  text-transform:uppercase; letter-spacing:.05em;
}
.sa-filter select, .sa-filter input{
  width:100%; background:var(--c-surface); border:1px solid var(--c-border);
  color:var(--c-text); font-family:var(--ff); font-size:var(--fs-sm);
  border-radius:var(--radius); padding:6px 10px; outline:none;
  transition:border-color .15s ease, box-shadow .15s ease;
}
.sa-filter select:focus, .sa-filter input:focus{
  border-color:var(--c-accent); box-shadow:0 0 0 2px var(--c-accent-soft);
}

.sa-actions{ display:flex; gap:var(--sp-2); align-items:center; flex-wrap:nowrap; }

.sa-field{ display:flex; flex-direction:column; gap:var(--sp-1); margin-bottom:var(--sp-3); }
.sa-field-row{ display:flex; gap:var(--sp-3); flex-wrap:wrap; }

.sa-empty{
  padding:var(--sp-8) var(--sp-4); text-align:center;
  color:var(--c-text-muted); font-size:var(--fs-sm);
}
```

- [ ] **Step 2: Verify no regression (classes are additive).**

Reload `/super-admin/dashboard/`. Expected: unchanged (no page uses these classes yet).

- [ ] **Step 3: Commit.**

```bash
git add static/css/superadmin.css
git commit -m "feat(superadmin): add shared toolbar/filter/actions/field component classes"
```

---

## Task 4: Purge the 8 dead dark-theme `<style>` blocks

Each of these pages has a `<style>` block that redefines `.sa-input`, `.sa-btn*`, `.sa-section-title`, etc. with the OLD dark palette, fighting the shell. Deleting them makes the page inherit the correct light theme from `superadmin.css`.

**Files:**
- Modify: `templates/superadmin/rooms.html`, `properties.html`, `guests.html`, `loyalty_config.html`, `tax_config.html`, `audit_log.html`, `room_images.html`, `event_images.html`

- [ ] **Step 1: Confirm the offenders.**

Run: `grep -l "#0f172a\|#334155\|#2563eb\|#1e293b" templates/superadmin/*.html`
Expected: the 8 files above (the dark hex confirms the block is the dead theme). If a file lists but has dark hex used for legitimate content (not a `.sa-*` redefinition), inspect before deleting.

- [ ] **Step 2: Delete each `<style>…</style>` block.**

For each of the 8 files, remove the entire `<style>…</style>` block (these redefine shell classes; the shell now owns them). Do NOT remove anything outside the `<style>` tags.

- [ ] **Step 3: Verify no dark CSS remains in templates.**

Run: `grep -rn "#0f172a\|#334155\|#2563eb\|#1e293b" templates/superadmin/`
Expected: no matches.

- [ ] **Step 4: Verify each page renders in the light theme.**

Reload `/super-admin/rooms/`, `/super-admin/properties/`, `/super-admin/guests/`, `/super-admin/loyalty-config/`, `/super-admin/tax-config/`, `/super-admin/audit-log/`. Expected: all light-themed, teal accents, inputs/buttons match the dashboard. No dark slate inputs anywhere.

- [ ] **Step 5: Commit.**

```bash
git add templates/superadmin/rooms.html templates/superadmin/properties.html templates/superadmin/guests.html templates/superadmin/loyalty_config.html templates/superadmin/tax_config.html templates/superadmin/audit_log.html templates/superadmin/room_images.html templates/superadmin/event_images.html
git commit -m "fix(superadmin): remove dead dark-theme style blocks that fought the light theme"
```

---

## Tasks 5–11: Inline `style="…"` → component classes (page by page)

**Conversion rules (apply to every page below):**
- A row of filters/search above a table/card → wrap in `<div class="sa-toolbar">`; each filter → `<label class="sa-filter"><span class="sa-filter-label">…</span><select>…</select></label>`; trailing primary action (e.g. "Add") → put in `<div class="sa-toolbar-end">`.
- A cluster of inline buttons in a table cell → wrap in `<div class="sa-actions">`; the buttons keep `.sa-btn` / `.sa-btn-sm` / `.sa-btn-danger`. Remove per-button inline margins.
- Form/modal fields with inline-spaced label+input → `<div class="sa-field"><label class="sa-label">…</label><input class="sa-input">…</div>`; group side-by-side fields in `<div class="sa-field-row">`.
- "No records" placeholders → `<div class="sa-empty">…</div>`.
- Replace ad-hoc inline spacing numbers with the spacing scale: `margin/padding` values map to the nearest `--sp-*` (4/8/12/16/20/24/32). When an inline style only sets spacing/layout that a component class now covers, delete the inline `style` attribute entirely.
- **Light/brand colors stay as-is** (or map to their matching `var()` token). Do not restyle elements that already use the light palette.
- **Dark-palette inline colors MUST be converted to light tokens** (decision 2026-06-30: these stray dark widgets — custom dropdowns, modals, image placeholders, empty-state text, status selects — currently render dark on the light panel and should match the rest of the panel). Apply this mapping, including colors set via JS `style.cssText` / `style.X` strings:

  | Dark value | Element role | → Light token |
  |-----------|--------------|---------------|
  | `#0f172a` | input / control / dropdown background | `var(--c-surface)` |
  | `#1e293b` | modal or dropdown-panel background | `var(--c-surface)` |
  | `#1e293b` | decorative / image-placeholder background | `var(--c-hover)` |
  | `#334155` | border | `var(--c-border)` |
  | `#64748b` | muted text | `var(--c-text-muted)` |
  | `#94a3b8` | faint text (e.g. "No Image") | `var(--c-text-faint)` |
  | `#e2e8f0`, `#f1f5f9`, `#f8fafc` | text on former-dark bg | `var(--c-text)` |
  | `#2563eb`, `#1d4ed8` | blue accent | `var(--c-accent)` / `var(--c-accent-hover)` |
  | `#064e3b` | success toast background | `var(--c-ok-bg)` |
  | `#6ee7b7` | success toast text | `var(--c-ok-fg)` |
  | `#450a0a`, `#7f1d1d` | error toast background | `var(--c-bad-bg)` |
  | `#fca5a5` | error toast text | `var(--c-bad-fg)` |

  (Status toasts in create/edit JS use dark bg + light text; the light theme inverts this — light tinted bg + dark text — via the `--c-ok-*`/`--c-bad-*` tokens.)

  For `#1e293b`, choose `--c-surface` vs `--c-hover` by the element's role (interactive panel/modal → surface; static decorative box → hover). After conversion, the page must contain NO dark-palette hex (`grep` for the dark set returns nothing for that page).

**Per-page verification (same for each task):** reload the page in the dev server; confirm (a) layout is tidy with consistent spacing, (b) colors unchanged, (c) all controls still present and functional. Then run `grep -c 'style="' templates/superadmin/<page>.html` and confirm the count dropped substantially.

### Task 5: `rooms.html` (41 inline styles — heaviest)

**Files:** Modify `templates/superadmin/rooms.html`

- [ ] **Step 1:** Apply the conversion rules above to `rooms.html`: filter/search row → `.sa-toolbar` + `.sa-filter`; per-row action buttons → `.sa-actions`; modal/add-room fields → `.sa-field`/`.sa-field-row`; empty states → `.sa-empty`.
- [ ] **Step 2:** Reload `/super-admin/rooms/`. Verify tidy layout, unchanged colors, all actions work (add, edit, delete, image links).
- [ ] **Step 3:** Run `grep -c 'style="' templates/superadmin/rooms.html`. Expected: well below 41 (only genuinely one-off inline styles remain).
- [ ] **Step 4:** Commit.
```bash
git add templates/superadmin/rooms.html
git commit -m "refactor(superadmin): convert rooms.html inline styles to component classes"
```

### Task 6: `employees.html` (32 inline styles)

**Files:** Modify `templates/superadmin/employees.html`

- [ ] **Step 1:** Apply conversion rules: filters → `.sa-toolbar`/`.sa-filter`; row action buttons → `.sa-actions`; add/edit employee modal fields → `.sa-field`/`.sa-field-row`.
- [ ] **Step 2:** Reload `/super-admin/employees/`. Verify layout, colors, and all actions (create, edit, activate/deactivate, assign property).
- [ ] **Step 3:** `grep -c 'style="' templates/superadmin/employees.html` — expect a large drop.
- [ ] **Step 4:** Commit (`refactor(superadmin): convert employees.html inline styles to component classes`).

### Task 7: `activities.html` (25) + `events.html` (22)

**Files:** Modify `templates/superadmin/activities.html`, `templates/superadmin/events.html`

- [ ] **Step 1:** Apply conversion rules to both files (toolbars, actions, fields, empty states).
- [ ] **Step 2:** Reload `/super-admin/activities/` and `/super-admin/events/`. Verify layout/colors/actions.
- [ ] **Step 3:** `grep -c 'style="'` on both — expect drops.
- [ ] **Step 4:** Commit (`refactor(superadmin): convert activities & events inline styles to component classes`).

### Task 8: `causes.html` (22) + `loyalty_config.html` (20)

**Files:** Modify `templates/superadmin/causes.html`, `templates/superadmin/loyalty_config.html`

- [ ] **Step 1:** Apply conversion rules to both.
- [ ] **Step 2:** Reload `/super-admin/causes/` and `/super-admin/loyalty-config/`. Verify layout/colors; confirm loyalty tier inputs and save still work.
- [ ] **Step 3:** `grep -c 'style="'` on both — expect drops.
- [ ] **Step 4:** Commit (`refactor(superadmin): convert causes & loyalty_config inline styles to component classes`).

### Task 9: `room_images.html` (16) + `event_images.html` (16)

**Files:** Modify `templates/superadmin/room_images.html`, `templates/superadmin/event_images.html`

- [ ] **Step 1:** Apply conversion rules (these are gallery/upload pages — focus on toolbar + field spacing + `.sa-empty`).
- [ ] **Step 2:** Reload both pages. Verify upload controls, thumbnails layout, delete actions; colors unchanged.
- [ ] **Step 3:** `grep -c 'style="'` on both — expect drops.
- [ ] **Step 4:** Commit (`refactor(superadmin): convert room_images & event_images inline styles to component classes`).

### Task 10: Remaining pages — `dashboard` (13), `bookings`, `guests`, `properties`, `analytics`, `tax_config`, `audit_log`, `room_status_board`

**Files:** Modify `templates/superadmin/dashboard.html`, `bookings.html`, `guests.html`, `properties.html`, `analytics.html`, `tax_config.html`, `audit_log.html`, `room_status_board.html`

- [ ] **Step 1:** Apply conversion rules to each. These are lighter; focus on filter toolbars (bookings/guests have status/property filters) and row action tidy. Leave `room_status_board.html`'s grid/overlay layout intact — only normalize spacing tokens, do not restructure the board.
- [ ] **Step 2:** Reload each page. Verify layout/colors/actions, especially bookings & guests filters (`.sa-filter`) and dashboard stat cards.
- [ ] **Step 3:** Run `for f in dashboard bookings guests properties analytics tax_config audit_log room_status_board; do echo "$f: $(grep -c 'style=\"' templates/superadmin/$f.html)"; done` — confirm reductions.
- [ ] **Step 4:** Commit (`refactor(superadmin): convert remaining page inline styles to component classes`).

---

## Task 11 (OPTIONAL): Drop `!important` from shared rules

Only do this if Tasks 4–10 verified clean (no page redefines shell classes). If any risk remains, skip — leaving `!important` is acceptable.

**Files:** Modify `static/css/superadmin.css`

- [ ] **Step 1:** Confirm no template still redefines `.sa-*`: `grep -rn "<style" templates/superadmin/` should show no block redefining shell classes (only genuinely page-local rules, if any).
- [ ] **Step 2:** Remove ` !important` from the rules in `superadmin.css`. Do this in small batches (e.g. buttons, then inputs, then tables), reloading after each.
- [ ] **Step 3:** Reload `/super-admin/dashboard/`, `/rooms/`, `/employees/`, `/bookings/`. Verify nothing visually regressed.
- [ ] **Step 4:** If any element breaks, restore `!important` only on that specific rule.
- [ ] **Step 5:** Commit (`refactor(superadmin): drop !important now that style conflicts are gone`).

---

## Task 12: Final consistency pass

**Files:** none (verification only) — fix-ups committed per page if needed.

- [ ] **Step 1:** Walk all 17 pages in the browser. Check: consistent label typography (11px uppercase), consistent card/section spacing, no cramped filters, no crowded action buttons, identical colors to baseline.
- [ ] **Step 2:** Run `grep -rn "#0f172a\|#334155\|#2563eb\|#1e293b\|#0f172a" templates/superadmin/ static/css/superadmin.css` — expect no matches (no dark palette anywhere).
- [ ] **Step 3:** Run `grep -rln "superadmin.css" templates/ static/css/style.css` — expect only `templates/superadmin/base.html` (scope isolation intact).
- [ ] **Step 4:** Confirm `git status` shows no changes to `templates/employeeadmin/`, `static/css/style.css`, or any non-superadmin file.
- [ ] **Step 5:** If any fix-ups were made, commit (`polish(superadmin): final spacing/typography consistency pass`).

---

## Self-Review notes

- **Spec coverage:** token layer (Task 1–2), component classes incl. filter dropdowns & inline-action tidy (Task 3), dead dark CSS purge (Task 4), all 17 pages converted (Tasks 5–10), optional `!important` removal (Task 11), final verification (Task 12). All spec sections mapped.
- **Scope:** Super Admin only; every task names exact `templates/superadmin/*` or `static/css/superadmin.css` paths; Task 12 step 4 guards against leakage.
- **No color change:** tokens are verbatim existing hex; conversion rules forbid introducing colors; grep checks for the dark palette.
- **Adaptation note:** TDD's red/green is replaced by grep + render verification, appropriate for a CSS/template refactor with no logic.
