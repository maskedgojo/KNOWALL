# KNOWALL Module 1 — Family self-activation and exception evidence (API contract)

## Accepted V1 policy

- Verified OWNER / TENANT with a current eligible membership may invite a FAMILY_MEMBER to that exact household and flat.
- New family acceptance **directly creates an ACTIVE membership** in one transaction. No family application draft, approval, required document, or Surya OCR.
- `relationship_to_sponsor` is declared by sponsor/invitee (not independently verified); `declared_current_occupant` is the invitee's self-report. `is_current_occupant` remains `null` until an admin separately confirms it.
- OWNER and TENANT invitation acceptance still creates DRAFT applications, with human review and evidence.
- Legacy family applications are **not backfilled or automatically approved**. Existing pending legacy applications may still be handled via the previous administrator workflow; a new family invitation cannot be redeemed while a matching open legacy family application remains unresolved.
- Household membership does not confer voting rights. Voting remains in Module 2.

## POST /api/invitations/accept (existing endpoint)

Requires logged-in, active account with verified email, session cookie, and `X-CSRF-Token`.

Request:
```json
{"token":"TOKEN_FROM_EMAIL","relationship_to_sponsor":"SPOUSE","declared_current_occupant":true}
```
For family, relationship is required unless supplied in the invitation itself. For Owner/Tenant, omit `relationship_to_sponsor`.

New successful family response **201**:
```json
{
 "outcome":"FAMILY_MEMBERSHIP_ACTIVATED",
 "application":null,
 "membership":{
   "id":"NEW_UUID","household_id":"HOME_UUID","category":"FAMILY_MEMBER",
   "status":"ACTIVE","access_state":"ACTIVE","relationship_to_sponsor":"SPOUSE",
   "sponsor_membership_id":"SPONSOR_MEMBERSHIP_UUID",
   "declared_current_occupant":true,"is_current_occupant":null,
   "valid_from":"2026-10-23","valid_until":null,"flat":{},"household_label":"Owner household",
   "occupancy_confirmed_at":null
 },
 "access":{"verified_resident":true,"permissions":["identity.households.read"]}
}
```
`membership.flat` and `access.permissions` above are abbreviated for illustration; always read the real OpenAPI spec. `valid_until` is limited to sponsor's current validity date, if set.

Owner/Tenant successful response **201** (previous `application` is retained):
```json
{"outcome":"APPLICATION_DRAFT_CREATED","application":{"id":"UUID","category":"TENANT","status":"DRAFT"},"membership":null}
```

Error codes: `EMAIL_VERIFICATION_REQUIRED` (403), `INVITATION_EMAIL_MISMATCH` (403), `RELATIONSHIP_REQUIRED` (400), `INVALID_INVITATION` (400/409), `SPONSOR_INELIGIBLE` (409), `ALREADY_A_RESIDENT` (409), `APPLICATION_ALREADY_OPEN` (409), `MEMBERSHIP_CONFLICT` (409), `HOUSEHOLD_MISMATCH` (409). Consumed invitations cannot be reused.

**Frontend:** On `outcome === "FAMILY_MEMBERSHIP_ACTIVATED"`, invalidate and reload `GET /api/auth/me`, `GET /api/me/access`, and `GET /api/me/memberships`, then navigate to the resident dashboard. Do not show family document/OCR/application submission/admin approval screens. Owner/Tenant must still navigate to their draft application onboarding. Never infer the result merely from the selected category.

## GET /api/admin/households (NEW)

Admin-only, paginated `?limit=30&offset=0`. Returns `{households:[{household_id,household_label,flat,members:[...]}], pagination}`. Each member has `membership_id`, `display_name`, `category`, `membership_status`, `access_state`, `relationship_to_sponsor`, explicit `sponsor_membership_id`, `sponsor_display_name`, `declared_current_occupant`, `is_current_occupant`, and membership validity dates. No email, phone, date of birth, occupation, credentials, or private files. The endpoint **never merges owner and tenant households** on a shared flat.

## Exception evidence lifecycle (NEW)

One open request per membership. No automatic status restriction during `REQUESTED` or `SUBMITTED`. One attachment per request; to ask for more/another document, resolve the current request and create a new one. Requests and decisions are audited.

1. `POST /api/admin/memberships/{membership_id}/evidence-requests` admin + CSRF. JSON:
   ```json
   {"reason":"A discrepancy in household information requires clarification.", "evidence_needed":"Any appropriate non-sensitive record confirming residence."}
   ```
   Response 201 `{request:{id,membership_id,reason,evidence_needed,status:"REQUESTED",...}}`
2. `GET /api/me/evidence-requests` authenticated member; `GET /api/admin/evidence-requests?limit=30&offset=0` admin. Returns requests and statuses. Render `REQUESTED` as an in-app notification. Do not reveal other users' requests.
3. `POST /api/me/evidence-requests/{entry_id}/upload` member + CSRF, `multipart/form-data` with `file` (one PDF/JPG/PNG <=5 MiB). Uses existing MIME/file-content validation, private random file storage, no public URLs. Response 200, status `SUBMITTED`.
4. `GET /api/member-evidence/{entry_id}/file` authenticated owning member or authorized admin only; secure download, no cache.
5. `POST /api/admin/evidence-requests/{entry_id}/resolve` admin + CSRF:
   ```json
   {"decision":"ACCEPTED","review_note":"Evidence was reviewed and found sufficient."}
   ```
   `ACCEPTED` and `REJECTED` require `SUBMITTED`; `CANCELLED` requires `REQUESTED`. Returns status and retention deadline. No membership status auto-change.
6. `python -m flask --app app:create_app purge-expired-member-evidence` performs **explicit attachment purging after 90 days from resolution**, retaining limited metadata and audit history. Schedule this CLI according to the deployment operator's retention policy and any applicable legal requirements. Do not log file contents or send to OCR automatically.

Request object `document` is `null` before upload or after purge. The client can poll/list own requests after login; no new push/notification service was introduced.

## Test and migration cautions

- Migration `7cfa926bd410` requires `5b1f8d7ac921` as its parent. It adds nullable `memberships.declared_current_occupant` and a single `member_evidence_requests` table, plus open-request uniqueness index.
- **No legacy family application is changed by migration**; existing invitations retain old recorded status/history. An unconsumed family invitation can be redeemed under the new policy after deployment, provided all eligibility rules still pass.
- Effective resident access is calculated live. Suspension/revocation/expiry of sponsor makes dependent family access ineligible even while the dependent membership retains stored status `ACTIVE` for audit/history. This does not automatically grant voting rights.
- Verify the exact PostgreSQL row locking/duplicate acceptance invariant in a dedicated integration environment with two concurrent clients; SQLite in-memory unit tests are not a concurrency substitute.
