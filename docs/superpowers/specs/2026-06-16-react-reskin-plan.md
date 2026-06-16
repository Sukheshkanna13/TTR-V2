# Re-skin Django to the approved React UI — plan

**Date:** 2026-06-16
**Decision:** Adopt the approved React **design only**. The Django booking engine
(search → 10-min hold → Razorpay → accounts → loyalty → admin) stays the core. We
copy the UI/layout, not the React app's external-OTA booking model.
**Reference:** `src-reference/` (approved app). Authoritative CSS = `src-reference/styles.css`.

## Hard rule
Re-skin is **presentation only**. Never change a form field `name`, URL, CSRF hook,
or JS fetch the Django backend depends on. Every re-skinned page keeps its existing
functional wiring; only markup/classes/structure change to match the React screen.

## Source → target map
| React screen (`src-reference`) | Django target | Wiring kept |
|---|---|---|
| `home.jsx` | `templates/pages/index.html` | search form → `/rooms/search/page/`; cards → property/search |
| `search.jsx` SearchScreen | `templates/rooms/search.html` | search API (JS card builder) |
| `search.jsx` PropertyScreen | room/property detail page | hold/checkout entry |
| `account.jsx` LoyaltyScreen | `templates/pages/folio.html` + loyalty | our loyalty data |
| `account.jsx` ThingsScreen | Things-to-do page | static/CMS |
| `account.jsx` CauseScreen | `templates/pages/cause.html` | static/CMS |
| `retreat.jsx` | Nature Retreat page | static |
| `events.jsx` | Events page | static/CMS |
| `shell.jsx` (nav/footer/utility/FAB) | `templates/base.html` | auth-aware nav kept |

**Nav mapping** (approved): Stays → `/rooms/search/`, Things to do, Nature Retreat,
Travel for Cause, Events, + WhatsApp. We additionally keep our **guest login/account**
entry (utility bar) since Django has real auth — styled to match, not in the React app.

## Interactions to port (React → vanilla JS in Django)
- Full-bleed hero + **sticky search pill** + **scroll-fading floating title** (home)
- **Property image carousel** (arrows + dots + touch swipe + rubber-band)
- **Moments carousel** (drag + momentum + infinite loop + auto-scroll)
- Mobile **hamburger menu** / bottom-sheet
- Split-fill **star rating** (data ready: `Property.rating`/`rating_pct`)

## Phases (each ends with browser verify: React vs Django screenshots)
- **Phase 0 — Groundwork (this turn):** adopt `src-reference/styles.css` → `static/css/style.css`
  (replaces my earlier doc-port append); copy `public/images` + logos → `static/images`.
- **Phase 1 — Global shell:** rebuild `base.html` from `shell.jsx` (utility bar, navbar,
  footer, WhatsApp FAB, mobile menu JS), Django-URL + auth aware. Affects every page.
- **Phase 2 — Home:** rebuild `index.html` from `home.jsx` + the hero/carousel/moments JS.
- **Phase 3 — Search + property detail:** match `search.jsx`, keep the search API wiring;
  add star rating to result cards (extend `RoomSerializer` + JS card builder).
- **Phase 4 — Secondary pages:** loyalty/folio, things, retreat, events, cause.
- **Phase 5 — Auth + checkout re-skin:** login/register/folio/checkout to match, logic intact.

## Assets
`src-reference/public/images` (82 files, ~70MB, real client photos) → `static/images/`.
Logos (`TTR-Logo.png`, `logo-half.png`, `logo-left.png`, `nature-retreat-Logo.png`) → `static/images/`.
Property image folders (`1F-1BHK`, `2F-1BHK`, `1F-2BHK`, `Auroville`) map to our Room/Property images later.

## Out of scope
External OTA `bookingUrl` links from `data.js` (we book in Django). Admin panels
(separate dark theme). The unused `booking.jsx` React component.
