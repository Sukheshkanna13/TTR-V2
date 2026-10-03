# Super Admin Panel — UI/UX Redesign (Design Spec)

**Date:** 2026-06-29
**Scope:** Super Admin panel ONLY (`templates/superadmin/`, 17 pages + shell)
**Out of scope (do NOT touch):** Employee Admin (`.ea-*`), public site (`tt-*` / `static/css/style.css`), Django admin, any colors (palette stays identical)
**Approach:** A — shared token layer + purge conflicts + component classes (keep the existing shell)

---

## Problem

The Super Admin panel feels unprofessional and congested. Code-only audit found the mechanical causes:

1. **Dead dark-theme `<style>` blocks fighting the live light theme.** 8 pages (rooms, properties, guests, loyalty_config, tax_config, audit_log, room_images, event_images) carry leftover CSS that *redefines* core classes with an old dark palette — e.g. `rooms.html` sets `.sa-input{background:#0f172a;…}` and `.sa-btn-primary{background:#2563eb;}` while the live theme is light (`#FAFAF9` / teal `#0F766E`). This directly contradicts "keep colors the same."
2. **`!important` specificity war.** Because of those conflicts, `base.html` overrides nearly every rule with `!important` (~150). Not a design system — brute force.
3. **Ad-hoc inline `style="…"` attributes** — 41 in rooms, 32 in employees, 25 in activities, 22 in events/causes, 20 in loyalty_config, etc. Source of the random padding / whitespace / inconsistent text formatting.
4. **No shared scale.** Colors, font sizes, and spacing are hardcoded and repeated, so typography drifts page to page (labels are 10px on some pages, 11px on others, with/without uppercase).

The correct colors already exist in `base.html`. The noise comes from the leftover ones. Fixing this means naming the good values as tokens, deleting the dead CSS, and replacing inline spacing with reusable classes.

---

## Solution overview

- New stylesheet **`static/css/superadmin.css`**, linked ONLY from `templates/superadmin/base.html`. Scoped so it cannot affect Employee Admin, the public site, or Django admin.
- It holds: design tokens (CSS variables), the migrated base-shell styles, and a small set of component classes.
- The 8 dead dark-theme `<style>` blocks are deleted.
- Heavy inline `style="…"` clusters are converted to component classes.
- After conflicts are gone, `!important` is dropped from the shared rules.
- All 17 pages must render with an **identical color appearance** to today (verified by running the app).

---

## 1. Token layer (`:root` in `superadmin.css`)

Every value is extracted from the existing light theme — no new colors.

```css
:root{
  /* Color — today's live palette, named */
  --c-bg:#FAFAF9;        --c-surface:#FFFFFF;
  --c-border:#E7E5E4;    --c-border-strong:#D6D3D1;   --c-hover:#F5F5F4;
  --c-text:#1C1917;      --c-text-muted:#78716C;      --c-text-faint:#A8A29E;
  --c-accent:#0F766E;    --c-accent-hover:#0D645D;    --c-accent-soft:rgba(15,118,110,.15);
  --c-ok-bg:#DCFCE7;  --c-ok-fg:#15803D;  --c-ok-bd:#BBF7D0;
  --c-warn-bg:#FEF3C7; --c-warn-fg:#B45309; --c-warn-bd:#FDE68A;
  --c-bad-bg:#FEE2E2; --c-bad-fg:#B91C1C; --c-bad-bd:#FCA5A5;

  /* Type scale — sizes already in use, consolidated */
  --fs-display:28px; --fs-h1:20px; --fs-h2:15px; --fs-body:14px;
  --fs-sm:13px; --fs-xs:12px; --fs-label:11px; --fs-eyebrow:10px;
  --ff:'Inter',-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;

  /* Spacing — 4px base, replaces ad-hoc inline numbers */
  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:20px; --sp-6:24px; --sp-8:32px;
  --radius:6px; --radius-lg:8px;
}
```

**Typography drift fix:** all labels/eyebrows standardize on `--fs-label` (11px, uppercase, letter-spacing `.05em`, weight 500). Section titles → `--fs-h2`, page titles → `--fs-h1`, stat values → `--fs-display`.

## 2. Component classes

Defined in `superadmin.css`, these absorb the repeated inline spacing:

| Class | Purpose | Replaces |
|-------|---------|----------|
| `.sa-toolbar` | Flex row above tables/cards: filters left, actions right. `gap:var(--sp-3)`, `margin-bottom:var(--sp-4)`, wraps on small screens. | Scattered inline-spaced filter/button rows |
| `.sa-filter` | Wrapper for a `<select>`/search filter: uppercase label above, roomy control, `min-width:160px`, teal focus ring (`--c-accent-soft`). | Cramped bare `<select>` filters |
| `.sa-actions` | Row-level action container: keeps inline Edit/View/Delete buttons, consistent gap + sizing, no crowding. | 3–4 inline buttons crowding a cell |
| `.sa-field` / `.sa-field-row` | Form field + label spacing for modals/forms. | Hand-spaced modal fields |
| `.sa-empty` | Standard empty-state block (icon + muted text), consistent padding. | Ad-hoc "no records" markup |

Existing well-formed classes (`.sa-card`, `.sa-btn*`, `.sa-stat*`, `.sa-badge*`, `.sa-input`, `.sa-label`, table styles) are **kept** — only migrated into `superadmin.css` and re-pointed at `var()` tokens.

## 3. Filter dropdowns & row actions

**In-page filter dropdowns.** Each `<select>`/search filter is wrapped in `.sa-filter`: small uppercase label, control with `--c-border` / teal focus ring, `min-width:160px` so option text isn't truncated. All filters for a page sit in one `.sa-toolbar` row instead of being scattered, removing congestion.

**Row actions stay inline.** Per-row Edit / View / Delete buttons remain inline in the table (no `⋮` dropdown — no interaction change). `.sa-actions` gives them consistent gap, sizing, and alignment so they stop crowding the cell. Destructive (Delete) uses `.sa-btn-danger` / `--c-bad-fg`.

> Both reuse only existing colors and the new spacing/type tokens.

## 4. The 17 Super Admin pages

Shell: `base.html`. Content pages: `dashboard`, `bookings`, `room_status_board`, `guests`, `employees`, `analytics`, `properties`, `rooms`, `tax_config`, `loyalty_config`, `causes`, `events`, `activities`, `event_images`, `room_images`, `audit_log`.

**Pages with dead dark-theme `<style>` to DELETE (8):** rooms, properties, guests, loyalty_config, tax_config, audit_log, room_images, event_images.

**Inline `style="…"` conversion priority (heaviest first):** rooms (41) → employees (32) → activities (25) → events (22) → causes (22) → loyalty_config (20) → room_images (16) → event_images (16) → dashboard (13) → remaining pages.

---

## Rollout (ordered)

1. **Foundation.** Create `static/css/superadmin.css` with the token layer. Move `base.html`'s inline `<style>` into it verbatim, then swap hardcoded hex/sizes for `var()` tokens. Link `superadmin.css` in `base.html` only. Verify the shell renders identically.
2. **Purge conflicts.** Delete the 8 dead dark-theme `<style>` blocks. Verify those pages now inherit the correct light theme.
3. **Component classes.** Add `.sa-toolbar`, `.sa-filter`, `.sa-actions`, `.sa-field*`, `.sa-empty` to `superadmin.css`.
4. **Per-page conversion.** Page by page (priority order above), replace inline `style="…"` clusters with component classes; apply the filter-dropdown pattern and `.sa-actions` inline-button tidy where tables/filters exist.
5. **Drop `!important` (OPTIONAL final step).** Only after every page verifies clean (no page redefines base classes). If any risk remains, skip — leaving `!important` in is acceptable.
6. **Final pass.** Walk all 17 pages, confirm consistent spacing/typography and **identical colors** to today.

## Verification

- Code-based (no screenshots): tokens reuse the exact existing hex values, so colors are unchanged by construction. Spot-check by grepping that no stray non-token hex remains in the migrated rules.
- Confirm `superadmin.css` is referenced ONLY by `templates/superadmin/base.html` (grep) — no leakage to Employee Admin, public site, or Django admin.
- No new JS dependencies.

## Non-goals

- No color/palette changes.
- No Employee Admin, public site, or Django admin changes.
- No sidebar nav restructure (stays a flat grouped list).
- No backend/view/logic changes — templates and CSS only.
