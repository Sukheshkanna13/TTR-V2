# Code Audit Report: Garbage & Unused Code

## Overview
This audit was conducted to identify unused, deprecated, or "garbage" code in the repository. The primary focus was on the recently removed **Interakt WhatsApp** feature, along with a general sweep for other dead code.

## 1. Interakt WhatsApp Integration (Removed Feature)
Although the Interakt feature was removed, several residual references and files still exist in the codebase. These should be cleaned up.

### `core/tasks.py`
- The entire file currently consists of the `send_whatsapp_message` background task, which relies on the deprecated Interakt API.
- **Recommendation:** If no other tasks are planned for the `core` app, this file can be completely deleted. Otherwise, the `send_whatsapp_message` function and its imports (`requests`, `settings`) should be removed.

### `accounts/views.py`
- **Location:** `RegisterView` (around line 292).
- **Issue:** A call to `async_task("core.tasks.send_whatsapp_message", ...)` is made after a user registers to send a WhatsApp welcome message. This code is now non-functional.
- **Recommendation:** Remove this `async_task` block.

### `payments/views.py`
- **Location:** `payment_callback` view (around lines 268 and 414).
- **Issue:** Calls to `async_task("core.tasks.send_whatsapp_message", ...)` are made to queue a WhatsApp booking confirmation message after successful payment.
- **Recommendation:** Remove these `async_task` blocks.

## Summary of Actions Needed
1. [ ] **Delete** `core/tasks.py` (or remove the `send_whatsapp_message` function if other tasks are added).
2. [ ] **Remove** the `async_task` WhatsApp welcome message in `accounts/views.py`.
3. [ ] **Remove** the `async_task` WhatsApp booking confirmation in `payments/views.py`.

*(No other significant blocks of dead code or orphaned files were detected during this audit pass.)*
