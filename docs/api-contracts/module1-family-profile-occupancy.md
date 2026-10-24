# KNOWALL Module 1 — Personal Profile, Family Relationships & Occupancy

Version: 0.9.1. Single-society Green Valley Residency; this is an **additive enhancement** after Phase 9.

## Data model

| Model | New field | Meaning |
|---|---|---|
| `users` | `date_of_birth DATE NULL`, `occupation VARCHAR(100) NULL` | Optional **private** personal fields, visible on own `auth/me` and `me/profile`, not to other households or residents. |
| `invitations` | `relationship_to_sponsor VARCHAR(24) NULL` | Suggested relationship label entered by inviter. Only family invitations. |
| `membership_applications` | `relationship_to_sponsor VARCHAR(24) NULL` | Applicant-confirmed family relationship to sponsor; editable while DRAFT/NEEDS_CORRECTION. |
| `membership_applications` | `declared_current_occupant BOOLEAN NULL` | Applicant's self-declaration only. **Not** voting authority or verified residence. |
| `memberships` | `relationship_to_sponsor VARCHAR(24) NULL` | Copied when family application is approved; supports household-scoped sponsor graph. |
| `memberships` | `is_current_occupant BOOLEAN NULL` | Only admin-confirmed, `NULL` = unknown. Independent of OWNER/TENANT category. |
| `memberships` | `occupancy_confirmed_at`, `occupancy_confirmed_by_user_id` | Evidence of when and by whom occupancy was confirmed. Audited separately. |

Relationships: `SPOUSE`, `CHILD`, `PARENT`, `SIBLING`, `GRANDPARENT`, `GRANDCHILD`, `OTHER`. These names mean **relationship to the owner/tenant sponsor**, not necessarily to all other family members. The tree is a verified **household sponsor graph**, not a genealogical genealogy database; do not infer cousin/parent/spouse relationships between two dependents.

Legacy `NULL` relations and occupancy are preserved as **unknown**. Never backfill guesses based on names or tenant/owner status.

## API routes and bodies

### PATCH `/api/me/profile` — logged-in account only

```json
{"display_name":"Rahul Sharma","phone":"+919876543210","date_of_birth":"1991-08-16","occupation":"Engineer"}
```

Both new fields optional and can be cleared with `null`. DOB: `YYYY-MM-DD`, 1900–today. Occupation: at most 100 chars. Fields appear in `GET /api/me/profile` and `GET /api/auth/me` for current user. Not published to other households. A profile update writes an audit log containing the changed field **names**, not private values.

### POST `/api/invitations` — member/society admin invites family

```json
{
  "flat_id": "<real flat UUID>",
  "household_id": "<sponsor household UUID>",
  "sponsor_membership_id": "<active owner/tenant membership UUID>",
  "category": "FAMILY_MEMBER",
  "email": "family-demo@example.test",
  "relationship_to_sponsor": "SPOUSE"
}
```

`relationship_to_sponsor` optional for legacy compatibility. The token is emailed; not returned by create-invitation endpoint. Existing sponsor and same-household authorization checks apply.

### POST `/api/invitations/accept` — intended invitee

```json
{
  "token": "<actual one-time email token>",
  "relationship_to_sponsor": "SPOUSE",
  "declared_current_occupant": true
}
```

Invitee may confirm/override the suggested family relationship and declare whether they actually live at the flat. Optional for legacy callers; frontend **should prompt explicitly**. A future stricter submission rule can be introduced after older client workflows have migrated.

### PATCH `/api/membership/applications/{id}` — applicant, draft/correction only

```json
{
  "relationship_to_sponsor": "CHILD",
  "declared_current_occupant": true
}
```

`relationship_to_sponsor` is prohibited for OWNER/TENANT applications. Any applicant can set `declared_current_occupant`. Admin application read responses include both fields. Approval copies family relationship but **does not set verified occupancy**.

### GET `/api/me/households` — household-scoped

Preserves existing payload and adds to each member: `membership_id`, `sponsor_membership_id`, `relationship_to_sponsor`, `is_current_occupant`. Returns **only active eligible members** in households to which the authenticated verified resident belongs. No birth dates, occupation, phone, email or passwords.

### GET `/api/me/family-tree` — household-scoped sponsor graph

```json
{
  "households": [
    {
      "household_id": "<owner household UUID>",
      "household_label": "Owner household",
      "flat": {"id":"<flat UUID>","tower_id":"<tower UUID>","tower_name":"B","flat_number":"402","floor_number":4},
      "members": [
        {"user_id":"<Rahul UUID>","display_name":"Rahul","category":"OWNER","membership_id":"<Rahul membership UUID>","sponsor_membership_id":null,"relationship_to_sponsor":null,"is_current_occupant":null},
        {"user_id":"<Priya UUID>","display_name":"Priya","category":"FAMILY_MEMBER","membership_id":"<Priya membership UUID>","sponsor_membership_id":"<Rahul membership UUID>","relationship_to_sponsor":"SPOUSE","is_current_occupant":null}
      ],
      "relationships":[{"sponsor_membership_id":"<Rahul membership UUID>","family_membership_id":"<Priya membership UUID>","relationship_to_sponsor":"SPOUSE"}]
    }
  ]
}
```

Only a verified resident with an eligible membership can view it; a resident from a different household at B-402 cannot see the owner household's sponsor graph. Membership suspension or sponsor ineligibility removes access.

### PATCH `/api/admin/memberships/{membership_id}/occupancy`

```json
{"is_current_occupant":false,"reason":"Owner lives elsewhere; tenancy documentation reviewed."}
```

Admin-only, requires active membership and a reason. Writes `is_current_occupant`, `occupancy_confirmed_at`, `occupancy_confirmed_by_user_id` and a separate audit action. It does **not** change existing membership permissions or create a vote.

### PATCH `/api/admin/memberships/{membership_id}/relationship`

```json
{"relationship_to_sponsor":"SIBLING","reason":"Relationship corrected following member confirmation."}
```

Admin-only and family-member membership only. `null` clears an incorrect legacy relationship to unknown. Does **not** change sponsor membership or household and does not infer any other edges. Audit action: `FAMILY_RELATIONSHIP_CORRECTED`.

## Current voting boundary

Module 1 provides independently verified account, household, membership category, sponsor and optional administrator-confirmed physical occupancy. **It does not confer voting rights.** Module 2 sets voting policy per poll, may take membership eligibility/occupancy snapshots and must enforce ballot uniqueness and society-specific bylaws. An owner's `is_current_occupant=false` does not negate their ownership; a tenant's `true` does not automatically grant owner-only formal votes.

## Frontend changes

1. Add date-of-birth and occupation inputs to editable personal profile; allow clear, show validation/errors.
2. Family invitation form: ask for relationship to sponsor; invitation acceptance: ask invitee to confirm it.
3. Onboarding wizard: ask "Do you currently live in this flat?" but label it **self-declared**, not verified.
4. Household view: render `members` and `relationships` of `/api/me/family-tree`; do not infer unsupported edges.
5. Admin application detail: show applicant's declared occupancy and family relation for manual review.
6. Admin membership detail: include separate verified occupancy control requiring a reason; show confirmed-at. Include audited family relation correction.
7. Keep private profile fields out of the household tree and directory.
8. Treat all `null` values as unknown, not `false` or `OTHER`.

All write requests still require Flask's session cookie and `X-CSRF-Token`.
