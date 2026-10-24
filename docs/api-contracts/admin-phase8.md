# KNOWALL — Phase 8 Administrator API Contract

Single society: Green Valley Residency. Auth: Flask signed session cookie. **All POST/PATCH requests require `X-CSRF-Token`**, obtained from `GET /api/auth/csrf` and refreshed after login.

## Admin authorization

Endpoints below require a signed-in, active, email-verified user with an unrevoked `SOCIETY_ADMIN` or `PLATFORM_ADMIN` role. No resident or applicant can use them. An administrator cannot decide their own membership application. Server-side authorization is authoritative; hiding UI controls is not sufficient.

## Application reviews

### `GET /api/admin/applications?status=PENDING&limit=30&offset=0`

Returns `applications` with applicant identity, category, flat, state, document count and timestamps; `pagination` with `total`, `limit`, `offset`. `status` is optional and must be one of `DRAFT`, `PENDING`, `IN_REVIEW`, `NEEDS_CORRECTION`, `APPROVED`, `REJECTED`. `limit` is 1–100; `offset` ≥ 0.

### `GET /api/admin/applications/{application_id}`

Returns `application` with details, uploaded document metadata, private download URLs, the latest OCR candidate fields/comparisons/warnings per document, and append-only review history. OCR is **not proof of identity**; the administrator must inspect the original evidence.

### `POST /api/admin/applications/{application_id}/decision`

```json
{
  "decision": "APPROVED",
  "document_reviewed": true,
  "acknowledge_ocr_warnings": true
}
```

Or:

```json
{
  "decision": "NEEDS_CORRECTION",
  "reason": "The flat number is not legible. Please submit a clearer occupancy letter."
}
```

`decision` is `APPROVED`, `REJECTED`, or `NEEDS_CORRECTION`. A nonempty `reason` is required for rejection/correction; optional for approval. Approval of owner/tenant requires at least one current (not soft-deleted) document plus `document_reviewed: true`. If any saved OCR run reports a failed state or warnings, `acknowledge_ocr_warnings: true` is required. OCR is optional: a missing or failed run does not automatically reject a readable, manually inspected document. Family membership requires an eligible active, same-household owner/tenant sponsor and does not require a document by default. Tenant approval requires requested validity dates and cannot be approved after its end date.

On approval, a single database transaction creates/reuses the appropriate household, inserts one active membership, assigns a `RESIDENT` role if needed, writes an `ApplicationReview`, updates the application and records an audit event. Correction/rejection writes a review and status change but does **not** create a membership.

Only `PENDING` / `IN_REVIEW` applications can receive decisions; repeated or racing decisions return 409. The `resulting_membership_id` is included after approval. Failures return `{ "error": { "code": "...", "message": "..." } }`.

## Membership management

### `GET /api/admin/memberships?status=ACTIVE&limit=30&offset=0`

Returns paged `memberships` with user details, household and flat data, stored `status` and computed `access_state`.

### `PATCH /api/admin/memberships/{membership_id}/status`

```json
{ "status": "SUSPENDED", "reason": "Administrative review required" }
```

Supported transitions: `ACTIVE → SUSPENDED` or `REVOKED`; `SUSPENDED → ACTIVE` or `REVOKED`. No direct revival from `REVOKED` or `EXPIRED`; expired tenancy should use a new renewal application. Reinstatement checks the account, dates, and family sponsorship. The `RESIDENT` role is synchronized with active eligible memberships. Sponsored family membership eligibility is computed dynamically when its sponsor becomes ineligible.

### `GET /api/admin/audit-logs?limit=30&offset=0`

Returns audit events without private document contents or authentication secrets.

## Expected user-interface behavior

Use admin-only navigation; show status filters and paged queues. In the detail screen, display the original private document and its OCR mismatch indicators side by side. Confirmation dialogs should require a reason for negative decisions. Show loading/errors on 400, 401, 403, 404, 409 and 503 responses. After successful approval, refresh membership data and `GET /api/me/access`; never grant access merely because the button was clicked.

## Planned follow-up (Phase 9)

Centralize authorization decorators across all modules; cross-module permission contracts; account-level/role management; full end-to-end browser testing. Do not treat Phase 8 as completing Phase 9 automatically.
