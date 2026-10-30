# Admin moderation v1 — discussions, proposals, disputes

Approved 2026-10-29 (see M2-POL-01 and M2-POL-10 in
`docs/module-2/scope-and-business-decisions.md`). Migration: `d9a4f2c6b871`.

All endpoints require a verified **SOCIETY_ADMIN** (`society.notices.manage`),
a Flask session and, for POST, `X-CSRF-Token`. PLATFORM_ADMIN and residents get
`403`. Responses carry display names, never user ids.

## Discussions — soft hide

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/api/admin/community/discussions/{id}/hide` | `{"reason": "3–500 chars"}` | `409 DISCUSSION_ALREADY_HIDDEN` |
| POST | `/api/admin/community/discussions/{id}/restore` | `{}` | `409 DISCUSSION_NOT_HIDDEN` |

A hidden discussion is kept, not deleted. Residents get `404` for it (read and
comment), it leaves `/api/discussions` and governance history, and returns on
restore. Admin views add `hidden`, `hidden_at`, `hidden_reason`,
`hidden_by_display_name`. Audit: `DISCUSSION_HIDDEN` (with reason),
`DISCUSSION_RESTORED`.

## Proposals — one final decision

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/api/admin/community/proposals/{id}/decision` | `{"decision": "APPROVED" \| "REJECTED", "note": "optional, ≤1000"}` | Only from `SUBMITTED`; otherwise `409 PROPOSAL_ALREADY_DECIDED` |

Proposal JSON (resident and admin) adds `decided_at`, `decision_note`; the admin
view also adds `decided_by_display_name`. `voting_open` stays `false`. Audit
`PROPOSAL_DECIDED` appears in governance history as
`Society Admin approved|rejected proposal "<title>".`

## Disputes — admin handling

| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/api/admin/disputes?status=&limit=&offset=` | — | `status` ∈ `SUBMITTED`, `IN_REVIEW`, `RESOLVED` |
| GET | `/api/admin/disputes/{id}` | — | |
| POST | `/api/admin/disputes/{id}/status` | `{"status": "IN_REVIEW" \| "RESOLVED", "response": "≤4000"}` | `RESOLVED` requires `response` |

Allowed moves: `SUBMITTED → IN_REVIEW | RESOLVED`, `IN_REVIEW → RESOLVED`,
`RESOLVED → IN_REVIEW` (reopen). Anything else is `409 INVALID_STATUS_TRANSITION`.
Residents still cannot change status (`PATCH /api/disputes/{id}` is `405`).

Resident dispute JSON adds `status_changed_at` and `admin_response`. Admin JSON
adds `author_display_name` and `handled_by_display_name`. Disputes never appear
in governance history or community activity. Audit `DISPUTE_STATUS_CHANGED`
records only `{"from", "to"}`, not the description or response text.

## Frontend

- Admin menu → Community: Discussions (hide/restore), Proposals
  (approve/reject), Disputes (`/admin/disputes`).
- Resident proposal and dispute detail pages show the decision or response.
