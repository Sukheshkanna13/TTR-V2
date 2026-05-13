# Temples & Towns — Website Content Reference

This document serves as a complete reference for all the text, copy, and structural content across the Temples & Towns (TTR-V2) platform.

---

## 1. Global Elements (Header & Footer)

### Navigation Bar
- **Wordmark:** Temples & Towns
- **Links:** Stays, Experiences, Wellness
- **Actions (Guest):** Sign in, Join
- **Actions (User):** [Full Name], My Bookings, Sign out

### Utility Strip
- **Destinations:** Pondicherry · Bengaluru
- **Account Actions:** Sign in / Create account (or User Name / My Bookings / Sign out)

### Footer
- **Logo:** Temples & Towns
- **Bio:** Curated heritage stays in Pondicherry and Bengaluru, where culture meets modern comfort.
- **Columns:**
    - **Stays:** Search Rooms, Pondicherry, Bengaluru
    - **Account:** My Bookings, Sign in, Create account
    - **Support:** Help centre, Cancellation policy, Contact us
- **Bottom:** © 2026 Temples & Towns. All rights reserved. | Privacy · Terms

### WhatsApp Support
- **FAB Label:** Contact on WhatsApp
- **Number:** +91 99999 99999 (Placeholder)

---

## 2. Home Page

### Hero Section
- **Bullets:** ✦ Pondicherry · Bengaluru · Heritage Stays
- **Main Heading:** Where temples meet tranquility.
- **Sub-heading:** Handpicked hotels and heritage properties in South India's most storied cities.
- **Search Bar Fields:**
    - Destination (Pondicherry or Bengaluru)
    - Check-in (Date)
    - Check-out (Date)
    - Guests (Number)
    - **Button:** Search

### Destinations (Featured)
- **Eyebrow:** Where to stay
- **Pondicherry:**
    - Category: Heritage & Beach
    - Locations: French Quarter · Auroville · Promenade Beach
    - Link: Explore stays →
- **Bengaluru:**
    - Category: Garden City
    - Locations: Indiranagar · Koramangala · MG Road
    - Link: Explore stays →

### Value Propositions
- **Eyebrow:** Why Temples & Towns
- **Heading:** Stays that feel like they were made for you.
- **Features:**
    - **Heritage Properties:** Hand-curated colonial bungalows and temple-town retreats.
    - **Instant Confirmation:** Book and receive your confirmation in seconds — no waiting.
    - **24/7 Concierge:** WhatsApp support from check-in to check-out, always on.

---

## 3. Search Results Page

### Sidebar / Filters
- **Heading:** Filter stays
- **Fields:**
    - Min price (₹)
    - Max price (₹)
    - Room type (All, Standard, Deluxe, Suite)
    - Sort by (Recommended, Price: Low to High, Price: High to Low)
- **Button:** Apply filters
- **Action:** ← New search

### Results Header
- **Dynamic Text:** Showing [X] stays in [City] (or "Finding the best rooms for you...")

### Room Cards
- **Tags:** [Room Type]
- **Details:** [Room Name], [Room Type] · Max [X] guests
- **Description:** [Snippet of description]
- **Amenities:** [Chips for Wifi, AC, etc.]
- **Price:** From ₹[Amount] per night
- **Button:** View details

### Empty State
- **Icon:** 🔍
- **Heading:** No rooms found
- **Text:** Try adjusting your dates, destination, or filters.
- **Button:** Back to search

---

## 4. Room Details Page

### Header Area
- **Back Link:** ← Back to results
- **Room Name:** [Dynamic]
- **Badge:** [Room Type] Room

### Layout (Left Column)
- **Quick Info:** 📍 [City], 👥 Up to [X] guests, 🏷️ [Room Type]
- **About Section:**
    - Label: About this room
    - Text: [Room Description]
- **Amenities Section:**
    - Label: Amenities & facilities
    - List: [Wifi, AC, TV, Room Service, etc. with icons]
- **Photo Gallery:**
    - Label: Photo gallery
- **Policies Section:**
    - Label: Hotel policies
    - **Check-in:** From 2:00 PM. Early check-in subject to availability.
    - **Check-out:** Until 11:00 AM. Late check-out available on request.
    - **Cancellation:** Free cancellation up to 24 hours before check-in.
    - **ID required:** Valid government-issued photo ID required at check-in.

### Booking Sidebar (Right Column)
- **Price:** ₹[Amount] per night
- **Summary Rows:**
    - Check-in: [Date]
    - Check-out: [Date]
    - Guests: [X] Guests
    - Duration: [X] Nights
- **Total:** ₹[Amount]
- **Button:** Book now — Reserve this room
- **Footer Text:** You won't be charged yet — a 10-minute hold will be placed.

---

## 5. Checkout Page

### Header
- **Eyebrow:** Step 2 of 2
- **Heading:** Complete your booking
- **Timer Badge:** ⏱ Hold expires in [MM:SS]

### Booking Summary
- **Eyebrow:** Booking summary
- **Room Name:** [Dynamic]
- **Dates:** [Check-in] → [Check-out] ([X] nights)
- **Guests:** [X] guest(s)
- **Total Amount:** ₹[Amount]
- **Footer:** Includes all taxes and fees

### Payment Action
- **Button:** Pay now with Razorpay
- **Security Footer:** Secured by Razorpay · 256-bit SSL encryption

---

## 6. Booking Confirmation

### Success Visuals
- **Success Mark:** Checkmark icon
- **Heading:** Payment successful!
- **Text:** Your booking is confirmed. A receipt has been sent to [Email].

### Confirmation Card
- **Eyebrow:** Booking reference
- **Reference Code:** [Dynamic - e.g., TT-12345]
- **Rows:** Room, Check-in, Check-out, Guests
- **Total Paid:** ₹[Amount]

### Actions
- **Button:** View my bookings
- **Button:** Book another stay
- **Email Status:** Confirmation email sent · Check your inbox

---

## 7. My Bookings (Dashboard)

### Page Header
- **Heading:** My bookings
- **Action:** + New search

### Stats Bar
- **Total:** [X]
- **Confirmed:** [X]
- **Pending:** [X]
- **Total spent:** ₹[Amount]

### Tabs
- **Upcoming:** [X]
- **Past:** [X]
- **All:** [X]

### Booking Item Card
- **Header:** [Room Name]
- **Status Badges:** Pending, Confirmed, Cancelled, Expired, Failed
- **Details:** 📅 [Dates], 🌙 [X] nights, 👥 [X] guest(s), 📍 [City]
- **Reference:** Ref: [Code] (or "Awaiting payment")
- **Price Section:** ₹[Total Amount] (Breakdown: [X] night(s) × ₹[Rate])
- **Actions:**
    - Complete payment (for Pending)
    - Cancel (for Confirmed/Upcoming)

### Cancel Modal
- **Heading:** Cancel booking
- **Text:** Are you sure you want to cancel your booking for "[Room Name]" (Ref: [Code])? This action cannot be undone.
- **Actions:** Keep booking, Yes, cancel it

---

## 8. Authentication Pages

### Login Page
- **Heading:** Welcome back
- **Sub-heading:** Sign in to your account to manage bookings.
- **Fields:** Email address, Password
- **Button:** Sign in
- **Footer:** Don't have an account? Create one
- **Security:** SSL secured · Your data is never shared

### Registration (3-Step Flow)

#### Step 1: Details
- **Heading:** Create your account
- **Sub-heading:** Join to unlock curated stays and member rates.
- **Fields:** Full name, Email address, Phone number
- **Button:** Send verification code

#### Step 2: Verification
- **Heading:** Verify your email
- **Sub-heading:** Enter the 6-digit code we sent you to [Email].
- **Fields:** 6-digit code (OTP)
- **Button:** Verify code
- **Action:** Didn't receive the code? Resend

#### Step 3: Password
- **Heading:** Create your password
- **Sub-heading:** One last step — secure your account.
- **Fields:** Password, Confirm password
- **Note:** Must contain uppercase, lowercase, digit & special character
- **Button:** Create account

---
