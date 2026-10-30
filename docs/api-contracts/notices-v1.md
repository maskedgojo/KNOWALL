# KNOWALL — Official Notices V1

**Audience:** society-wide. **Publisher:** a verified, active `SOCIETY_ADMIN` with `society.notices.manage`. **Readers:** accounts that currently have `society.notices.read`. No acknowledgements, attachments, notifications, or voting.

The canonical machine-readable contract is `backend/app/openapi.json`. This document records the lifecycle rules used by the implementation.

## Authorization

- Management routes are under `/api/admin/notices` and require `society.notices.manage`. That code is granted only to a verified, active Society Admin and does not require a resident membership.
- Read routes are `GET /api/notices` and `GET /api/notices/{notice_id}` and require `society.notices.read`.
- Read permission does not allow create, edit, publish, archive, or replacement.
- Management permission does not grant resident read access. A Society Admin without an eligible membership uses the admin routes to review notices.
- `PLATFORM_ADMIN` and `COMMITTEE_MEMBER` do not receive `society.notices.manage`. A committee member with an eligible membership can still read through the existing resident permission.
- Every mutation requires the existing `X-CSRF-Token` header. Anonymous requests receive `401`. A missing permission receives `403`.

## Society scope

The server loads `society_profile` id `1` and stores that integer on `notices.society_id`. Clients cannot submit `society_id`. If the profile row is missing, the API returns `404` / `SOCIETY_NOT_CONFIGURED`.

## Lifecycle

| State | Editable | Resident visible | Allowed next step |
|---|---|---|---|
| `DRAFT` | Title, body, and expiry | No | Publish, or archive |
| `PUBLISHED` | No | Yes, until expiry | Archive, or create a replacement draft |
| `ARCHIVED` | No | No | None. Archive is terminal |

- Expiry is optional. `expires_at: null` means the notice does not expire by time.
- Expiry is evaluated on each read against server time. It does not change `status` and it does not archive the notice.
- A published notice with `expires_at` in the past stays `PUBLISHED`, remains available to managers, and is hidden from readers with `404` / `NOTICE_NOT_FOUND`.
- Publication rejects an expiry that is not in the future.
- Published title, body, and expiry are immutable. A correction is `POST /api/admin/notices/{id}/replacements`, which creates a new draft copied from a notice that has already been published. The source notice is not edited and is not archived.
- A draft that was never published cannot be replaced. Archive it instead. V1 has no delete.
- There is no unarchive operation.

## Audit

Successful create, draft update, publish, archive, and replacement append a row to the existing `audit_logs` table. `entity_type` is `NOTICE` and `entity_id` is the notice UUID. `details` contains the title, status, expiry, replacement id, and the previous status where relevant. The notice body is not copied into the audit row. These rows appear in the existing `GET /api/admin/audit-logs` response.

## Validation

- `title`: 3–160 characters after trimming.
- `body`: 1–8000 characters after trimming.
- `expires_at`: `null` or a timezone-aware ISO timestamp. A naive timestamp is rejected.
- Unknown JSON fields, including `society_id`, are rejected.
- Publish, archive, and replacement bodies must be empty JSON objects.

## Manual acceptance not yet run

The migration `c3a91e7b4d20` has not been applied to the project database. Browser acceptance is still outstanding:

1. Sign in as the Society Admin and create, edit, publish, and archive a notice.
2. Sign in as an eligible resident and confirm only the published, unexpired, unarchived notice is visible.
3. Confirm a platform admin cannot open notice management.
