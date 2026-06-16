# Temple And Towns Resorts — UI/UX Design System Blueprint

> **Purpose:** Complete reference for rebuilding this exact UI over Django.  
> **Source (v2 — `ui-revisions`):** Extracted from the production Vite build — `src/styles.css` (3,300+ lines) and all components in `src/components/`. This supersedes the older `test/` build, which lags behind.  
> **Stack to rebuild on:** Django + plain CSS (no Tailwind) — replicate every class 1:1.

> **⚠️ v2 design changes vs the original doc — read these first:**
> - **Accent is now `#5161CB` (brand blue from logo)** — was `#4a4ce0` electric indigo. Deep `#3f4da3`, soft `#eef0fa`.
> - **Everything is fully squared — `--pill`, `--r-sm`, `--r-md`, `--r-lg` are all `0px`.** There are no rounded corners anywhere except intentionally circular elements (`border-radius: 50%` on avatars, slider arrows, status dots, WhatsApp dots/FAB).
> - **Property cards use a swipeable image carousel** (`.tt-slider-*`), not a single static image.
> - **New components:** `StarRating` (split-fill stars), JS-driven Moments carousel, fixed hero float overlay, Nature Retreat page, Events page.

---

## Implementation Status (Django build)

> Living tracker — update as the spec is applied to `static/css/style.css` and `templates/`.

**✅ Phase 1 — Foundation (applied 2026-06-16):** `static/css/style.css` `:root` now
matches v2 — accent `#5161CB` / deep `#3f4da3` / soft `#eef0fa`, all radius tokens
(`--pill`, `--r-sm`, `--r-md`, `--r-lg`) = `0`, Inter-only import (dropped Instrument
Serif), and `.tt-italic-soft` = SF/Inter weight-500 (no serif). Because the customer
templates reference these tokens, the whole site is re-themed at once. Inline px radii
across customer pages (`pages/`, `accounts/`, `bookings/`) were squared too; only
intentional `border-radius: 50%` circles remain.

**⏳ Phase 2+ — Net-new v2 components (not yet built):** an audit of `style.css` vs
templates found the existing customer pages already define/use all their `tt-*` classes
(the Phase 1 token change re-themed them cleanly). The genuinely missing pieces are the
v2 *additions*, none of which exist in `style.css` or templates yet:
> - `.tt-star*` — split-fill star rating (§9.10a)
> - `.tt-slider*` — property image carousel (§9.10b / §9.11)
> - `.tt-msb*` — mobile search bar (§9.7)
> - `.tt-sheet*` — bottom sheet (§9.8)
> - hero float overlay (§9.5/§9.6), `.tt-moments*` JS carousel (§9.12)
>
> These are net-new construction (CSS + markup + JS + in some cases model data such as a
> room/property `rating`) and should be built page-by-page with visual review.

**Scope note:** admin panels (`templates/superadmin/`, `templates/employeeadmin/`) use a
separate dark operational theme and are intentionally **out of scope** for this editorial
design system.

---

## Table of Contents

1. [Design Philosophy](#1-design-philosophy)
2. [CSS Design Tokens](#2-css-design-tokens)
3. [Typography System](#3-typography-system)
4. [Spacing & Layout](#4-spacing--layout)
5. [Shadows, Radius & Easing](#5-shadows-radius--easing)
6. [Animations & Keyframes](#6-animations--keyframes)
7. [Icon System](#7-icon-system)
8. [Image System](#8-image-system)
9. [Component Library](#9-component-library)
   - [Utility Bar](#91-utility-bar)
   - [Navbar](#92-navbar)
   - [Buttons](#93-buttons)
   - [Tags & Chips](#94-tags--chips)
   - [Hero — Desktop](#95-hero--desktop)
   - [Hero — Mobile (Marriott-style)](#96-hero--mobile-marriott-style)
   - [Mobile Search Bar (.tt-msb)](#97-mobile-search-bar-tt-msb)
   - [Bottom Sheet](#98-bottom-sheet)
   - [Category Scroll Tabs](#99-category-scroll-tabs)
   - [Property Card](#910-property-card)
   - [Star Rating (split-fill)](#910a-star-rating-split-fill)
   - [Property Image Carousel](#910b-property-image-carousel)
   - [Desktop Search Bar](#911-desktop-search-bar)
   - [Moments Carousel (JS-driven)](#912-moments-carousel-v2--js-driven-draggable)
   - [Dark Editorial Section](#913-dark-editorial-section)
   - [How It Works Grid](#914-how-it-works-grid)
   - [Forms & Inputs](#915-forms--inputs)
   - [Stepper (Booking Wizard)](#916-stepper-booking-wizard)
   - [Status Badges](#917-status-badges)
   - [Room Card](#918-room-card)
   - [Summary Sidebar Card](#919-summary-sidebar-card)
   - [Modal](#920-modal)
   - [Progress Bar (Loyalty)](#921-progress-bar-loyalty)
   - [Success / Confirmation Screen](#922-success--confirmation-screen)
   - [Footer](#923-footer)
   - [WhatsApp FAB](#924-whatsapp-fab)
   - [Nature Retreat — Experience Rows](#925-nature-retreat--experience-rows)
   - [Events Page](#926-events-page)
10. [Responsive Breakpoints](#10-responsive-breakpoints)
11. [Page Layouts](#11-page-layouts)
12. [Data Model](#12-data-model)
13. [Django Rebuild Notes](#13-django-rebuild-notes)

---

## 1. Design Philosophy

- **Editorial/minimalist** — 75% Marriott Bonvoy reference (white, navy, generous whitespace, image-led) + 25% legacy brand
- **No Tailwind** — pure CSS custom properties as design tokens
- **Font:** Inter from Google Fonts — weights 400 / 500 / 600 / 700
- **Colors:** White background, dark navy ink (`#0a1628`), brand-blue accent (`#5161CB`)
- **Corners:** **Fully squared — `border-radius: 0` everywhere.** Every radius token (`--pill`, `--r-sm`, `--r-md`, `--r-lg`) resolves to `0px`. The only curves left are deliberate circles (`50%`): slider arrows, status dots, success mark, WhatsApp dot/FAB.
- **Motion:** Two easing curves only: `--ease` (standard) and `--ease-spring` (spring/overshoot)
- **Mobile:** Marriott Bonvoy-style — 90vh full-bleed hero, bottom sheet search, fixed scroll-fade hero overlay, swipeable property carousels
- **Primary CTA channel:** WhatsApp (`#25d366`) for all booking and support

---

## 2. CSS Design Tokens

Paste this `:root` block at the top of every CSS file.

```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
  /* Backgrounds */
  --bg:          #ffffff;
  --bg-soft:     #f7f7f6;
  --bg-tint:     #f1f2f0;
  --surface:     #ffffff;

  /* Text */
  --ink:         #0a1628;   /* dark navy — primary text, nav */
  --ink-2:       #1a2536;
  --text:        #0a1628;
  --text-soft:   #4a5468;   /* secondary body text */
  --text-muted:  #7a8290;   /* labels, captions */
  --text-faint:  #9aa1ad;

  /* Borders */
  --line:        #e6e7e3;   /* default hairline */
  --line-strong: #c9cbc4;   /* stronger border */

  /* Accent — brand blue from logo */
  --accent:      #5161CB;
  --accent-deep: #3f4da3;
  --accent-soft: #eef0fa;   /* tinted bg for chips/badges */

  /* Brand */
  --whatsapp:    #25d366;

  /* Border Radius — FULLY SQUARED OFF (all 0) */
  --pill:        0px;       /* used everywhere as "pill" — resolves to a square corner */
  --r-sm:        0px;
  --r-md:        0px;
  --r-lg:        0px;

  /* Easing */
  --ease:        cubic-bezier(0.25, 0.1, 0.25, 1);
  --ease-spring: cubic-bezier(0.22, 1, 0.36, 1);

  /* Shadows */
  --shadow-sm:   0 1px 2px rgba(10, 22, 40, 0.04);
  --shadow-md:   0 6px 24px -8px rgba(10, 22, 40, 0.10);
  --shadow-lg:   0 24px 60px -20px rgba(10, 22, 40, 0.18);
}

/* Base reset */
* { box-sizing: border-box; }

html, body {
  margin: 0; padding: 0;
  background: var(--bg);
  color: var(--text);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 16px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

a { color: inherit; text-decoration: none; }

button {
  font-family: inherit;
  cursor: pointer;
  border: none;
  background: none;
  color: inherit;
  padding: 0;
}

input, select, textarea {
  font-family: inherit;
  font-size: inherit;
  color: inherit;
}

img { display: block; max-width: 100%; }
```

---

## 3. Typography System

```css
/* Hero display — large page titles */
.tt-display {
  font-weight: 700;
  letter-spacing: -0.035em;
  line-height: 1.0;
  font-size: clamp(28px, 3.2vw, 48px);
  color: var(--ink);
}

/* H1 — main hero headline */
.tt-h1 {
  font-weight: 700;
  letter-spacing: -0.025em;
  line-height: 1.05;
  font-size: clamp(40px, 5vw, 72px);
  color: var(--ink);
}

/* H2 — section headings */
.tt-h2 {
  font-weight: 600;
  letter-spacing: -0.018em;
  line-height: 1.15;
  font-size: clamp(28px, 3vw, 40px);
  color: var(--ink);
}

/* H3 — card titles, sidebar headings */
.tt-h3 {
  font-weight: 600;
  letter-spacing: -0.01em;
  font-size: 22px;
  color: var(--ink);
}

/* Eyebrow — uppercase section labels */
.tt-eyebrow {
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--text-soft);
  font-weight: 500;
}

/* Sub-headline / lead text */
.tt-sub {
  font-size: clamp(17px, 1.4vw, 21px);
  color: var(--text-soft);
  font-weight: 400;
  line-height: 1.55;
}

/* Soft italic (for accent words in hero) */
.tt-italic-soft {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Inter", sans-serif;
  font-weight: 500;
  font-size: 0.92em;
  letter-spacing: -0.020em;
}

/* Utility color classes */
.tt-muted { color: var(--text-muted); }
.tt-soft  { color: var(--text-soft); }
```

**Mobile type overrides (≤768px):**
```css
@media (max-width: 768px) {
  .tt-display { font-size: 28px; line-height: 1.08; }
  .tt-h1      { font-size: 28px; line-height: 1.12; }
  .tt-h2      { font-size: 22px; }
  .tt-h3      { font-size: 18px; }
  .tt-sub     { font-size: 16px; }
}
```

---

## 4. Spacing & Layout

### Page container

```css
/* Max-width wrapper — use inside every section */
.tt-page {
  max-width: 1440px;
  margin: 0 auto;
  padding: 0 56px;       /* desktop */
}

@media (max-width: 1200px) {
  .tt-page { padding: 0 32px; }
}

@media (max-width: 768px) {
  .tt-page { padding: 0 16px; }
}
```

### Section spacing

```css
.tt-section    { padding: 96px 0; }
.tt-section-sm { padding: 56px 0; }
```

### Grid utilities

```css
.tt-grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 24px; }
.tt-grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }
.tt-grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 24px; }
.tt-flex   { display: flex; }
.tt-stack  { display: flex; flex-direction: column; }
```

### Gap utilities

```css
.tt-gap-4  { gap: 4px;  }
.tt-gap-8  { gap: 8px;  }
.tt-gap-12 { gap: 12px; }
.tt-gap-16 { gap: 16px; }
.tt-gap-24 { gap: 24px; }
.tt-gap-32 { gap: 32px; }
```

### Margin-top utilities

```css
.tt-mt-8  { margin-top: 8px;  }
.tt-mt-16 { margin-top: 16px; }
.tt-mt-24 { margin-top: 24px; }
.tt-mt-32 { margin-top: 32px; }
.tt-mt-48 { margin-top: 48px; }
.tt-mt-64 { margin-top: 64px; }
```

### Divider

```css
.tt-hr {
  height: 1px;
  background: var(--line);
  border: none;
  margin: 28px 0;
}
```

---

## 5. Shadows, Radius & Easing

| Token | Value | Usage |
|-------|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(10,22,40,0.04)` | cards at rest |
| `--shadow-md` | `0 6px 24px -8px rgba(10,22,40,0.10)` | elevated cards |
| `--shadow-lg` | `0 24px 60px -20px rgba(10,22,40,0.18)` | modals, bottom sheet |
| `--pill` / `--r-sm` / `--r-md` / `--r-lg` | `0px` | **all radius tokens = 0** — fully squared UI |
| `border-radius: 50%` | circle | slider arrows, status dots, success mark, WhatsApp dot/FAB — the only curves left |
| `.tt-msb` (mobile search bar) | `10px` literal | one deliberate exception — the mobile hero search bar keeps a soft radius |
| `--ease` | `cubic-bezier(0.25, 0.1, 0.25, 1)` | standard transitions |
| `--ease-spring` | `cubic-bezier(0.22, 1, 0.36, 1)` | hover lifts, sheet slide-up |

---

## 6. Animations & Keyframes

```css
/* Used on bottom sheet backdrop */
@keyframes tt-backdrop-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

/* Used on bottom sheet slide-up */
@keyframes tt-sheet-up {
  from { transform: translateY(100%); }
  to   { transform: translateY(0); }
}

/* Modal fade-in */
@keyframes fadein {
  from { opacity: 0; }
  to   { opacity: 1; }
}

/* Modal content rise */
@keyframes rise {
  from { opacity: 0; transform: translateY(16px) scale(0.98); }
  to   { opacity: 1; transform: none; }
}

/* Success check circle pop */
@keyframes pop {
  0%   { transform: scale(0); opacity: 0; }
  60%  { transform: scale(1.08); opacity: 1; }
  100% { transform: scale(1); }
}

/* Pending status dot pulse */
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.45; transform: scale(0.85); }
}

/* Loader spin */
@keyframes tt-spin {
  to { transform: rotate(360deg); }
}
```

---

## 7. Icon System

All icons are inline SVG — 1.5–1.6px stroke, `strokeLinecap: round`, `strokeLinejoin: round`.  
In Django, implement as a template tag or include partial.

```css
.tt-ico    { width: 16px; height: 16px; flex-shrink: 0; }
.tt-ico-lg { width: 22px; height: 22px; }
```

### Icon catalogue

| Name | SVG path summary | Use |
|------|-----------------|-----|
| `search` | circle + diagonal line | search inputs |
| `pin` | teardrop + inner circle | location fields |
| `cal` | rectangle + lines + tick marks | date inputs |
| `user` | circle head + path body | guest/account |
| `arrow` | horizontal line + right chevron | CTAs |
| `arrowL` | left arrow | back buttons |
| `check` | checkmark path | done states |
| `x` | × cross | close/dismiss |
| `star` | filled 5-point star | ratings |
| `wifi` | concentric arcs | amenity |
| `spark` | 8-ray sun | highlights |
| `shield` + check | shield outline | security |
| `gift` | gift box | loyalty |
| `lock` | padlock | auth |
| `bed` | headboard + pillow circle | room type |
| `users` | double user silhouette | guests |
| `sun` | circle + rays | amenity |
| `menu` | three horizontal lines | hamburger |
| `wa` | WhatsApp logo (filled) | all CTA buttons |
| `phone` | phone handset | support |

### Django template tag example

```html
{# In your Django template — replace with SVG include or custom template tag #}
{% load tt_icons %}
{% tt_icon "search" size=16 class="tt-ico" %}
```

---

## 8. Image System

### Lazy-loading placeholder pattern

```css
/* Wrapper maintains aspect ratio and shows striped fallback */
.tt-img {
  position: relative;
  width: 100%;
  height: 100%;
  border-radius: inherit;
  overflow: hidden;
  background: var(--bg-tint);
}

/* Animated diagonal stripe placeholder — shown until image loads */
.tt-img-stripes {
  position: absolute;
  inset: 0;
  background-image: repeating-linear-gradient(
    135deg,
    var(--tone, oklch(0.9 0.04 230)) 0 18px,
    oklch(from var(--tone, oklch(0.9 0.04 230)) calc(l - 0.04) c h) 18px 36px
  );
  transition: opacity .5s ease;
}

.tt-img-stripes::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(255,255,255,0) 50%, rgba(0,0,0,0.18) 100%);
}
```

### HTML pattern

```html
<!-- Property card image -->
<div class="tt-card-media">
  <div class="tt-img" style="aspect-ratio: 4/3">
    <div class="tt-img-stripes" style="--tone: oklch(0.88 0.05 210); opacity: 1"></div>
    <img src="{{ property.cover }}" alt="{{ property.name }}"
         loading="lazy"
         style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:0;z-index:1"
         onload="this.style.opacity=1;this.previousElementSibling.style.opacity=0" />
  </div>
</div>
```

### Unsplash fallback (React only — swap for real images in Django)

```js
// Pattern: https://images.unsplash.com/{photo-id}?auto=format&fit=crop&w=1000&q=72
const unsplashUrl = (id, w = 1000) =>
  `https://images.unsplash.com/${id}?auto=format&fit=crop&w=${w}&q=72`;
```

---

## 9. Component Library

### 9.1 Utility Bar

Thin strip above the navbar — phone/WhatsApp CTA left, navigation links right.

```css
.tt-utility {
  border-bottom: 1px solid var(--line);
  background: #fff;
  font-size: 14px;
  color: var(--text-soft);
}

.tt-utility-inner {
  max-width: 1440px;
  margin: 0 auto;
  padding: 16px 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.tt-utility a:hover { color: var(--ink); }

.tt-utility-left  { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
.tt-utility-right { display: flex; align-items: center; gap: 28px; }

/* WhatsApp green circle icon */
.tt-wa-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px; height: 28px;
  border-radius: 50%;
  background: var(--whatsapp);
  color: #fff;
}
```

```html
<!-- Django template -->
<div class="tt-utility">
  <div class="tt-utility-inner">
    <div class="tt-utility-left">
      <span class="tt-utility-support">Reservations &amp; support</span>
      <a href="{{ WA_URL }}" target="_blank" rel="noopener noreferrer"
         style="display:inline-flex;align-items:center;gap:8px;font-weight:500">
        <span class="tt-wa-dot">{% tt_icon "wa" size=14 %}</span>
        +91-0000000000
      </a>
    </div>
    <div class="tt-utility-right">
      <a href="{% url 'search' %}">Trip Planner</a>
      <a href="{% url 'retreat' %}">Nature Retreat</a>
    </div>
  </div>
</div>
```

**Mobile:** `.tt-utility-support` and `.tt-utility-right` are hidden at ≤768px.

---

### 9.2 Navbar

Sticky nav with frosted glass background, split logo (logomark + wordmark), desktop links, hamburger for mobile.

```css
.tt-nav {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--line);
}

.tt-nav-inner {
  max-width: 1440px;
  margin: 0 auto;
  padding: 22px 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

/* Split logo — logomark + wordmark side by side, tightly kerned */
.tt-logo-split {
  display: inline-flex;
  align-items: center;
  gap: 4px;          /* tight kerning so the two halves read as one mark */
  cursor: pointer;
  vertical-align: middle;
}

.tt-logo-left-img {            /* logo-left.png — the logomark */
  height: 52px;
  width: auto;
  object-fit: contain;
  mix-blend-mode: multiply;
  transition: transform 0.25s var(--ease);
}

.tt-logo-half-img {            /* logo-half.png — the wordmark */
  height: 52px;
  width: auto;
  object-fit: contain;
  mix-blend-mode: multiply;
  transition: transform 0.25s var(--ease);
}

.tt-logo-split:hover .tt-logo-left-img { transform: scale(1.03); }
.tt-logo-split:hover .tt-logo-half-img { transform: scale(1.01); }

/* Nav links */
.tt-nav-links {
  display: flex;
  gap: 40px;
  align-items: center;
}

.tt-nav-link {
  font-size: 16px;
  color: var(--ink);
  cursor: pointer;
  position: relative;
  padding: 4px 0;
  font-weight: 400;
  transition: color .2s var(--ease);
}

.tt-nav-link:hover { color: var(--accent); }
.tt-nav-link.active { color: var(--accent); }

/* Active underline indicator */
.tt-nav-link.active::after {
  content: '';
  position: absolute;
  left: 0; right: 0;
  bottom: -8px;
  height: 1.5px;
  background: var(--accent);
}

/* Book Now pill in nav — green WhatsApp button */
.tt-nav-wa-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  background: var(--whatsapp);
  color: #fff;
  border-radius: var(--pill);
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
  white-space: nowrap;
  transition: opacity .2s;
}

.tt-nav-wa-btn:hover { opacity: 0.88; color: #fff; }

/* Hamburger — hidden on desktop */
.tt-hamburger {
  display: none;
  align-items: center;
  justify-content: center;
  width: 38px; height: 38px;
  background: transparent;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-sm);
  color: var(--ink);
  cursor: pointer;
  transition: background .18s;
  flex-shrink: 0;
}

.tt-hamburger:hover { background: var(--bg-soft); }

/* Mobile menu (dropdown below nav) */
.tt-mobile-menu {
  border-top: 1px solid var(--line);
  background: #fff;
  padding: 8px 16px 20px;
  display: flex;
  flex-direction: column;
}

.tt-mobile-link {
  display: block;
  padding: 14px 4px;
  font-size: 16px;
  font-weight: 500;
  color: var(--ink);
  cursor: pointer;
  border-bottom: 1px solid var(--line);
  transition: color .18s;
}

.tt-mobile-link:hover { color: var(--accent); }

.tt-mobile-wa {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-top: 16px;
  padding: 14px 20px;
  background: var(--whatsapp);
  color: #fff;
  border-radius: var(--pill);
  font-size: 15px;
  font-weight: 600;
  justify-content: center;
}

/* Mobile show/hide */
@media (max-width: 768px) {
  .tt-nav-links  { display: none; }
  .tt-hamburger  { display: inline-flex; }
  .tt-logo-img   { height: 54px; }
  .tt-logo-left-img { height: 38px; }
  .tt-logo-half-img { height: 38px; }
  .tt-logo-split { gap: 3px; }
  .tt-logo-home-mobile { display: none !important; }  /* hide wordmark on mobile home hero */
}
```

**Nav links:** Stays · Things to do · Nature Retreat · Travel for Cause · Events

---

### 9.3 Buttons

```css
/* Base button */
.tt-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 14px 26px;
  border-radius: var(--pill);
  font-size: 15px;
  font-weight: 500;
  border: 1px solid transparent;
  transition: background .25s var(--ease), color .25s var(--ease),
              border-color .25s var(--ease), transform .15s var(--ease);
  white-space: nowrap;
  letter-spacing: -0.005em;
}

.tt-btn:active { transform: scale(0.985); }
.tt-btn[disabled] { opacity: 0.4; pointer-events: none; }

/* Primary — navy fill, hover to accent indigo */
.tt-btn-primary {
  background: var(--ink);
  color: #fff;
  border-color: var(--ink);
}
.tt-btn-primary:hover {
  background: var(--accent);
  border-color: var(--accent);
}

/* Ghost — transparent, muted border */
.tt-btn-ghost {
  background: transparent;
  color: var(--ink);
  border: 1px solid var(--line-strong);
}
.tt-btn-ghost:hover { border-color: var(--ink); }

/* Outline — transparent, ink border, fills on hover */
.tt-btn-outline {
  background: transparent;
  color: var(--ink);
  border: 1px solid var(--ink);
}
.tt-btn-outline:hover { background: var(--ink); color: #fff; }

/* Link style — underline only */
.tt-btn-link {
  padding: 0;
  background: transparent;
  color: var(--ink);
  border-bottom: 1px solid currentColor;
  border-radius: 0;
  padding-bottom: 2px;
}
.tt-btn-link:hover { color: var(--accent); }

/* Sizes */
.tt-btn-sm { padding: 10px 18px; font-size: 13px; }
.tt-btn-lg { padding: 18px 34px; font-size: 16px; }

/* Card CTA (inline compact) */
.tt-btn-card-cta {
  background: var(--ink);
  color: #fff;
  border: none;
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 600;
  border-radius: var(--pill);
  cursor: pointer;
  transition: background 0.2s ease, transform 0.1s ease;
  white-space: nowrap;
}
.tt-btn-card-cta:hover  { background: var(--accent); }
.tt-btn-card-cta:active { transform: scale(0.97); }
```

---

### 9.4 Tags & Chips

```css
/* Overlay tag (glass) */
.tt-tag {
  display: inline-flex;
  align-items: center;
  background: rgba(255,255,255,0.92);
  color: var(--ink);
  font-size: 13px;
  padding: 8px 14px;
  border-radius: var(--pill);
  letter-spacing: -0.005em;
  backdrop-filter: blur(6px);
}
.tt-tag-dark    { background: var(--ink); color: #fff; }
.tt-tag-outline { background: transparent; border: 1px solid var(--line-strong); color: var(--ink); }

/* Filter chips */
.tt-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: var(--pill);
  background: transparent;
  border: 1px solid var(--line-strong);
  font-size: 13px;
  color: var(--ink);
  cursor: pointer;
  transition: all .2s var(--ease);
}
.tt-chip:hover        { border-color: var(--ink); }
.tt-chip-active       { background: var(--ink); color: #fff; border-color: var(--ink); }
.tt-chip-tonal        { background: var(--bg-soft); border-color: transparent; }
.tt-chip-blue         { background: var(--accent-soft); color: var(--accent-deep); border-color: transparent; }
```

---

### 9.5 Hero — Desktop

Two-column grid: left = headline + CTAs, right = featured image card.

```css
.tt-hero {
  position: relative;
  padding: 56px 0 80px;
}

.tt-hero-grid {
  display: grid;
  grid-template-columns: 1.1fr 1fr;
  gap: 64px;
  align-items: start;
}

/* Featured image card on the right */
.tt-featured-card {
  position: relative;
  aspect-ratio: 5/4;
  border-radius: var(--r-sm);
  overflow: hidden;
}

/* Overlay gradient on featured card */
/* linear-gradient(180deg, rgba(10,22,40,0.35) 0%, rgba(10,22,40,0.05) 40%, rgba(10,22,40,0.55) 100%) */

/* Corner label and meta */
.tt-featured-label {
  position: absolute; top: 24px; left: 24px;
  font-size: 14px; color: rgba(255,255,255,0.92);
  font-weight: 500; z-index: 3;
}
.tt-featured-meta {
  position: absolute; top: 24px; right: 24px;
  font-size: 12px; color: rgba(255,255,255,0.75);
  letter-spacing: 0.06em; text-transform: uppercase; z-index: 3;
}

/* 2x2 grid of property tiles overlaid at bottom */
.tt-featured-tags {
  position: absolute; inset: 0;
  padding: 60px 24px 24px;
  display: grid; grid-template-columns: 1fr 1fr;
  gap: 14px; align-content: end; z-index: 3;
}

.tt-featured-tile {
  background: rgba(255,255,255,0.96);
  padding: 16px 20px;
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: transform .35s var(--ease-spring), background .25s var(--ease);
}
.tt-featured-tile:hover {
  transform: translateY(-2px);
  background: #fff;
}
.tt-featured-tile .lbl  { font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }
.tt-featured-tile .name { font-size: 17px; font-weight: 600; color: var(--ink); letter-spacing: -0.01em; }

/* Social proof pills at bottom of card */
.tt-featured-stats {
  position: absolute; bottom: 24px; left: 24px; right: 24px;
  display: flex; gap: 12px; z-index: 3; pointer-events: none;
}
.tt-featured-stat {
  background: rgba(255,255,255,0.92);
  padding: 8px 14px; border-radius: var(--pill);
  font-size: 13px; display: inline-flex; align-items: center; gap: 6px; color: var(--ink);
}
.tt-featured-stat b { font-weight: 600; }
```

**Django HTML:**

```html
<section class="tt-section-sm tt-hero-section">
  <div class="tt-hero-desktop-wrap">
    <div class="tt-page">
      <div class="tt-hero-grid" style="align-items:center">
        <div>
          <span class="tt-eyebrow">Temple And Towns Resorts</span>
          <h1 class="tt-display" style="margin-top:16px">
            Explore stays that feel <span class="tt-italic-soft" style="color:var(--accent)">modern,</span><br>
            calm, and unmistakably Indian.
          </h1>
          <p class="tt-sub" style="margin-top:28px;max-width:560px">
            A hand-picked collection of stays across temple towns and quiet coastlines.
          </p>
          <div style="display:flex;gap:14px;margin-top:36px">
            <a href="{% url 'search' %}" class="tt-btn tt-btn-primary">
              Find a stay {% tt_icon "arrow" size=14 %}
            </a>
            <a href="{{ WA_URL }}" target="_blank"
               style="display:inline-flex;align-items:center;gap:8px;padding:14px 26px;
                      background:var(--whatsapp);color:#fff;border-radius:var(--pill);
                      font-size:15px;font-weight:500">
              {% tt_icon "wa" size=15 %} Chat with us
            </a>
          </div>
        </div>
        <div class="tt-featured-card" style="height:280px;aspect-ratio:unset">
          <img src="{% static 'images/hero_resort.png' %}" alt="" style="width:100%;height:100%;object-fit:cover">
          {# gradient overlay, featured tiles go here #}
        </div>
      </div>
    </div>
  </div>
</section>
```

---

### 9.6 Hero — Mobile (Marriott-style)

Full-bleed 90vh hero, dark scrim, search bar pinned to top, headline pinned to bottom.  
Desktop elements are hidden via `.tt-hero-desktop-wrap { display: none !important }` on ≤768px.

```css
/* src/styles.css — mobile @media blocks (v2 has no separate mobile-overrides.css) */

/* Hide mobile elements on desktop */
.tt-hero-overlay,
.tt-hero-mobile-top,
.tt-hero-mobile-bottom,
.tt-hero-float-overlay { display: none; }

@media (max-width: 768px) {

  /* Full-bleed container */
  .tt-hero-section {
    position: relative;
    height: 90vh;
    overflow: hidden;
    padding: 0 !important;
  }

  /* Cover image */
  .tt-hero-bg-img {
    position: absolute; inset: 0;
    width: 100%; height: 100%;
    object-fit: cover;
    object-position: center top;
    z-index: 0;
  }

  /* Dark overlay scrim */
  .tt-hero-overlay {
    display: block;
    position: absolute; inset: 0;
    background: rgba(0,0,0,0.42);
    z-index: 1;
    pointer-events: none;
  }

  /* Hide desktop content */
  .tt-hero-desktop-wrap { display: none !important; }

  /* Search bar — pinned top */
  .tt-hero-mobile-top {
    display: block;
    position: absolute;
    top: 20px; left: 16px; right: 16px;
    z-index: 2;
  }

  /* Headline + CTA — pinned bottom */
  .tt-hero-mobile-bottom {
    display: block;
    position: absolute;
    bottom: 36px; left: 0; right: 0;
    text-align: center;
    padding: 0 24px;
    z-index: 2;
  }

  .tt-hero-eyebrow-mobile {
    color: rgba(255,255,255,0.65);
    font-size: 11px;
    letter-spacing: 0.12em;
    display: block;
    margin-bottom: 8px;
  }

  .tt-hero-title-mobile {
    color: #fff !important;
    font-size: 22px !important;
    line-height: 1.15 !important;
    margin-bottom: 0 !important;
  }

  .tt-hero-cta-mobile {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin-top: 20px;
    padding: 14px 28px;
    background: #0a1628;
    color: #fff;
    border: none;
    border-radius: var(--pill);
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    letter-spacing: -0.01em;
    transition: background 0.18s;
    -webkit-tap-highlight-color: transparent;
  }
  .tt-hero-cta-mobile:active { background: #1a2e4a; }

}
```

**v2 Floating hero overlay (`.tt-hero-float-overlay`):** The mobile hero headline + CTA now live in a **fixed, viewport-anchored overlay** pinned to the bottom of the screen (not the hero element). It has its own bottom-up dark gradient so the white text stays legible over any background, and fades out on scroll via JS. Positioned purely by viewport dimensions — independent of hero/nav heights.

```css
.tt-hero-float-overlay {
  position: fixed;
  bottom: 0; left: 0; right: 0;
  z-index: 50;
  display: flex; flex-direction: column;
  align-items: center; justify-content: flex-end;
  padding: 0 32px 64px;
  text-align: center;
  background: linear-gradient(to top,
      rgba(0,0,0,0.55) 0%,
      rgba(0,0,0,0.35) 40%,
      rgba(0,0,0,0.08) 75%,
      transparent 100%);
  transition: opacity 0.12s ease-out;
  will-change: opacity;
}

.tt-hero-float-title {
  color: #fff !important;
  margin: 0 0 28px;
  max-width: 680px;
  font-size: 40px;
  line-height: 1.12;
  text-shadow: 0 2px 8px rgba(0,0,0,0.35), 0 0 20px rgba(0,0,0,0.15);
}
```

**Scroll-fade logic (JS/Django):**

```html
<script>
  // Fade out the fixed hero overlay as the user scrolls past the hero
  window.addEventListener('scroll', function() {
    const alpha = Math.max(0, 1 - window.scrollY / 160);
    const floatEl = document.querySelector('.tt-hero-float-overlay');
    if (floatEl) floatEl.style.opacity = alpha;
  }, { passive: true });
</script>
```

---

### 9.7 Mobile Search Bar (.tt-msb)

Two-field tap-to-open bar: Destination | Dates. Tapping opens the bottom sheet.

```css
.tt-msb {
  display: flex;
  align-items: center;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 6px 28px rgba(0,0,0,0.22);
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.14s, box-shadow 0.2s;
  -webkit-tap-highlight-color: transparent;
  user-select: none;
}
.tt-msb:active { transform: scale(0.975); box-shadow: 0 3px 14px rgba(0,0,0,0.16); }

.tt-msb-field {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  min-width: 0;
}

.tt-msb-ico { flex-shrink: 0; color: var(--text-soft); display: flex; }

.tt-msb-text {
  display: flex; flex-direction: column; gap: 2px;
  min-width: 0; overflow: hidden;
}

.tt-msb-lbl {
  font-size: 10px; font-weight: 600;
  letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--text-muted); white-space: nowrap;
}

.tt-msb-val {
  font-size: 14px; font-weight: 500;
  color: var(--ink);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* Vertical separator between fields */
.tt-msb-sep {
  width: 1px; height: 38px;
  background: var(--line);
  flex-shrink: 0;
}
```

```html
<!-- Only shown inside .tt-hero-mobile-top -->
<div class="tt-msb" id="msbTrigger" role="button" tabindex="0">
  <div class="tt-msb-field">
    {% tt_icon "pin" size=18 class="tt-msb-ico" %}
    <div class="tt-msb-text">
      <span class="tt-msb-lbl">Destination</span>
      <span class="tt-msb-val">Where next?</span>
    </div>
  </div>
  <div class="tt-msb-sep"></div>
  <div class="tt-msb-field">
    {% tt_icon "cal" size=18 class="tt-msb-ico" %}
    <div class="tt-msb-text">
      <span class="tt-msb-lbl">Dates</span>
      <span class="tt-msb-val">Add dates</span>
    </div>
  </div>
</div>
```

---

### 9.8 Bottom Sheet

Slides up from bottom. Rendered as a portal to `<body>` in React. In Django, use a fixed `<div>` toggled with JS.

```css
.tt-sheet-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.32);
  z-index: 200;
  animation: tt-backdrop-in 0.22s ease forwards;
}

.tt-bottom-sheet {
  position: fixed; bottom: 0; left: 0; right: 0;
  background: #fff;
  border-radius: 20px 20px 0 0;
  padding: 0 20px calc(28px + env(safe-area-inset-bottom, 0px));
  z-index: 201;
  animation: tt-sheet-up 0.3s cubic-bezier(0.22, 1, 0.36, 1) forwards;
  max-height: 88vh;
  overflow-y: auto;
}

.tt-sheet-drag-wrap {
  display: flex; justify-content: center; padding: 10px 0 18px;
}
.tt-sheet-drag-bar {
  width: 36px; height: 4px;
  background: var(--line-strong);
  border-radius: 99px;
}

.tt-sheet-field {
  display: flex; flex-direction: column; gap: 5px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-sm);
  padding: 12px 16px;
  margin-bottom: 12px;
  transition: border-color 0.18s;
}
.tt-sheet-field:focus-within { border-color: var(--ink); }

.tt-sheet-field .lbl {
  font-size: 11px; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--text-muted);
}

.tt-sheet-field select,
.tt-sheet-field input[type="date"] {
  border: none; background: transparent; outline: none;
  font-size: 15px; font-weight: 500; color: var(--ink);
  padding: 0; width: 100%;
  -webkit-appearance: none; appearance: none;
  font-family: inherit;
}
```

```html
<!-- Shown/hidden by JS toggle on .tt-sheet-backdrop and .tt-bottom-sheet -->
<div class="tt-sheet-backdrop" id="sheetBackdrop" onclick="closeSheet()"></div>
<div class="tt-bottom-sheet" id="bottomSheet">
  <div class="tt-sheet-drag-wrap"><div class="tt-sheet-drag-bar"></div></div>
  <h3 style="margin:0 0 20px;font-size:20px;font-weight:600">Plan your stay</h3>

  <div class="tt-sheet-field">
    <span class="lbl">Where</span>
    <select name="city">
      <option>Pondicherry</option>
      <option>Near Auroville</option>
      <option>Both cities</option>
    </select>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
    <div class="tt-sheet-field">
      <span class="lbl">Check in</span>
      <input type="date" name="check_in">
    </div>
    <div class="tt-sheet-field">
      <span class="lbl">Check out</span>
      <input type="date" name="check_out">
    </div>
  </div>

  <div class="tt-sheet-field">
    <span class="lbl">Guests</span>
    <select name="guests">
      <option>1 guest · 1 room</option>
      <option>2 guests · 1 room</option>
      <option>3 guests · 1 room</option>
      <option>4 guests · 2 rooms</option>
    </select>
  </div>

  <button class="tt-btn tt-btn-primary" style="width:100%;margin-top:8px;padding:16px;justify-content:center">
    {% tt_icon "search" size=15 %} Search stays
  </button>
</div>
```

---

### 9.9 Category Scroll Tabs

Horizontally scrolling pill chips for filtering properties by theme.

```css
.tt-category-tabs-section {
  background: var(--bg);
  border-bottom: 1px solid var(--line);
}

.tt-category-tabs {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
  padding: 16px 0;
}
.tt-category-tabs::-webkit-scrollbar { display: none; }

/* Pill chip — note: these use border-radius 9999px — NOT var(--pill) */
.tt-tab-chip {
  display: inline-flex;
  align-items: center;
  white-space: nowrap;
  flex-shrink: 0;
  padding: 8px 20px;
  border-radius: 9999px;
  border: 1px solid var(--line-strong);
  background: #fff;
  color: var(--ink);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.16s, color 0.16s, border-color 0.16s, transform 0.12s;
  -webkit-tap-highlight-color: transparent;
  letter-spacing: -0.005em;
}
.tt-tab-chip:hover         { border-color: var(--ink); }
.tt-tab-chip:active        { transform: scale(0.95); }
.tt-tab-chip-active        { background: var(--ink); color: #fff; border-color: var(--ink); }
```

**Tabs data:**

```python
THEMES = [
    {'key': 'all',      'label': 'All stays'},
    {'key': 'temple',   'label': 'Temple stays'},
    {'key': 'town',     'label': 'Town escapes'},
    {'key': 'nature',   'label': 'Nature retreats'},
    {'key': 'auroville','label': 'Auroville'},
]
```

```html
<div class="tt-category-tabs-section">
  <div class="tt-page">
    <div class="tt-category-tabs">
      {% for theme in themes %}
        <button class="tt-tab-chip {% if active_theme == theme.key %}tt-tab-chip-active{% endif %}"
                hx-get="{% url 'search' %}?theme={{ theme.key }}"
                hx-target="#property-grid"
                hx-push-url="true">
          {{ theme.label }}
        </button>
      {% endfor %}
    </div>
  </div>
</div>
```

---

### 9.10 Property Card

Image-led card. Hover lifts with `translateY(-3px)` + image scale.

> **v2:** On the homepage "Featured stays" the card media is now a **swipeable image carousel** (`PropertyCarousel`), not a single image — see [9.10b Property Image Carousel](#910b-property-image-carousel). The card itself, body, and meta are unchanged. The card body row now puts the **Book now** CTA inline on the same row as the name (`align-items: center`), with `.tt-card-area` below.

```css
.tt-card {
  background: var(--surface);
  border-radius: var(--r-sm);
  overflow: hidden;
  cursor: pointer;
  transition: transform .35s var(--ease-spring);
  display: flex;
  flex-direction: column;
}
.tt-card:hover { transform: translateY(-3px); }

/* Media wrapper — 4:3 desktop, 16:9 mobile */
.tt-card-media {
  position: relative;
  aspect-ratio: 4 / 3;
  border-radius: var(--r-sm);
  overflow: hidden;
}

/* Image zoom on hover */
.tt-card-media .tt-img > img  { transition: transform .8s var(--ease-spring); }
.tt-card:hover .tt-card-media .tt-img > img { transform: scale(1.04); }

/* Tag overlay (city/theme) */
.tt-card-tags {
  position: absolute; top: 14px; left: 14px; right: 14px;
  display: flex; justify-content: space-between; z-index: 3;
}

.tt-card-body {
  padding: 18px 4px 8px;
  display: flex; flex-direction: column; gap: 4px;
}

.tt-card-row {
  display: flex; justify-content: space-between;
  align-items: baseline; gap: 12px;
}

.tt-card-name  { font-weight: 600; font-size: 19px; letter-spacing: -0.015em; color: var(--ink); }
.tt-card-area  { font-size: 14px; color: var(--text-muted); }
.tt-card-blurb { font-size: 14px; color: var(--text-soft); line-height: 1.55; margin-top: 8px; }

.tt-card-meta {
  display: flex; justify-content: space-between;
  align-items: center; margin-top: 14px;
}

.tt-card-price       { font-weight: 600; font-size: 18px; color: var(--ink); }
.tt-card-price small { font-weight: 400; color: var(--text-muted); font-size: 13px; }

/* Mobile overrides */
@media (max-width: 768px) {
  .tt-card-media { aspect-ratio: 16 / 9 !important; }
  .tt-card-body  { padding: 12px 2px 8px !important; }
  .tt-card-blurb { display: none; }   /* hide blurb on mobile */
  .tt-card-name  { font-size: 16px; }
}

/* Disable hover lift on touch devices */
@media (hover: none) {
  .tt-card:hover { transform: none !important; }
}
```

```html
<!-- Property grid -->
<div class="tt-grid-3" id="property-grid">
  {% for property in properties %}
  <div class="tt-card" onclick="window.location='{% url 'property' property.id %}'">
    <div class="tt-card-media">
      <div class="tt-img">
        <div class="tt-img-stripes" style="--tone: oklch(0.88 0.05 210)"></div>
        <img src="{{ property.cover }}" alt="{{ property.name }}" loading="lazy">
      </div>
      <div class="tt-card-tags">
        <span class="tt-tag">{{ property.city_display }}</span>
        <span class="tt-tag">★ {{ property.rating }}</span>
      </div>
    </div>
    <div class="tt-card-body">
      <div class="tt-card-row">
        <span class="tt-card-name">{{ property.name }}</span>
      </div>
      <span class="tt-card-area">{{ property.area }}</span>
      <p class="tt-card-blurb">{{ property.blurb }}</p>
      <div class="tt-card-meta">
        <span class="tt-card-price">{{ property.from }} <small>/ night</small></span>
        <button class="tt-btn-card-cta">Book now</button>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
```

---

### 9.10a Star Rating (split-fill)

Renders 5 stars with a partial fill clipped to `rating/5` width, plus the numeric rating. Used in search results and property detail. In React it's `StarRating`; in Django render two stacked star rows and clip the top one.

```css
/* No dedicated CSS class — built with inline styles + the `star` icon.
   Structure: a muted base row of 5 stars, an ink-colored fill row
   absolutely positioned on top, clipped to a percentage width. */
```

```html
<!-- rating = 4.6 → fill width = 92% -->
<span class="tt-stars" style="position:relative;display:inline-flex;align-items:center;
      color:var(--line-strong);gap:2px">
  <span style="display:flex;gap:2px">
    {% for _ in "12345" %}{% tt_icon "star" size=13 %}{% endfor %}
  </span>
  <span style="position:absolute;top:0;left:0;display:flex;gap:2px;overflow:hidden;
        width:{{ rating_pct }}%;color:var(--ink)">
    {% for _ in "12345" %}{% tt_icon "star" size=13 %}{% endfor %}
  </span>
  <span style="color:var(--ink);font-weight:600;margin-left:6px">{{ rating }}</span>
</span>
```

```python
# in the view / template tag:  rating_pct = rating / 5 * 100
```

---

### 9.10b Property Image Carousel

The homepage "Featured stays" card media is a horizontal slider: a flex track of full-width images translated by `idx * 100%`, with prev/next arrow buttons, pagination dots, and (on mobile) touch-swipe with a rubber-band edge effect. Desktop reveals the arrows on card hover; mobile shows them always.

```css
/* Track — slides horizontally, spring easing */
.tt-slider-track {
  display: flex;
  height: 100%;
  transition: transform 0.6s var(--ease-spring);
}
.tt-slider-img {
  width: 100%; height: 100%;
  object-fit: cover;
  flex-shrink: 0;
}

/* Arrow buttons — circular, hidden until card hover on desktop */
.tt-slider-btn {
  position: absolute; top: 50%;
  transform: translateY(-50%);
  width: 36px; height: 36px;
  background: rgba(255,255,255,0.9);
  color: var(--ink);
  border-radius: 50%;          /* deliberate circle */
  display: flex; align-items: center; justify-content: center;
  z-index: 4; opacity: 0;
  transition: opacity 0.3s, transform 0.3s;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}
.tt-card:hover .tt-slider-btn { opacity: 1; }
.tt-slider-btn.prev { left: 12px; }
.tt-slider-btn.next { right: 12px; }
.tt-slider-btn:active { transform: translateY(-50%) scale(0.9); }

/* Pagination dots — active dot stretches into a bar */
.tt-slider-dots {
  position: absolute; bottom: 16px; left: 0; right: 0;
  display: flex; justify-content: center; gap: 6px; z-index: 4;
}
.tt-dot {
  width: 6px; height: 6px;
  background: rgba(255,255,255,0.5);
  border-radius: 50%;
  transition: all 0.3s;
}
.tt-dot.active { background: #fff; width: 14px; border-radius: 0; }  /* stretches to a bar */

/* Mobile — arrows always visible, smaller, dark glass */
@media (max-width: 768px) {
  .tt-slider-btn {
    display: flex !important; opacity: 1 !important;
    width: 28px; height: 28px;
    background: rgba(0,0,0,0.45);
    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
    color: #fff;
    box-shadow: 0 2px 8px rgba(0,0,0,0.18);
    border: 1px solid rgba(255,255,255,0.15);
  }
  .tt-slider-btn.prev { left: 6px; }
  .tt-slider-btn.next { right: 6px; }
  .tt-slider-btn svg  { width: 10px; height: 10px; }
  .tt-slider-dots { gap: 4px; bottom: 10px; max-width: 80%; overflow: hidden; }
  .tt-dot { width: 5px; height: 5px; flex-shrink: 0; }
  .tt-dot.active { width: 12px; background: #fff; }
}
```

```html
<!-- Inside .tt-card-media — replaces the single <img> -->
<div class="tt-card-media">
  <div class="tt-slider-track" data-idx="0">
    {% for img in property.images %}
      <img src="{{ img }}" alt="{{ property.name }}" class="tt-slider-img" loading="lazy">
    {% endfor %}
  </div>
  <button class="tt-slider-btn prev">{% tt_icon "arrowL" size=14 %}</button>
  <button class="tt-slider-btn next">{% tt_icon "arrow" size=14 %}</button>
  <div class="tt-slider-dots">
    {% for img in property.images %}
      <div class="tt-dot {% if forloop.first %}active{% endif %}"></div>
    {% endfor %}
  </div>
  <div class="tt-card-tags">
    <span class="tt-tag">{{ property.city_display }}</span>
    <span class="tt-tag tt-tag-dark">★ {{ property.rating }}</span>
  </div>
</div>
```

**Slider JS (vanilla):** track each card's index; `translateX(-idx*100%)`; bind arrow clicks (`stopPropagation` so they don't trigger the card's navigate-to-detail); on mobile bind `touchstart/move/end` with a 50px swipe threshold and dampen drag to `0.3×` at the first/last image for a rubber-band feel.

---

### 9.11 Desktop Search Bar

5-column grid: Location | Check-in | Check-out | Guests | Search button.

```css
.tt-search {
  margin-top: 16px;
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr 0.9fr auto;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-sm);
  background: #fff;
  overflow: hidden;
}

.tt-search-cell {
  padding: 18px 24px;
  border-right: 1px solid var(--line);
  display: flex; flex-direction: column; justify-content: center;
  min-width: 0;
}
.tt-search-cell:first-child { padding-left: 56px; }
.tt-search-cell:last-of-type { border-right: none; }

.tt-search-cell .lbl {
  font-size: 11px; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--text-muted); margin-bottom: 6px;
}
.tt-search-cell .val { font-size: 15px; font-weight: 500; color: var(--ink); }

.tt-search-cell input,
.tt-search-cell select {
  border: none; background: transparent; outline: none; padding: 0;
  font-size: 15px; font-weight: 500; color: var(--ink); width: 100%;
}

.tt-search-go {
  padding: 0 32px;
  background: var(--ink); color: #fff;
  display: flex; align-items: center; gap: 10px;
  font-weight: 500;
  transition: background .25s var(--ease);
  cursor: pointer;
}
.tt-search-go:hover { background: var(--accent); }

/* Collapse to 2-col at 1200px */
@media (max-width: 1200px) {
  .tt-search { grid-template-columns: 1fr 1fr; }
  .tt-search-go { grid-column: span 2; padding: 18px; justify-content: center; }
}
```

---

### 9.12 Moments Carousel (v2 — JS-driven, draggable)

The static 3-column grid was replaced by a horizontal, infinitely-scrolling carousel of 280×350 tiles. It auto-scrolls, pauses on hover, supports drag/touch scrubbing, and has soft mask-faded edges. The legacy `.tt-moment*` grid classes still exist but are no longer used on the homepage.

```css
/* Scroll container — hidden scrollbar + soft edge fade */
.tt-moments-carousel-container {
  width: 100%;
  overflow-x: scroll; overflow-y: hidden;
  position: relative;
  padding: 10px 0;
  scrollbar-width: none;          /* Firefox */
  -ms-overflow-style: none;       /* IE/Edge */
  mask-image: linear-gradient(to right, transparent, #000 6%, #000 94%, transparent);
  -webkit-mask-image: linear-gradient(to right, transparent, #000 6%, #000 94%, transparent);
}
.tt-moments-carousel-container::-webkit-scrollbar { display: none; }  /* Chrome/Safari */

/* JS-driven track — plain flex, scrubbed via scrollLeft (no CSS animation) */
.tt-moments-carousel-track-js {
  display: flex;
  gap: 20px;
  width: max-content;
  padding: 0 20px;
}

/* Legacy CSS-marquee track (kept for backward compat, unused on home) */
.tt-moments-carousel-track {
  display: flex; width: max-content;
  animation: tt-marquee 40s linear infinite;
}
.tt-moments-carousel-track:hover { animation-play-state: paused; }
@keyframes tt-marquee {
  0%   { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}

.tt-moments-carousel-item {
  width: 280px; height: 350px;
  position: relative;
  border-radius: 0;
  overflow: hidden; cursor: pointer;
  flex-shrink: 0;
  background: var(--bg-tint);
}
.tt-moments-carousel-item img {
  width: 100%; height: 100%;
  object-fit: cover; display: block;
  transition: transform .6s var(--ease-spring);
  pointer-events: none;            /* prevent image drag ghost */
}
.tt-moments-carousel-item:hover img { transform: scale(1.04); }

/* Mobile — smaller tiles, faster legacy marquee */
@media (max-width: 768px) {
  .tt-moments-carousel-item  { width: 200px; height: 250px; }
  .tt-moments-carousel-track { animation-duration: 25s; }
}
```

**Carousel JS:** render the moment tiles twice (a duplicated group) so the loop is seamless; on each animation frame nudge `container.scrollLeft += speed` and wrap when past the first group's width; pause the auto-advance on `pointerenter`; on `pointerdown` switch to manual scrub (track `scrollLeft` vs pointer X), resume auto-scroll on release.

---

### 9.13 Dark Editorial Section

Full-width navy block for "Featured Journeys" or "Travel for a Cause".

```css
.tt-dark-section {
  background: #0a1628;
  color: #fff;
  border-radius: var(--r-sm);
  padding: 72px 64px;
  position: relative;
  overflow: hidden;
}
.tt-dark-section .tt-eyebrow { color: rgba(255,255,255,0.6); }
.tt-dark-section h2           { color: #fff; }
.tt-dark-section p            { color: rgba(255,255,255,0.7); }

.tt-journey-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-top: 48px;
}

.tt-journey {
  position: relative;
  aspect-ratio: 5 / 4;
  border-radius: var(--r-sm);
  overflow: hidden;
  cursor: pointer;
}

.tt-journey-cat {
  position: absolute; top: 16px; left: 16px;
  background: rgba(255,255,255,0.16);
  border: 1px solid rgba(255,255,255,0.25);
  color: #fff; font-size: 12px;
  padding: 5px 12px; border-radius: var(--pill);
  z-index: 3; backdrop-filter: blur(4px);
}

.tt-journey-body {
  position: absolute; left: 20px; right: 20px; bottom: 20px;
  z-index: 3; color: #fff;
}

.tt-journey-title { font-size: 22px; font-weight: 600; letter-spacing: -0.01em; line-height: 1.15; }
.tt-journey-loc   { font-size: 14px; opacity: 0.85; margin-top: 6px; }

.tt-journey-link {
  font-size: 14px; margin-top: 16px;
  display: inline-flex; gap: 8px; align-items: center; opacity: 0.9;
}
.tt-journey:hover .tt-journey-link     { gap: 12px; }
.tt-journey-link svg                   { transition: transform .3s var(--ease); }
.tt-journey:hover .tt-journey-link svg { transform: translateX(4px); }
```

---

### 9.14 How It Works Grid

3-icon grid with numbered steps — used on homepage and booking pages.

```html
<!-- 3-column grid, each cell has icon + heading + body -->
<div class="tt-section">
  <div class="tt-page">
    <p class="tt-eyebrow tt-text-c" style="margin-bottom:16px">How it works</p>
    <h2 class="tt-h2 tt-text-c" style="margin-bottom:56px">Three easy steps</h2>
    <div class="tt-grid-3">
      <div style="text-align:center;padding:32px 24px">
        <div style="width:48px;height:48px;border-radius:50%;background:var(--bg-soft);
                    display:flex;align-items:center;justify-content:center;margin:0 auto 20px">
          {% tt_icon "search" size=20 %}
        </div>
        <h3 class="tt-h3" style="margin-bottom:8px">Search stays</h3>
        <p class="tt-soft" style="font-size:15px">Choose from our curated collection across Pondicherry and Auroville.</p>
      </div>
      {# steps 2 and 3 #}
    </div>
  </div>
</div>
```

---

### 9.15 Forms & Inputs

```css
.tt-field {
  display: flex; flex-direction: column; gap: 8px;
}

.tt-field-label,
.tt-field label {
  font-size: 12px; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--text-muted);
  font-weight: 500;
}

.tt-input,
.tt-select,
.tt-field input,
.tt-field select {
  padding: 14px 16px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-strong);
  background: var(--surface);
  font-size: 15px; outline: none;
  color: var(--ink);
  transition: border-color .2s var(--ease), box-shadow .2s var(--ease);
  width: 100%;
}

.tt-input:focus,
.tt-select:focus,
.tt-field input:focus,
.tt-field select:focus {
  border-color: var(--ink);
  box-shadow: 0 0 0 3px rgba(10,22,40,0.06);
}

.tt-textarea {
  width: 100%; padding: 14px 16px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-strong);
  background: var(--surface);
  font: inherit; font-size: 15px; color: var(--ink);
  outline: none; resize: vertical;
  transition: border-color .2s var(--ease), box-shadow .2s var(--ease);
}
.tt-textarea:focus {
  border-color: var(--ink);
  box-shadow: 0 0 0 3px rgba(10,22,40,.06);
}

/* Read-only display value */
.tt-field-val {
  font-size: 15px; font-weight: 500; color: var(--ink);
  padding: 14px 16px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--bg-soft);
}
```

---

### 9.16 Stepper (Booking Wizard)

3-step: Trip details → About you → Review & request.

```css
.tt-stepper {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; color: var(--text-muted);
}

.tt-step { display: flex; align-items: center; gap: 8px; }

.tt-step-num {
  width: 24px; height: 24px;
  border-radius: 50%;
  background: transparent;
  border: 1px solid var(--line-strong);
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 600;
}

.tt-step.active .tt-step-num { background: var(--ink); color: #fff; border-color: var(--ink); }
.tt-step.done   .tt-step-num { background: var(--accent); color: #fff; border-color: var(--accent); }
.tt-step.active .tt-step-label { color: var(--ink); font-weight: 500; }

/* Connecting bar between steps */
.tt-step-bar { width: 32px; height: 1px; background: var(--line-strong); }
```

```html
<div class="tt-stepper">
  <div class="tt-step {% if step >= 1 %}active{% endif %} {% if step > 1 %}done{% endif %}">
    <div class="tt-step-num">
      {% if step > 1 %}{% tt_icon "check" size=10 %}{% else %}1{% endif %}
    </div>
    <span class="tt-step-label">Trip details</span>
  </div>
  <div class="tt-step-bar"></div>
  <div class="tt-step {% if step >= 2 %}active{% endif %} {% if step > 2 %}done{% endif %}">
    <div class="tt-step-num">{% if step > 2 %}{% tt_icon "check" size=10 %}{% else %}2{% endif %}</div>
    <span class="tt-step-label">About you</span>
  </div>
  <div class="tt-step-bar"></div>
  <div class="tt-step {% if step >= 3 %}active{% endif %}">
    <div class="tt-step-num">3</div>
    <span class="tt-step-label">Review &amp; request</span>
  </div>
</div>
```

---

### 9.17 Status Badges

Used in booking list (Upcoming / Past tabs).

```css
.tt-status {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 500;
  padding: 5px 12px;
  border-radius: var(--pill);
  letter-spacing: 0.02em;
}

.tt-status-dot { width: 6px; height: 6px; border-radius: 50%; }

.tt-status-pending  { background: oklch(0.96 0.04 75); color: #8a5a00; }
.tt-status-pending .tt-status-dot { background: #c47a00; animation: pulse 1.6s infinite; }

.tt-status-approved { background: var(--accent-soft); color: var(--accent-deep); }
.tt-status-approved .tt-status-dot { background: var(--accent); }

.tt-status-confirmed { background: oklch(0.95 0.05 145); color: #1a7f4b; }
.tt-status-confirmed .tt-status-dot { background: #1a7f4b; }

.tt-status-completed { background: var(--bg-soft); color: var(--text-soft); }
.tt-status-completed .tt-status-dot { background: var(--text-soft); }
```

```html
<span class="tt-status tt-status-{{ booking.status }}">
  <span class="tt-status-dot"></span>
  {{ booking.status|title }}
</span>
```

---

### 9.18 Room Card

Horizontal 3-col card: thumbnail | details | price + select button.

```css
.tt-room-card {
  display: grid;
  grid-template-columns: 140px 1fr auto;
  gap: 24px;
  align-items: center;
  padding: 16px;
  border-radius: 6px;
  border: 1px solid var(--line);
  background: #fff;
  cursor: pointer;
  transition: all .2s var(--ease);
  position: relative;
}

.tt-room-card.selected {
  border-color: var(--ink);
  background: var(--bg-soft);
}
```

---

### 9.19 Summary Sidebar Card

Sticky sidebar on the booking/property detail page.

```css
.tt-summary {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  padding: 28px;
  position: sticky;
  top: 110px;    /* nav height + buffer */
}
```

---

### 9.20 Modal

Centered overlay with blur backdrop.

```css
.tt-modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(10,22,40,0.45);
  backdrop-filter: blur(6px);
  display: flex; align-items: center; justify-content: center;
  z-index: 100;
  padding: 24px;
  animation: fadein .25s var(--ease);
}

.tt-modal {
  width: 100%; max-width: 480px;
  background: #fff;
  border-radius: var(--r-sm);
  padding: 36px 32px;
  animation: rise .35s var(--ease);
}
```

---

### 9.21 Progress Bar (Loyalty)

Used in loyalty tiers screen.

```css
.tt-progress {
  height: 6px;
  border-radius: 999px;
  background: var(--bg-tint);
  overflow: hidden;
}

.tt-progress-fill {
  height: 100%;
  background: var(--ink);
  border-radius: 999px;
  transition: width 1s var(--ease);
}
```

```html
<div class="tt-progress">
  <div class="tt-progress-fill" style="width: {{ loyalty.progress_pct }}%"></div>
</div>
```

**Loyalty tiers:** Bronze → Silver → Gold

---

### 9.22 Success / Confirmation Screen

Shown after booking request is submitted (WhatsApp link sent).

```css
.tt-confetti-wrap {
  position: relative; width: 100%;
  padding: 96px 0 64px; text-align: center; overflow: hidden;
}

.tt-success-mark {
  width: 88px; height: 88px;
  margin: 0 auto 28px;
  border-radius: 50%;
  background: var(--ink); color: #fff;
  display: flex; align-items: center; justify-content: center;
  animation: pop .55s var(--ease);
}
```

```html
<div class="tt-confetti-wrap">
  <div class="tt-success-mark">
    {% tt_icon "check" size=36 %}
  </div>
  <h2 class="tt-h2" style="margin-bottom:12px">Request sent!</h2>
  <p class="tt-soft" style="max-width:420px;margin:0 auto 32px;font-size:17px">
    We've received your booking request. Check WhatsApp — we'll confirm within a few hours.
  </p>
  <a href="{{ WA_URL }}" target="_blank" class="tt-btn tt-btn-primary" style="font-size:16px">
    {% tt_icon "wa" size=16 %} Open WhatsApp
  </a>
</div>
```

---

### 9.23 Footer

Two-column grid: brand blurb left, help links right.

```css
.tt-footer {
  margin-top: 96px;
  padding: 80px 0 40px;
  border-top: 1px solid var(--line);
  background: #fff;
}

.tt-footer-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 56px;
}

.tt-footer h4 {
  font-size: 12px; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--text-muted);
  margin: 0 0 18px; font-weight: 500;
}

.tt-footer ul {
  list-style: none; padding: 0; margin: 0;
  display: flex; flex-direction: column; gap: 10px;
  font-size: 14px; color: var(--text-soft);
}

.tt-footer ul a:hover { color: var(--ink); }
```

```html
<footer class="tt-footer">
  <div class="tt-page">
    <div class="tt-footer-grid">
      <div>
        <div class="tt-logo-split" style="margin-bottom:18px">
          <img src="{% static 'logo-left.png' %}" alt="Logo" class="tt-logo-left-img" style="height:44px">
          <img src="{% static 'logo-half.png' %}" alt="Temple and Towns" class="tt-logo-half-img" style="height:30px">
        </div>
        <p style="color:var(--text-soft);font-size:14px;max-width:340px;line-height:1.6;margin:0">
          Modern, calm, unmistakably Indian. A small, hand-picked collection of stays
          across temple towns and quiet coastlines.
        </p>
        <div style="display:flex;gap:12px;margin-top:24px;font-size:13px;color:var(--text-muted)">
          <a href="#">Instagram</a><span>·</span><a href="#">Journal</a>
        </div>
      </div>
      <div>
        <h4>Help</h4>
        <ul>
          <li><a href="{{ wa_cancellation }}">Cancellation</a></li>
          <li><a href="{{ wa_contact }}">Contact host</a></li>
          <li><a href="{% url 'privacy' %}">Privacy</a></li>
          <li><a href="{% url 'terms' %}">Terms</a></li>
        </ul>
      </div>
    </div>
    <div class="tt-footer-bottom" style="margin-top:64px;padding-top:28px;border-top:1px solid var(--line);
         display:flex;justify-content:space-between;font-size:13px;color:var(--text-muted)">
      <span>© 2026 Temple And Towns Resorts LLP · Pondicherry &amp; Near Auroville</span>
      <span>INR · English</span>
    </div>
  </div>
</footer>
```

---

### 9.24 WhatsApp FAB

Fixed bottom-right floating action button.

```css
.tt-wa-fab {
  position: fixed;
  right: 36px; bottom: 36px;
  width: 56px; height: 56px;
  background: var(--whatsapp);
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  color: #fff;
  z-index: 80;
  box-shadow: 0 10px 28px -8px rgba(37,211,102,0.55);
  cursor: pointer;
  transition: transform .25s var(--ease);
}

.tt-wa-fab:hover { transform: translateY(-2px) scale(1.04); }
```

```html
<!-- Place just before </body> -->
<a class="tt-wa-fab" href="{{ WA_URL }}" target="_blank" rel="noopener noreferrer"
   aria-label="Chat with Support">
  {% tt_icon "wa" size=26 %}
</a>
```

---

### 9.25 Nature Retreat — Experience Rows

The Nature Retreat page (`retreat.jsx`) uses alternating image/text rows. A full-bleed hero (`.tt-retreat-hero`), a highlights grid (`.tt-highlights-grid`), the experience list below, and a closing 2-col `.tt-retreat-gallery`.

```css
.tt-experience-list {
  display: flex; flex-direction: column;
  gap: 48px;
}

.tt-experience-row {
  display: flex; gap: 32px;
  align-items: center;
}
.tt-experience-row.tt-row         { flex-direction: row; }
.tt-experience-row.tt-row-reverse { flex-direction: row-reverse; }   /* zig-zag */

.tt-experience-img-wrap {
  flex: 1;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  background: var(--bg-soft);
}
.tt-experience-img-wrap img { width: 100%; height: 100%; object-fit: cover; display: block; }

.tt-experience-text { flex: 1; padding: 16px; }
.tt-experience-text .tt-h3    { margin-bottom: 12px; }
.tt-experience-text .tt-muted { font-size: 16px; line-height: 1.6; }
```

**Mobile (≤768px):** `.tt-retreat-hero` height `260px`; `.tt-highlights-grid` → 1 col; `.tt-experience-row` stacks to a column (`align-items: stretch`); `.tt-experience-img-wrap` goes full-width `16/9`; `.tt-retreat-gallery` → 2 cols.

---

### 9.26 Events Page

Centered editorial list of event cards (`events.jsx`). Each card is a horizontal flex row: circular icon | body (name + description + actions). Closes with a soft-bg CTA block.

```css
.tt-events-page   { padding-top: 32px; padding-bottom: 96px; }
.tt-events-crumb  { margin-bottom: 24px; }

.tt-events-header { text-align: center; max-width: 640px; margin: 0 auto 64px; }
.tt-events-title  { margin-top: 12px; margin-bottom: 16px; }
.tt-events-intro  { color: var(--text-soft); font-size: 17px; line-height: 1.65; margin: 0; }

.tt-events-list   { max-width: 720px; margin: 0 auto; display: grid; gap: 20px; }

.tt-event-card {
  display: flex; align-items: flex-start; gap: 24px;
  padding: 32px;
  border: 1px solid var(--line);
  background: #fff;
  transition: box-shadow 0.25s ease, transform 0.25s ease;
}
.tt-event-card:hover { box-shadow: 0 8px 32px rgba(0,0,0,0.08); transform: translateY(-2px); }

/* Explicit width keeps the icon circular even when the card stacks on mobile */
.tt-event-icon {
  flex: 0 0 52px; width: 52px; height: 52px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
}

.tt-event-body { flex: 1; min-width: 0; }
.tt-event-name { font-size: 19px; font-weight: 600; margin: 0 0 8px; color: var(--ink); }
.tt-event-desc { font-size: 15px; line-height: 1.6; margin: 0; }

.tt-event-actions { margin-top: 20px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.tt-event-via     { font-size: 13px; }

.tt-events-cta         { margin: 72px auto 0; text-align: center; padding: 48px; background: var(--bg-soft); max-width: 720px; }
.tt-events-cta-text    { font-size: 15px; max-width: 440px; margin: 0 auto 28px; }
.tt-events-cta-actions { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }
```

**Mobile (≤768px):** page padding tightens (`padding-top: 18px`), card padding `18px 16px`, icon shrinks to `40px`, name `17px`.

---

## 10. Responsive Breakpoints

| Breakpoint | Width | Key changes |
|-----------|-------|-------------|
| Desktop | `>1200px` | Full 56px padding, 3-col grids, 5-col search bar |
| Tablet | `≤1200px` | 32px padding, hero goes single-col, 2-col grids, search bar 2-col |
| Mobile | `≤768px` | 16px padding, nav collapses to hamburger, 90vh hero, category tabs |
| Touch | `hover: none` | All hover transforms disabled |

```css
/* Tablet — ≤1200px */
@media (max-width: 1200px) {
  .tt-page, .tt-utility-inner, .tt-nav-inner { padding-left: 32px; padding-right: 32px; }
  .tt-hero-grid { grid-template-columns: 1fr; }
  .tt-search { grid-template-columns: 1fr 1fr; }
  .tt-search-go { grid-column: span 2; padding: 18px; justify-content: center; }
  .tt-grid-3, .tt-journey-grid, .tt-moments-grid { grid-template-columns: repeat(2, 1fr); }
  .tt-footer-grid { grid-template-columns: 1fr 1fr; }
  .tt-dark-section { padding: 56px 32px; }
}

/* Mobile — ≤768px (summarised — see full blocks above) */
@media (max-width: 768px) {
  .tt-page { padding: 0 16px; }
  .tt-nav-links { display: none; }
  .tt-hamburger { display: inline-flex; }
  .tt-utility-support, .tt-utility-right { display: none; }
  .tt-hero-section { height: 90vh; }
  .tt-hero-desktop-wrap { display: none !important; }
  .tt-grid-3 { grid-template-columns: 1fr; }
}
```

---

## 11. Page Layouts

### Homepage

```
UtilityBar
Navbar (sticky)
  └── Hero Section
       ├── [Desktop] tt-hero-grid (headline | featured card)
       └── [Mobile]  90vh full-bleed image + .tt-hero-mobile-top (search bar)
                     + .tt-hero-float-overlay (fixed scroll-fade headline + CTA)
CategoryTabs (scroll)
FeaturedStays (3-col → 2-col → 1-col cards, each with swipeable image carousel)
MomentsCarousel (JS-driven horizontal auto-scroll, draggable, mask-faded edges)
DarkSection (Featured Journeys, 3-col)
HowItWorksGrid (3-col)
LoyaltyTeaser
Footer
WhatsAppFab (fixed)
```

### Search / Results Page

```
Navbar (sticky)
SearchBar (5-col desktop / 2-col tablet)
ResultsList (property cards, list layout with left image)
```

### Property Detail Page

```
Navbar (sticky)
ImageGallery (responsive grid)
  ├── Left: property name, highlights, room selector, reviews
  └── Right: tt-summary sidebar (sticky)
[Mobile] sticky bottom CTA bar
```

### Booking Wizard Page

```
Navbar
Stepper (3 steps)
Step 1: Trip Details (arrival chips, dates, textarea)
Step 2: About You (name, email, phone)
Step 3: Review & Request → WhatsApp submit → Success screen
```

### Account Pages

```
Tabs: Upcoming | Past
BookingCard (status badge, property, dates, WhatsApp link)
LoyaltyScreen (tier progress, points)
```

---

## 12. Data Model

### Properties

```python
# models.py — Django equivalent of TT_DATA.properties
class Property(models.Model):
    THEME_CHOICES = [
        ('temple', 'Temple stays'),
        ('town', 'Town escapes'),
        ('nature', 'Nature retreats'),
    ]
    CITY_CHOICES = [
        ('pondicherry', 'Pondicherry'),
        ('auroville', 'Near Auroville'),
    ]

    id        = models.CharField(max_length=8, primary_key=True)  # e.g. 'p1'
    city      = models.CharField(max_length=20, choices=CITY_CHOICES)
    theme     = models.CharField(max_length=20, choices=THEME_CHOICES)
    name      = models.CharField(max_length=120)
    area      = models.CharField(max_length=120)   # "White Town · 100m from beach"
    blurb     = models.TextField()
    rating    = models.DecimalField(max_digits=3, decimal_places=1)
    reviews   = models.CharField(max_length=20)    # "10+" (display string)
    from_text = models.CharField(max_length=40)    # "Book now" or "₹3,500"
    booking_url = models.URLField()
    cover     = models.ImageField(upload_to='properties/covers/')
```

### 4 Real Properties

| ID | Name | City | Theme | Booking |
|----|------|------|-------|---------|
| p1 | White Town 1BHK - 1st Floor | pondicherry | town | Airbnb |
| p2 | White Town 1BHK - 2nd Floor | pondicherry | town | Airbnb |
| p3 | White Town 2BHK - 1st Floor | pondicherry | town | Airbnb |
| p4 | Nature Retreat | auroville | nature | Booking.com |

### Rooms

```python
class Room(models.Model):
    property    = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='rooms')
    type        = models.CharField(max_length=60)    # "1BHK 1st Floor"
    capacity    = models.IntegerField()               # max guests
    beds        = models.CharField(max_length=80)    # "1 Queen + Living Room"
    size        = models.CharField(max_length=80)    # "Independent floor"
    amenities   = models.JSONField(default=list)     # ["Wi-Fi", "Kitchen", "Laundry", "Balcony"]
```

### Booking (Django new model)

```python
class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('approved',  'Approved'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
    ]
    user         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    property     = models.ForeignKey(Property, on_delete=models.PROTECT)
    room         = models.ForeignKey(Room, on_delete=models.PROTECT)
    check_in     = models.DateField()
    check_out    = models.DateField()
    guests       = models.IntegerField()
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    message      = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    whatsapp_ref = models.CharField(max_length=120, blank=True)
```

---

## 13. Django Rebuild Notes

### File structure

```
project/
├── static/
│   ├── css/
│   │   └── styles.css          ← copy src/styles.css verbatim (mobile @media blocks
│   │                              are inline; the src/ build has NO separate
│   │                              mobile-overrides.css — that was the old test/ build)
│   ├── js/
│   │   └── main.js             ← scroll fade, hamburger toggle, bottom sheet
│   └── images/
│       ├── logo-left.png
│       ├── logo-half.png
│       ├── hero_resort.png
│       └── ...property images
├── templates/
│   ├── base.html               ← utility bar + navbar + footer + fab
│   ├── home.html
│   ├── search.html
│   ├── property_detail.html
│   ├── booking/
│   │   ├── step1.html
│   │   ├── step2.html
│   │   └── step3.html
│   ├── account/
│   │   ├── bookings.html
│   │   └── loyalty.html
│   └── partials/
│       ├── property_card.html  ← reusable card partial
│       └── status_badge.html
└── templatetags/
    └── tt_icons.py             ← custom icon template tag
```

### base.html pattern

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Temple And Towns Resorts{% endblock %}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{% static 'css/styles.css' %}">
</head>
<body>
  {% include "partials/utility_bar.html" %}
  {% include "partials/navbar.html" %}

  <main>
    {% block content %}{% endblock %}
  </main>

  {% include "partials/footer.html" %}

  {# WhatsApp FAB #}
  <a class="tt-wa-fab" href="{{ WA_URL }}" target="_blank" rel="noopener noreferrer" aria-label="Chat">
    {# SVG wa icon inline #}
  </a>

  <script src="{% static 'js/main.js' %}"></script>
</body>
</html>
```

### main.js — Core interactions

```javascript
// Hamburger toggle
document.querySelector('.tt-hamburger')?.addEventListener('click', () => {
  document.querySelector('.tt-mobile-menu')?.classList.toggle('open');
});

// Scroll-fade on the fixed hero float overlay (mobile)
window.addEventListener('scroll', () => {
  const alpha = Math.max(0, 1 - window.scrollY / 160);
  const floatEl = document.querySelector('.tt-hero-float-overlay');
  if (floatEl) floatEl.style.opacity = alpha;
}, { passive: true });

// Bottom sheet open/close
const msbTrigger = document.getElementById('msbTrigger');
const bottomSheet = document.getElementById('bottomSheet');
const sheetBackdrop = document.getElementById('sheetBackdrop');

function openSheet() {
  bottomSheet?.classList.add('open');
  sheetBackdrop?.classList.add('open');
}
function closeSheet() {
  bottomSheet?.classList.remove('open');
  sheetBackdrop?.classList.remove('open');
}

msbTrigger?.addEventListener('click', openSheet);
sheetBackdrop?.addEventListener('click', closeSheet);

// Category tab filter (with HTMX or vanilla)
document.querySelectorAll('.tt-tab-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    document.querySelectorAll('.tt-tab-chip').forEach(c => c.classList.remove('tt-tab-chip-active'));
    chip.classList.add('tt-tab-chip-active');
  });
});
```

### WhatsApp booking URL builder

```python
# utils.py
import urllib.parse

WA_NUMBER = '910000000000'  # include country code, no +

def wa_booking_url(property_name, check_in, check_out, guests, room_type):
    text = (
        f"Hi, I'd like to book:\n"
        f"Property: {property_name}\n"
        f"Room: {room_type}\n"
        f"Check-in: {check_in}\n"
        f"Check-out: {check_out}\n"
        f"Guests: {guests}"
    )
    encoded = urllib.parse.quote(text)
    return f"https://api.whatsapp.com/send/?phone={WA_NUMBER}&text={encoded}&type=phone_number&app_absent=0"
```

### Admin panel additions for Django rebuild

```python
# admin.py
from django.contrib import admin
from .models import Property, Room, Booking

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ['name', 'city', 'theme', 'rating']
    list_filter  = ['city', 'theme']
    search_fields = ['name', 'area']

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['property', 'user', 'check_in', 'check_out', 'status', 'created_at']
    list_filter  = ['status', 'property__city']
    list_editable = ['status']
    search_fields = ['user__email', 'property__name']
    actions = ['mark_confirmed', 'mark_approved']

    def mark_confirmed(self, request, queryset):
        queryset.update(status='confirmed')
    def mark_approved(self, request, queryset):
        queryset.update(status='approved')
```

### Icon template tag (replaces React `<Ico>` component)

```python
# templatetags/tt_icons.py
from django import template
from django.utils.html import format_html

register = template.Library()

ICONS = {
    'search': '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    'pin':    '<path d="M12 21s7-6.5 7-12a7 7 0 1 0-14 0c0 5.5 7 12 7 12Z"/><circle cx="12" cy="9" r="2.5"/>',
    'cal':    '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    'arrow':  '<path d="M5 12h14M13 6l6 6-6 6"/>',
    'check':  '<path d="m5 12 4.5 4.5L19 7"/>',
    'star':   '<path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1.1 5.9L12 16.9 6.7 19.7l1.1-5.9-4.3-4.1 5.9-.8L12 3.5Z"/>',
    'menu':   '<path d="M4 7h16M4 12h16M4 17h16"/>',
    'x':      '<path d="M6 6l12 12M18 6 6 18"/>',
    'user':   '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.6-4 4.5-6 8-6s6.4 2 8 6"/>',
    'wa':     None,  # special case — use full fill SVG
}

@register.simple_tag
def tt_icon(name, size=16, class_name='tt-ico'):
    paths = ICONS.get(name, '')
    if name == 'wa':
        return format_html(
            '<svg width="{}" height="{}" viewBox="0 0 24 24" fill="currentColor" class="{}">'
            '<path d="M17.5 14.4c-.3-.1-1.6-.8-1.9-.9-.3-.1-.4-.1-.6.1-.2.3-.7.9-.9 1.1-.2.2-.3.2-.6.1-.3-.2-1.2-.5-2.3-1.4-.9-.8-1.4-1.7-1.6-2-.2-.3 0-.5.1-.6.1-.1.3-.4.4-.5.1-.2.2-.3.3-.5 0-.2 0-.3 0-.5-.1-.1-.6-1.5-.8-2-.2-.5-.4-.5-.6-.5h-.5c-.2 0-.5.1-.7.3-.3.3-1 1-1 2.4 0 1.4 1 2.7 1.1 2.9.1.2 2 3.1 4.9 4.3.7.3 1.2.5 1.6.6.7.2 1.3.2 1.8.1.6-.1 1.6-.7 1.9-1.4.2-.6.2-1.2.1-1.4-.1-.1-.3-.2-.5-.3M12 2C6.5 2 2 6.5 2 12c0 1.7.4 3.4 1.3 4.9L2 22l5.3-1.3c1.4.8 3 1.3 4.7 1.3 5.5 0 10-4.5 10-10S17.5 2 12 2"/>'
            '</svg>', size, size, class_name
        )
    return format_html(
        '<svg width="{}" height="{}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" class="{}">'
        '{}</svg>',
        size, size, class_name, format_html(paths)
    )
```

### HTMX patterns (for real-time-ish UX without full SPA)

```html
<!-- Category tab filtering without page reload -->
<button class="tt-tab-chip"
        hx-get="{% url 'properties_partial' %}?theme=temple"
        hx-target="#property-grid"
        hx-swap="innerHTML">
  Temple stays
</button>

<!-- Booking status update (admin action triggers this) -->
<span class="tt-status tt-status-{{ booking.status }}"
      hx-get="{% url 'booking_status' booking.id %}"
      hx-trigger="every 30s"
      hx-swap="outerHTML">
  {{ booking.status|title }}
</span>
```

---

*Generated from the production Vite build: `src/styles.css` (v2, 3,300+ lines), `src/components/{shell,home,search,retreat,events}.jsx`, `src/data.js` · tt2 project · `ui-revisions` branch · revised June 15, 2026.*
