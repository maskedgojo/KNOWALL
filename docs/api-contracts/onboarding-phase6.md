# KNOWALL Module 1 — Phase 6 API contract

Base prefix: `/api`. Use signed, HTTP-only `knowall_session` cookie. Send `X-CSRF-Token` from `/api/auth/csrf` on every POST/PATCH. All errors have the existing `{ "error": { "code": "...", "message": "..." } }` format. The endpoints are in `/docs` and `/openapi.json`.

## 1. Create a self-application

`POST /api/membership/applications` (signed in)

```json
{
  "flat_id": "UUID from /api/residential/...",
  "category": "OWNER",
  "applicant_notes": "Optional explanation"
}
```

Category is `OWNER` or `TENANT`. For TENANT, optional `requested_valid_from` and `requested_valid_until` are ISO dates. `FAMILY_MEMBER` must accept a verified sponsor invitation instead. Success **201**: `{ "application": { "id": "...", "status": "DRAFT", "flat": { ... }, "category": "OWNER", "evidence_required": true, "documents_uploaded": 0, ... } }`. `409` on duplicate open application or active membership, `404` for unknown flat. Draft creation does not require verified email; submission does.

## 2. List, view, and modify your own applications

- `GET /api/membership/applications/me` → `{ "applications": [ { ... } ] }`.
- `GET /api/membership/applications/{application_id}` → `{ "application": { ... } }`. Unknown or another user's ID returns **404** (never reveals others' data).
- `PATCH /api/membership/applications/{application_id}` accepts `flat_id`, `category`, `applicant_notes`, `requested_valid_from`, `requested_valid_until`. Only `DRAFT` or `NEEDS_CORRECTION`. Invitations bind flat/category, so those fields cannot change for invited users. Success **200**. Others **409/403/404**.
- `POST /api/membership/applications/{application_id}/submit` body `{}`; verified email required. Moves draft/correction to `PENDING`; rechecking sponsor eligibility for family. **200** `{ "application": { ... "status":"PENDING" ... } }`; **403** if email unverified; **409** if invalid state/sponsor.

An application is **not** a membership. Owner/tenant `evidence_required: true` is a reminder that Phase 7 documents and Phase 8 human approval are still needed.

## 3. Create invitation

`POST /api/invitations` requires signed-in email-verified sender.

Admin owner/tenant example:

```json
{"flat_id":"<uuid>","category":"TENANT","email":"newtenant@example.test"}
```

Sponsor-family example:

```json
{
  "flat_id":"<uuid>",
  "household_id":"<uuid>",
  "sponsor_membership_id":"<active-owner-or-tenant-membership-uuid>",
  "category":"FAMILY_MEMBER",
  "email":"family@example.test"
}
```

Sends a private 7-day link to the intended email. Success **201** `{ "invitation": { "id", "email", "flat_id", "category", "expires_at" } }`. Raw token never appears in API response or persisted plain-text. Unauthorized senders **403**; mismatched household/sponsor **400/403**; rate-limited **429**. If email delivery fails, the invitation is revoked and route returns **503**.

## 4. Invitation list & acceptance

`GET /api/invitations/me` — signed-in, email-verified; lists invites addressed to the exact account email, not their raw tokens. Status `ACTIVE`, `USED`, `EXPIRED`, or `REVOKED`.

`POST /api/invitations/accept` — signed-in, email-verified, body:

```json
{"token":"raw token from emailed link"}
```

Success **201** returns a bound `DRAFT` application. Token is atomically consumed in a database transaction. Bad/expired/replayed token **400/409**, wrong email **403**, existing equivalent application **409**, ineligible family sponsor **409**. User must subsequently `submit` the draft; they do not receive resident access immediately.

## Key application response fields

`id`, `flat`, `category`, `status`, `household_id`, `sponsor_membership_id`, `invitation_id`, `resulting_membership_id`, `applicant_notes`, `requested_valid_from`, `requested_valid_until`, `evidence_required`, `documents_uploaded`, `created_at`, `submitted_at`, `decided_at`.

## Integration boundaries

Later Phase 7 will upload documents to an application and write OCR findings. Later Phase 8 will implement admin decisions, approval transactions and actual memberships, including checks for owner/tenant document evidence. Phases 9–10 will harden RBAC and full end-to-end testing. Frontend should rely on `status` rather than assume submitted applications are approved.
