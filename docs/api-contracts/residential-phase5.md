# KNOWALL Module 1 — Phase 5 Residential API contract

Flask origin: `http://localhost:5000` locally; Next.js frontend uses its existing same-origin `/api/*` rewrite.

## Public directory (no identity data)

- `GET /api/residential/society` → `200` `{"society":{"name":"Green Valley Residency","address":"...","locality":"...","city":"..."}}` or `404 SOCIETY_NOT_CONFIGURED` if seed not loaded.
- `GET /api/residential/towers` → `200` `{"towers":[{"id":"uuid","name":"A"}]}` (sorted).
- `GET /api/residential/towers/<uuid>/flats?floor=4` → `200` `{"flats":[{"id":"uuid","tower_id":"uuid","tower_name":"B","flat_number":"402","floor_number":4}]}`. The `floor` parameter is optional; invalid floor yields `400 VALIDATION_ERROR`; unknown tower yields `404 TOWER_NOT_FOUND`.
- `GET /api/residential/flats/<uuid>` → `200` `{"flat":{...}}` or `404 FLAT_NOT_FOUND`.

Never infer available occupancy from the public flat list; **all known flats are selectable reference data**, not confirmation that a unit is vacant. No names, phone numbers, applications or household/member data appear on public routes.

## Current user

Requires Flask cookie session (`knowall_session`) from `POST /api/auth/login`.

- `GET /api/me/profile` → `200` `{"user":{...}}` with same public user fields as `GET /api/auth/me`.
- `PATCH /api/me/profile` with body `{"display_name":"Updated Name", "phone":"+919999888777"}` → `200` `{"user":{...}}`. Either property may be omitted; `phone: null` clears the phone. `display_name` must be 2–120 chars; phone must be 7–15 digits with optional leading `+`. The endpoint rejects unknown fields, including `email`, `role`, `id`, `email_verified`, etc. Requires `X-CSRF-Token` from `GET /api/auth/csrf`; invalid fields → `400 VALIDATION_ERROR`; unauthenticated → `401 AUTH_REQUIRED`.
- `GET /api/me/memberships` → `200` `{"memberships":[{"id":"uuid","household_id":"uuid","household_label":"Owner Home","flat":{...},"category":"OWNER","status":"ACTIVE","access_state":"ACTIVE","valid_from":"2026-10-01","valid_until":null,"sponsor_membership_id":null}]}`. Includes only the signed-in person's memberships, including historical/inactive ones; no other users' contact details.
- `GET /api/me/households` → `200` `{"households":[{"id":"uuid","label":"Demo Household","flat":{...},"members":[{"user_id":"uuid","display_name":"Rahul Demo","category":"OWNER"}]}]}`. Requires email verification, current resident/committee/admin role and an active, in-date, eligible membership. Family memberships require an eligible active sponsor in the same household. Otherwise → `403 RESIDENT_ACCESS_REQUIRED`. **Other residents' email addresses and phones are never exposed.**
- `GET /api/me/access` → `200` `{"user_id":"uuid","email_verified":true,"roles":["RESIDENT"],"verified_resident":true,"active_memberships":[...]}`. A convenience identity/access summary; **do not use browser-provided roles as authorization for modifying APIs**. Final server-side permission policies are Phase 9.

## Error shape

```json
{"error":{"code":"VALIDATION_ERROR","message":"Check the submitted fields.","fields":{"phone":"Use 7 to 15 digits..."}}}
```

## Important distinctions

- Membership status is stored as one of `ACTIVE`, `SUSPENDED`, `EXPIRED`, `REVOKED`.
- `access_state` is a **computed** field. It can also be `NOT_STARTED` or `SPONSOR_INELIGIBLE`, or `EXPIRED` when a still-stored ACTIVE membership has passed its date. The API does not mutate lifecycle state on reads.
- An owner and tenant can coexist at the same flat in separate households.
- The frontend must not let users browse arbitrary household IDs; the API derives household access from the current authenticated user.
- API contracts in `/openapi.json`; interactive Swagger UI at `/docs` on Flask origin.
