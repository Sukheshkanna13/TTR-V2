# TEMPLE AND TOWNS RESORTS

## Hotel Booking Platform

### Platform Feature & Architecture Specification

##### Module-by-Module User Flows · V1 → V2 → V3 Roadmap

##### Pondicherry • (14 rooms + 3 rooms + scalable on multiple locations) 
```

## PRODUCT ROADMAP

##### Temple and Towns Resorts is built in three focused phases. Each phase builds on the previous, ensuring the

##### platform grows reliably without disruption to operations.

##### V1 Digital Presence — Deliver First

- Mobile-first property showcase website: rooms, photos, and pricing across all cities
- All booking enquiries flow through WhatsApp — one tap opens a chat with the property
- No backend systems needed — ships fast, establishes online presence immediately
- Purpose: be discoverable online and start capturing guest interest while V2 is built

##### V2 Online Booking Application — Core Platform

- Guests can search, select, and book rooms directly with online payment
- Real-time availability — only genuinely free rooms shown to guests
- 10-minute room hold during payment prevents any double booking
- Guest accounts: login history, booking records, invoice access
- Employee and Super Admin panels for operations and management
- Automated confirmation emails and WhatsApp messages
- Loyalty points program introduced — earn points per stay, 3 membership tiers

##### V3 Growth & Differentiation Features

- OTA integration — sync availability automatically with Booking.com, MakeMyTrip, Agoda
- Full loyalty program — campaigns, multipliers, advanced coupon management
- Room UX signals — sold out, last room, trending, top-rated badges
- Explore Culture page — local attractions and experiences by city
- Travel for a Cause — volunteer opt-in and guest matching
- Tax reporting, analytics dashboard, future accounting integration
V1 ships while V2 is in development. V3 features are built one at a time, each confirmed with the client before
development begins.


## DIAGRAM 1 — PRODUCT ROADMAP OVERVIEW

##### How the three versions relate to each other. Each version is a complete, working product — V2 and V3 add

##### capability on top of a stable foundation.

```
Fig 1 — V1 (digital presence), V2 (full booking app + loyalty), V3 (OTA sync + growth features). Each column shows the
key modules in that version.
```
### Version Summary

```
Version Primary Goal Key Additions
V1 Be online, capture leads Property showcase, WhatsApp
booking
V2 Accept payments, manage
operations
```
```
Online booking, payments,
accounts, loyalty start, admin
panels
V3 Scale and differentiate OTA sync, full loyalty, culture page,
volunteer, analytics
```

## DIAGRAM 2 — GUEST BOOKING FLOW

##### How a guest moves from discovering a room to receiving a confirmed booking. This is the core journey every

##### guest goes through in V2. Each step is a self-contained module.

```
Fig 2 — Five-module guest journey: Discovery → Login → Room Hold (10 min) → Payment → Confirmation. Status bar at
bottom shows all possible booking states.
```
### Module-by-Module Explanation

#### Module 1 — Discovery

##### The guest browses properties without needing to log in. They can filter by city, view room photos and

##### descriptions, and check pricing. The availability shown is real-time — if a room is already booked or held, it

##### will not appear in the results.

#### Module 2 — Login / Account


##### When the guest decides to book, they are prompted to log in. Two options are available: email address with a

##### one-time verification code, or existing Google account. If the same email is used for both, the system

##### recognises it and merges them into one account — all bookings, points, and history unified.

#### Module 3 — Room Hold (10 Minutes)

##### When the guest confirms their selection, the room is instantly reserved for that guest for 10 minutes. No

##### other guest can book the same room and dates during this window. This prevents two guests from

##### simultaneously paying for the same room.

##### If payment is not completed within 10 minutes, the hold is automatically released and the room becomes

##### available for other guests again. This runs as a background check — no manual intervention needed.

#### Module 4 — Payment

##### The guest is taken to a secure payment page. All major Indian payment methods are supported: UPI apps

##### (Google Pay, PhonePe, Paytm), debit and credit cards, net banking, and wallets. Payment is handled by a

##### certified payment gateway — card data is never stored on our servers.

##### Once payment is completed, the gateway sends a secure confirmation to our system. The booking is verified

##### and marked as Confirmed.

#### Module 5 — Confirmation

##### Immediately after payment, the guest receives a confirmation invoice by email and a WhatsApp message. The

##### invoice includes booking reference, property details, dates, amount breakdown, and tax. Loyalty points are

##### credited to the guest's account at this point.

### Booking Status States

```
Status What It Means How Long
HELD Room reserved, guest on payment
page
```
```
Up to 10 minutes
```
```
CONFIRMED Payment received, booking secured Until checkout date
COMPLETED Stay finished, bonus points credited Permanent
EXPIRED 10-minute window passed without
payment
```
```
Room freed automatically
```
```
CANCELLED Guest or admin cancelled booking Cancellation policy applies
```

## DIAGRAM 3 — LOYALTY POINTS PROGRAM

##### The loyalty program rewards guests for staying with Temple and Towns Resorts. It follows the same

##### structural logic as major hotel loyalty programs — guests earn points, unlock tiers, and redeem rewards —

##### adapted for a boutique multi-property scale.

```
Fig 3 — Three sections: (A) how points are earned, (B) the three membership tiers, (C) campaign multipliers and coupon
redemption. All values configured by Super Admin.
```
### Reference: How Major Hotel Programs Work

##### Programs like Marriott Bonvoy and IHG One Rewards follow the same core structure: guests earn points per

##### night, accumulate into tiers, unlock discounts and perks at higher tiers, and can redeem points for rewards.

##### Time-limited campaigns offer bonus points to drive bookings during specific periods.

##### Temple and Towns applies the same architecture — tier names, point thresholds, discount percentages, and

##### campaign rules are all configured by the Super Admin. Nothing is hardcoded.

### Section A — How Points Are Earned

```
Trigger When It Happens Points
First booking bonus Guest books for the very first time Set by admin
```

```
Per night stayed Every confirmed booking Set by admin per night
Successive bookings Returning guest from 2nd booking
onwards
```
```
Higher rate — set by admin
```
```
Monthly repeat Guest books 2+ times in same
calendar month
```
```
Multiplier — set by admin
```
```
Review submitted Guest writes a review after their
stay
```
```
Set by admin
```
```
Referral Friend signs up and completes their
first booking
```
```
Set by admin
```
### Section B — Three Membership Tiers

- Tier 1 (Base): All guests start here. No discount. Points accumulate normally.
- Tier 2 (Mid): Unlocked when guest crosses a set points threshold. Percentage discount on bookings.

##### Points earn at a higher rate.

- Tier 3 (Top): Highest threshold. Highest discount. Priority treatment.
All tier names, point thresholds, and discount percentages are set and adjustable by the Super Admin from the
admin panel at any time.

### Section C — Campaigns & Coupon Redemption

##### The Super Admin can run time-limited campaigns from the admin panel: for example, double points every

##### weekend, triple points during a festival week, or a bonus for stays above a certain amount. Campaigns are

##### toggled on and off in real time with a defined start and end date.

##### Guests can redeem accumulated points for discount coupons. The Super Admin defines redemption rules —

##### for example, 100 points equals a ₹500 discount coupon. The guest redeems from their dashboard, receives a

##### unique code, and applies it at their next booking checkout.


## DIAGRAM 4 — ADMIN MODULE FLOW

##### Two admin roles manage the platform: Employee Admin and Super Admin. They share the same underlying

##### data but see different views and have different levels of control. Guest and admin systems are completely

##### separate — different logins, different access paths.

```
Fig 4 — Left column: Employee Admin modules (property-scoped). Right column: Super Admin modules (platform-wide).
Bottom bar: shared system principles.
```
### Employee Admin — What They Can Do

- Manage rooms for their assigned properties: add or edit rooms, upload photos, set pricing, adjust

##### seasonal rates, mark rooms as inactive during maintenance

- View and manage the availability calendar: two views available (horizontal timeline showing week, and

##### monthly grid), with colour coding for confirmed bookings, active holds, and manually blocked dates

- Block dates when an external booking arrives (from any OTA platform) — enter the date range and the

##### external reference, and those dates are blocked for guests on this platform

- View confirmed bookings and guest details for their assigned properties
- Financial visibility is controlled by Super Admin — employee may see booking status only, booking

##### amounts, or full financial view depending on what they are assigned

### Super Admin — What They Control

- Create all employee accounts: set email, initial password, assign one or multiple properties, set

##### financial access level. Employees change their own password after first login.


- Full financial view: set room costs, view profit across date ranges and properties, configure tax rules

##### per property

- Manage all properties across all cities: add new properties, toggle visibility on and off, manage

##### cancellation policies

- Control the entire loyalty program: tier names, point rules, campaign multipliers, coupon creation —

##### all in real time

- View platform-wide analytics: revenue by property and city, occupancy trends, booking breakdown,

##### and a full audit trail of all admin actions

Super Admin has full override capability on all employee accounts — can lock, reset, or deactivate any account
at any time. Employees can only access the properties they are assigned.


## FULL MODULE SUMMARY

```
Module Version What It Does
Property showcase V1 Displays rooms, photos, pricing —
no account needed
WhatsApp booking V1 One-tap redirect to WhatsApp chat
for booking enquiry
Room search & availability V2 Real-time availability — only free
rooms shown
10-minute room hold V2 Prevents double booking during
payment window
Online payment V2 UPI, card, net banking, wallets via
payment gateway
Guest accounts V2 Email OTP or Google login · unified
profile · booking history
Invoice & confirmation V2 Auto-sent by email + WhatsApp on
payment confirmation
Employee admin panel V2 Room management, calendar,
bookings for assigned properties
Super admin panel V2 Platform-wide control, financials,
employee management
Loyalty points (start) V2 Earn points per stay, 3 tiers,
coupon redemption
OTA availability sync V3 Automatic inventory sync with
external booking platforms
Full loyalty program V3 Campaigns, multipliers, advanced
admin control
Room UX signals V3 Sold out, last room, trending, top-
rated labels
Explore Culture page V3 Admin-managed local attractions
by city
Travel for a Cause V3 Volunteer opt-in and matching
guests with shared interests
Analytics & audit V3 Revenue reports, occupancy, tax,
full audit trail
```
##### Temple and Towns Resorts | Pondicherry • Auroville • Bengaluru

```
Platform Feature & Architecture Specification — May 2026
```

