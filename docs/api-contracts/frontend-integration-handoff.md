# KNOWALL Module 1 — Frontend API handoff

**Backend:** Flask (`localhost:5000`), PostgreSQL, SQLAlchemy. **Frontend:** Next.js App Router (`localhost:3000`). Single society, Green Valley Residency. 4 towers, 240 seed flats. No Docker, Redis or multi-society features.

## Single browser origin

Browser uses **relative** `/api/*` fetches to Next.js. Keep a Next.js rewrite from `/api/:path*` to `http://127.0.0.1:5000/api/:path*`. Browsers should not call port 5000 directly; avoid mixing `127.0.0.1` with `localhost` in browser URLs. Flask owns all authentication and business logic. Do not create a second Next.js session system.

## Auth lifecycle

1. `GET /api/auth/csrf` retrieves `csrf_token` and a cookie.
2. Include `X-CSRF-Token` for **every modifying API call**, even unauthenticated registration/login and multipart upload. Use `credentials: "same-origin"`.
3. `POST /api/auth/register` creates an **unverified applicant**, not a logged-in or approved resident. Registration causes verification email; in development `MAIL_DELIVERY_MODE=console`.
4. `POST /api/auth/login` returns `user` plus a **rotated** CSRF token. Store the new CSRF value in suitable in-memory app state (never the session cookie).
5. `GET /api/auth/me` gives login state. `GET /api/me/access` gives live roles/eligible memberships/effective permissions. Refetch after login, admin approval, correction, membership change, and tab refresh.
6. Logout returns a new guest CSRF token. Password reset invalidates previous sessions; on `401` return to login gracefully.
7. `403 CSRF_REQUIRED`: recover CSRF and present/retry appropriately; do not retry arbitrary mutations blindly if they might have succeeded.

**Never store passwords, session cookies or verification/reset tokens in localStorage.** Do not print private document contents or tokens to console or analytics.

## Implemented endpoints (from Phase 8 OpenAPI + Phase 9 access extension)

Source of truth: `backend/app/openapi.json` (served from Flask as `/openapi.json` and Swagger `/docs`). The endpoint map below is for navigation only; consult schemas and current code for request/response details.

- `GET   /api/health` — Health check
- `GET   /api/auth/csrf` — Get or refresh CSRF token
- `POST  /api/auth/register` — Register applicant account
- `POST  /api/auth/login` — Login and rotate CSRF token
- `GET   /api/auth/me` — View current account
- `POST  /api/auth/logout` — End session
- `POST  /api/auth/verification/resend` — Resend email verification
- `POST  /api/auth/password/forgot` — Request password reset
- `POST  /api/auth/verify-email` — Confirm email verification token
- `POST  /api/auth/password/reset` — Set new password and revoke prior sessions
- `GET   /api/residential/society` — Public single-society profile
- `GET   /api/residential/towers` — List Green Valley towers
- `GET   /api/residential/towers/{tower_id}/flats` — List flats in a tower; optional floor filter
- `GET   /api/residential/flats/{flat_id}` — Public flat reference details (no occupants)
- `GET   /api/me/profile` — Get current user profile
- `PATCH /api/me/profile` — Update display name or phone
- `GET   /api/me/memberships` — List current user membership history
- `GET   /api/me/access` — View current account roles and eligible memberships (not final RBAC)
- `GET   /api/me/households` — View own eligible household members (names/categories only)
- `POST  /api/membership/applications` — Create a self-registration draft
- `GET   /api/membership/applications/me` — List my applications
- `GET   /api/membership/applications/{application_id}` — Get my application detail
- `PATCH /api/membership/applications/{application_id}` — Edit draft or correction-requested application
- `POST  /api/membership/applications/{application_id}/submit` — Submit or resubmit for administrator review
- `POST  /api/invitations` — Invite a resident with a single-use token
- `GET   /api/invitations/me` — List invitations addressed to my verified email
- `POST  /api/invitations/accept` — Accept single-use invitation as matching verified email
- `POST  /api/documents/upload` — Upload private residence evidence for own application
- `GET   /api/documents/application/{application_id}` — List uploaded documents for application (owner/admin)
- `GET   /api/documents/{document_id}` — Read private document metadata
- `GET   /api/documents/{document_id}/file` — Download original private evidence as attachment
- `POST  /api/documents/{document_id}/ocr` — Run Surya OCR on demand; may be slow on CPU
- `GET   /api/documents/{document_id}/ocr` — View OCR run history for document
- `GET   /api/admin/applications` — Paged application verification queue
- `GET   /api/admin/applications/{application_id}` — View application, documents, OCR warnings, review history
- `POST  /api/admin/applications/{application_id}/decision` — Human reviewer approves, rejects or requests corrections
- `GET   /api/admin/memberships` — List memberships and computed access states
- `PATCH /api/admin/memberships/{membership_id}/status` — Suspend, revoke or reinstate a membership
- `GET   /api/admin/audit-logs` — Admin audit trail without private document content


## Required frontend UX contract

- Applicant: signup, login, email verify/resend, forgot/reset, selection of tower/flat, owner/tenant applications, invitation acceptance (including sponsored family), draft editing, submission, documents, OCR status, corrections, application-status timeline.
- Resident: membership cards, active/current household members, profile editing, resident dashboard; future module tiles may be visually present but cannot claim functionality.
- Administrator: application queue with pagination/status filters, detail and private evidence preview, side-by-side OCR comparisons/warnings, required manual-review confirmation, approval/rejection/correction actions, membership directory/status transitions, audit history.
- Do not show applicant PII or documents to unauthorized people. Private document URLs need the authenticated browser session and must be handled with appropriate no-store/privacy behavior.
- Validation errors use `{ "error": {"code":"...","message":"...","fields": {"field":"..."}} }` when field errors are present. Handle `400`, `401`, `403`, `404`, `409`, `413`, `415`, `429`, `503`, and network interruptions distinctly.
- OCR can take time on CPU. Show pending state, prevent accidental duplicate submissions, support retry when applicable, and indicate OCR never authenticates a document.
- Never fabricate a successful API state with local React state. For design fixtures, label them as nonfunctional and remove them for the integrated build.

## Completion checks

- Backend Pytest and `db current` green, and relevant endpoints manually exercised via Swagger in the final verification phase.
- Frontend typecheck, lint, production build and component tests pass.
- End-to-end flows: unverified applicant, successful approval, rejection/correction, sponsored family, owner/tenant coexistence, expired invitation, OCR warning, unauthorized admin, suspended resident, password reset, logout, unexpected backend error.
- Document remaining limitations openly. Swagger is a tool for manual verification; it does not replace Pytest or frontend end-to-end tests.
