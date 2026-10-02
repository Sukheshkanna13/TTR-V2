# Design: Real, Editable Stays Search

**Date:** 2026-06-17
**Branch:** fix/superadmin-employee-management
**Status:** Approved — ready for implementation plan

---

## Problem

The guest-facing booking flow has **no real search inputs anywhere**. Every "search"
control is a static `<a>` link with hardcoded text:

- `base.html` lines 50-65 — `tt-nav-pill-inline` near the logo (home only). Not editable.
- `index.html` line 16 — `tt-nav-search-pill` floating hero pill. Also a link, carries
  server-default dates (`hero.check_in_iso`).
- `search.html` filter sidebar — has Destination, Guests, price, type, sort, but
  **no check-in/check-out date fields at all**.

`grep` confirms zero `type="date"` / datepicker / calendar in any guest-facing template.
Dates only enter the system as URL params pre-filled by the server.

**The break:** landing on the stays page without dates shows *"Dates required. Please go
back and enter check-in and check-out dates"* (`search.html` lines 242-250) — but there is
**nowhere on the page to enter dates**. Dead end.

The backend `SearchRoomsView` (`rooms/views.py` line 96) already accepts `check_in`,
`check_out`, `city`/`property_id`, `guests`, `min_price`, `max_price`, `room_type`, `sort`.
The API is ready; only the UI to feed it is missing.

---

## Goals

1. Remove the redundant search pill near the logo (Task 1).
2. Make the stays page a real, editable search hub: Where + Check-in + Check-out, wired
   to the live search API and integrated with the existing filters (Task 2).
3. Eliminate the "dates required" dead-end.

## Non-goals

- No backend / URL / search-API contract changes.
- No changes to the home hero, room-detail, hold, or checkout flows.
- No new JS dependency (no calendar library).

---

## Decisions (from brainstorming)

| Decision | Choice |
|----------|--------|
| Search placement | Keep home hero pill as entry point → redirects to stays. Stays page is the functional search hub. |
| Redundant nav pill | Remove `tt-nav-pill-inline` from `base.html`. |
| "Where" control | Reuse the existing `property_id` `<select>` (populated from `properties`). Not a free-text city box. |
| Date picker | Native HTML `type="date"` inputs (consistent with admin pages; no new dependency). |
| Refetch behavior | Live refetch on change, debounced ~350ms. Dates only fire a fetch when both are present and valid. |
| Empty-state default | When landing on stays with no dates, pre-fill tomorrow → day-after so results render immediately. |

---

## Implementation scope

Two files only — templates + client JS. Low blast radius.

### 1. `templates/base.html` — nav cleanup
- Remove the `{% if url_name == 'home' %} ... tt-nav-pill-inline ... {% endif %}` block
  (lines 50-65). The logo `tt-nav-left-group` keeps only the logo link.

### 2. `templates/rooms/search.html` — search hub
Add to the existing `#filterForm`, placed **above** Destination so the panel reads like a
real search (Where → Check-in → Check-out → Guests → price → type → sort):

- **Where** — reuse existing `property_id` `<select>` (relabel/reorder, no new markup needed
  beyond moving it).
- **Check-in** — `<input type="date" id="check_in" name="check_in">`
- **Check-out** — `<input type="date" id="check_out" name="check_out">`

Client JS (extends existing `searchParams` / `runSearch()` logic in the same file):

- On load, initialize date inputs from URL params (`check_in`/`check_out`). If absent,
  pre-fill tomorrow → day-after.
- Live, debounced (~350ms) refetch on any field change.
- Date validation in JS: check-in `min` = today; check-out `min` = check-in + 1 day; if
  check-out ≤ check-in, auto-bump check-out to check-in + 1 day. Never fire an invalid request.
- A fetch is only triggered for date changes once both dates are present and valid.
- Keep the existing "Dates required" error path as a safety net (now effectively unreachable).

---

## Data flow (after change)

```
Home hero pill ──(check_in, check_out, guests, city defaults)──▶ /rooms/search/page/
                                                                        │
                          ┌─────────────────────────────────────────────┘
                          ▼
   search.html: date inputs + property select + filters initialise from URL params
                          │  (any change, debounced 350ms, dates valid)
                          ▼
   POST /rooms/search/  ──▶ SearchRoomsView._handle_search ──▶ JSON room list
                          ▼
   results rendered client-side (existing renderResults logic)
```

No new endpoints. `SearchRoomsView` already supports the full parameter set.

---

## Testing

- **Manual / browser:** land on stays with no params → date inputs pre-filled, results show.
  Edit dates → results refetch. Set checkout ≤ checkin → auto-corrected. Change destination/
  guests → refetch. Arrive from home hero with params → inputs reflect them.
- **Regression:** home hero pill still redirects correctly; room-detail and checkout flows
  unchanged (carry `check_in`/`check_out`/`guests` as before).
- No backend tests needed (no backend change); existing `SearchRoomsView` tests still cover
  the API contract.

---

## Risk

Low. Scoped to two templates and client JS. The search API and all downstream flows are
untouched. The main correctness surface is the JS date validation + debounce, verified by
manual browser testing.
