# KNOWALL Module 1 — Phase 4B API contract

**Implementation:** Flask blueprint, `/api/auth/*`, using the existing `auth_tokens` table. No new database migration.

## Client conventions

- Browser calls use the Next.js same-origin `/api/...` rewrite (which forwards to Flask).
- All `POST` endpoints use JSON, and **require a current `X-CSRF-Token` header** from `GET /api/auth/csrf`.
- Session cookie `knowall_session` remains `HttpOnly`, with `SameSite=Lax`; `Secure` is required for HTTPS deployment.
- Do **not** store an authentication token in localStorage or in application logs.
- One-time email links point to the Next.js pages `/verify-email?token=...` and `/reset-password?token=...`; these are **frontend URLs**, not GET API endpoints. The frontend takes the query token and submits it as a POST JSON body.
- Tokens are valid once: email verification **24 hours**, password reset **30 minutes**.
- Never render token values into server logs, analytics, referrer headers, or third-party scripts; strip the token from the browser URL as soon as consumed. Set `Referrer-Policy: no-referrer` on these pages.
- API errors use `{ "error": { "code": "...", "message": "...", "fields": { ... } } }`.

## Endpoints

### `POST /api/auth/verification/resend`
Request: `{ "email": "name@example.test" }`
Response `202`: `{ "message": "If the account is eligible, an email will be sent shortly." }`.
The response is the same for unknown, suspended, already-verified and cooldown-limited accounts. Invalid email format returns `400 VALIDATION_ERROR`; per-IP abuse threshold returns `429 RATE_LIMITED`.

### `POST /api/auth/verify-email`
Request: `{ "token": "raw-one-time-token" }`
Response `200`: `{ "message": "Email verified successfully." }`.
Invalid, expired, revoked, previously used tokens: `400 INVALID_OR_EXPIRED_TOKEN`.
Frontend should query `GET /api/auth/me` after verification if an account session is already active.

### `POST /api/auth/password/forgot`
Request: `{ "email": "name@example.test" }`
Response `202`: `{ "message": "If the account is eligible, an email will be sent shortly." }`.
The response is the same whether the email is registered or not. Invalid email: `400 VALIDATION_ERROR`, IP threshold: `429 RATE_LIMITED`.

### `POST /api/auth/password/reset`
Request: `{ "token": "raw-one-time-token", "new_password": "12-or-more-characters" }`
Response `200`: `{ "message": "Password reset successfully. Please sign in again.", "csrf_token": "..." }`.
Invalid, expired, revoked or used token: `400 INVALID_OR_EXPIRED_TOKEN`.
Same password as current hash: `400 PASSWORD_REUSE_NOT_ALLOWED` (token remains unused).
New password under 12 or over 128 characters: `400 VALIDATION_ERROR`.
The old password stops working and **previously issued Flask sessions become invalid on their next authenticated request**, including in other browsers. Do not automatically log the user in after resetting.

### Registration integration
`POST /api/auth/register` still creates an unverified account (`201`), and now attempts to email a one-time verification link. Email delivery failure does not delete the account; the user can request a resend.

### Session compatibility
`POST /api/auth/login` now binds the session to a keyed fingerprint of the password hash. Existing sessions from deployments before Phase 4B will need to sign in again after upgrading; no new database table/column is required.

## Error codes and UX

- `CSRF_REQUIRED` (403): refresh the CSRF token and retry an intended action.
- `RATE_LIMITED` (429): avoid automatic repeated requests; ask the user to try later.
- `INVALID_OR_EXPIRED_TOKEN` (400): show an expired/invalid-link message, with a request-new-link path.
- `VALIDATION_ERROR` (400): attach field messages to inputs.
- `AUTH_REQUIRED` (401): return to the sign-in screen.

## Delivery modes

- `MAIL_DELIVERY_MODE=console`: **local Flask debug only**. Sensitive verification/reset URLs are printed to the backend log; never run this in production.
- `MAIL_DELIVERY_MODE=smtp`: uses standard Python `smtplib` with TLS (`SMTP_SECURITY=starttls` on port 587, or `ssl` typically on 465).
- `MAIL_DELIVERY_MODE=memory`: available in tests only; messages live in `app.extensions["knowall_outbox"]`.

**Simple V1 rate limits:** one active email per account/purpose per 60 seconds; 12 requests per IP per recovery operation per 15 minutes using a process-local counter. This is suitable for the current one-server academic prototype, **not a distributed/global rate limit**. Later deployments with multiple workers would require a shared limiter, or another centralized mechanism.
