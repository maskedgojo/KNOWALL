# KNOWALL Module 2 — Society Communication & Governance

## 1. Purpose

Module 2 provides society communication and governance for the single-society
Green Valley Residency demo. The intended journey is official communication,
resident participation, accountable decisions, and traceable governance
outcomes.

This directory is the planning and handoff home for Module 2. Update it in
the same change as the code, tests, API contract, and migration it describes.

## 2. Current status

**Branch:** `shwati`

**Formal voting is not implemented.** There is no ballot table, no
`/api/votes` route, and no `/api/proposals/{id}/votes` route. Proposal records
can be submitted and read with `voting_open` set to false. Informal polls are
a separate, non-binding feature.

### Implemented

- Official notices: draft, edit, publish, immutable published content,
  replacement draft, archive, and live expiry. Audience is the whole
  configured society. No notice category, pin, attachment, or read
  acknowledgement.
- Discussions and threaded comments for an eligible resident.
- Suggestion submission. Status stays `SUBMITTED`.
- Informal polls: one response per signed-in eligible resident, open and close
  window, counts hidden until close, and no voter identity in API responses.
- Private dispute submission. The reporter can list and read only their own
  dispute. Another resident receives 404.
- Proposal submission and reading, without a ballot.
- Resident governance history of safe event summaries.
- Society Admin read-only Community Activity for discussions, suggestions,
  polls, and proposals. Private disputes are not included.

### Partially implemented

- Notice expiry is enforced by the resident API and the resident list. A full
  browser regression has not been recorded as passed.
- Poll eligibility reuses `society.notices.read`. A separate poll-eligibility
  rule is not approved.
- Governance history is a filtered audit view, not published minutes or a
  formal decision record.
- Setup notes in this directory match the code below. The root `README.md`
  remains the Module 1 runbook.

### Missing

- Notice categories, audience targeting, pinning, attachments, and read
  acknowledgements.
- Discussion reporting.
- Suggestion conversion into a proposal or another resulting action.
- Published minutes.

### Blocked by policy

- Discussion moderation (`society.discussions.moderate` is not registered;
  M2-POL-01).
- Committee suggestion decisions (`society.suggestions.decide` is not
  registered; M2-POL-01).
- Dispute handlers, responses, appeals, reopening, and evidence (M2-POL-10 and
  M2-POL-11).
- Formal voting, including per-resident or per-flat eligibility, representative
  selection, snapshots, one-ballot rules, deadlines, quorum, results, and
  recorded decisions (M2-POL-04 through M2-POL-08).
- Informal-poll anonymity and early-result rules beyond the current
  hide-until-close behavior (M2-POL-09).
- Contextual notifications (M2-POL-13).

The development database was reported on 2026-10-25 as having the Module 2
migrations applied. This document change did not query Alembic or run a
migration.

## 3. Routes and permissions

Resident participation uses the existing eligible-resident permission
`society.notices.read`. Society Admin notice management and Community Activity
use `society.notices.manage`, which is granted only to a verified Society
Admin and does not grant resident read access or voting. No other Module 2
permission code is registered.

| Area | Routes | Permission |
|---|---|---|
| Resident notices | `GET /api/notices`, `GET /api/notices/{notice_id}` | `society.notices.read` |
| Notice management | `GET/POST /api/admin/notices`, `GET/PATCH /api/admin/notices/{notice_id}`, `POST .../publish`, `POST .../archive`, `POST .../replacements` | `society.notices.manage` |
| Discussions | `GET/POST /api/discussions`, `GET /api/discussions/{discussion_id}`, `POST /api/discussions/{discussion_id}/comments` | `society.notices.read` |
| Suggestions | `GET/POST /api/suggestions`, `GET /api/suggestions/{suggestion_id}` | `society.notices.read` |
| Informal polls | `GET/POST /api/polls`, `GET /api/polls/{poll_id}`, `POST /api/polls/{poll_id}/votes` | `society.notices.read` |
| Private disputes | `GET/POST /api/disputes`, `GET /api/disputes/{dispute_id}` | `society.notices.read`, owner only |
| Proposals | `GET/POST /api/proposals`, `GET /api/proposals/{proposal_id}` | `society.notices.read` |
| Governance history | `GET /api/governance/history` | `society.notices.read` |
| Community Activity | `GET /api/admin/community/discussions`, `GET /api/admin/community/discussions/{discussion_id}`, `GET /api/admin/community/suggestions`, `GET /api/admin/community/suggestions/{suggestion_id}`, `GET /api/admin/community/polls`, `GET /api/admin/community/polls/{poll_id}`, `GET /api/admin/community/proposals`, `GET /api/admin/community/proposals/{proposal_id}` | `society.notices.manage` |

If a feature table is missing, its routes return `503 SCHEMA_NOT_READY`
instead of a not-found error. Notices do not use that helper. Mutations
require the Flask session cookie and `X-CSRF-Token`. GET requests do not.

## 4. Migration chain

The Module 2 script chain, without applying it here, is:

`7cfa926bd410` → `c3a91e7b4d20` (notices) → `e4b8c2d71a05` (discussions) →
`f1c7a4e82b30` (suggestions) → `b4e8c1a27d90` (polls, disputes, proposals).

`b4e8c1a27d90` is the single head in the migration files. It does not create a
ballot table.

## 5. Documentation map

| Document | Purpose |
|---|---|
| [Scope and business decisions](scope-and-business-decisions.md) | Scope boundary and the policy decision register. |
| [Progress tracker](progress.md) | Implementation status, tests, and the browser checklist. |
| [Acceptance criteria](acceptance-criteria.md) | What can be accepted now, and which criteria stay conditional. |
| [Formal voting dependencies](formal-voting-dependencies.md) | Why formal voting stays blocked. |
| [Official Notices V1 contract](../api-contracts/notices-v1.md) | Notice lifecycle, authorization, and audit rules. |
| [Discussions](../api-contracts/discussions-v1.md), [suggestions](../api-contracts/suggestions-v1.md), [governance history](../api-contracts/governance-history-v1.md) | Contracts for those slices. |

## 6. Integration baseline

- Flask remains the sole backend and authentication authority.
- PostgreSQL, SQLAlchemy, and Alembic remain the persistence and migration stack.
- Next.js and TypeScript remain the frontend stack.
- Module 1 owns identity, sessions, memberships, households, roles, and effective access.
- Module 2 uses `requires_permission` and does not create a second identity system.
- `backend/app/openapi.json` is the canonical API contract.

Module 2 must not infer a voting right from a role, household, flat, or
occupancy value, expose a private dispute in a society feed, or treat a
pending decision as approved policy.

## 7. Authoritative references

- Root project baseline: `README.md`
- Permission contract: `docs/api-contracts/permissions-phase9.md`
- Voting boundary: `docs/api-contracts/module1-family-profile-occupancy.md`
- Canonical runtime contract: `backend/app/openapi.json`
