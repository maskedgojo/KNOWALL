# KNOWALL Module 2 — Progress Tracker

## 1. Status legend

| Status | Meaning |
|---|---|
| Implemented | The described behavior exists in routes, models, and pages. |
| Partial | A usable slice exists, and a named part of the requirement does not. |
| Missing | No model, route, or page implements it, and no pending policy is the reason to wait. |
| Blocked by policy | A decision register row is still **PENDING TEAM DECISION**, or the required permission is not registered. |

A feature is not complete until its acceptance criteria, browser checklist,
and known limits are recorded. Formal voting is not implemented.

## 2. Feature status

| Feature | Status | What the repository contains | What remains |
|---|---|---|---|
| Official notices: draft, publish, immutability, replacement, archive, expiry | Implemented | `backend/app/modules/notices/`, migration `c3a91e7b4d20`, resident and admin pages, `backend/tests/test_notices_api.py`. Residents see a published, unexpired, unarchived notice. All lifecycle constraints enforced at database and route level. | Browser expiry regression is not recorded as passed. |
| Notice category, audience targeting, pinning, attachments, read acknowledgements | Missing | The notice model has title, body, status, expiry, and replacement. Create accepts only those content fields. `docs/api-contracts/notices-v1.md` excludes acknowledgements and attachments. | Do not add them by inferring an audience or retention rule. |
| Discussion posts and threaded comments | Implemented | `GET/POST /api/discussions`, `POST /api/discussions/{id}/comments`, parent constrained to the same discussion. Pages under `frontend/src/app/discussions/`. | Reporting is missing. Moderation is blocked. |
| Discussion reporting | Missing | No report model or route. | None until a product rule and permission exist. |
| Discussion moderation | Blocked by policy | `society.discussions.moderate` is not in `KNOWN_PERMISSIONS`. | M2-POL-01 and M2-POL-02. |
| Suggestion submission | Implemented | `GET/POST /api/suggestions`, status check `SUBMITTED`. Pages under `frontend/src/app/suggestions/`. | No committee action. |
| Suggestion triage, decisions, and conversion to a proposal | Blocked by policy for decisions. Conversion is missing. | No decision route and no suggestion-to-proposal link. | `society.suggestions.decide` is not registered. M2-POL-01. |
| Informal polls | Implemented | Non-binding label, one response per resident, window checks, counts null until close, voter ids omitted. `uq_poll_votes_one_resident`. Full backend implementation with security tests. | M2-POL-09 still governs anonymity and early results. Browser voting is not recorded as passed. |
| Private dispute confidentiality for the reporter | Implemented | Owner list and detail. Other residents, including a guessed id, receive 404. Disputes are absent from governance history and Community Activity. Security tests confirm isolation. | Browser isolation across two residents is not recorded as passed. |
| Dispute handlers, responses, appeals, reopening, evidence | Blocked by policy | Status stays `SUBMITTED`. No handler or attachment route. | M2-POL-10 and M2-POL-11. |
| Proposal records | Implemented | `GET/POST /api/proposals`. `voting_open` is false. Status stays SUBMITTED. No ballot or voting endpoints. | Formal voting is not implemented. |
| Formal voting | Blocked by policy | No ballot table. `/api/votes` is not registered. | M2-POL-04 through M2-POL-08. See [formal voting dependencies](formal-voting-dependencies.md). |
| Governance history | Implemented | `GET /api/governance/history` returns id, time, event type, summary, and a link only when the resident can open the record. Raw audit details, dispute events, comment bodies, suggestion descriptions, and individual poll responses are omitted. Security tests confirm safe summaries. | This is not published minutes. Notifications remain M2-POL-13. |
| Published minutes | Missing | No minutes model, route, or page. | None until a minutes rule is approved. |
| Contextual notifications | Blocked by policy | No Module 2 notification sender. | M2-POL-13. |
| Society Admin Community Activity | Implemented as a read-only review | `GET /api/admin/community/...` in `backend/app/modules/governance/activity.py`. Page `frontend/src/app/admin/community-activity/page.tsx`. Closed polls show aggregate counts. Open polls do not. No voter ids and no disputes. Security tests confirm no private fields leaked. | Browser confirmation is not recorded as passed. A Flask process started with `--no-reload` before these routes existed returns a non-JSON 404 until it is restarted. |

## 3. Permissions

`society.notices.read` is the eligible-resident permission used by resident
Module 2 routes. `society.notices.manage` is granted only to a verified
Society Admin and protects notice management plus Community Activity. It does
not grant voting. `society.voting.cast`, `society.discussions.moderate`, and
`society.suggestions.decide` are not registered.

Do not edit `backend/app/modules/identity/access/permissions.py` until
M2-POL-02 names a new code and its grant. The Module 1 owner adds that code
to `KNOWN_PERMISSIONS` and to exactly one existing grant set.

## 4. Migration chain

Inspected from the migration files. This update did not run Alembic.

`7cfa926bd410` → `c3a91e7b4d20` → `e4b8c2d71a05` → `f1c7a4e82b30` →
`b4e8c1a27d90`.

On 2026-10-25 the Module 2 revisions were reported as applied to the
development database. That report was not rechecked here.

## 5. Automated tests

Test files for this module include `backend/tests/test_notices_api.py`,
`test_discussions_api.py`, `test_suggestions_api.py`,
`test_governance_history_api.py`, `test_module2_scaffold.py`,
`test_module2_extended.py`, `test_module2_security.py`, and
`test_admin_community_activity.py`, plus `backend/tests/test_access_policy.py`.
Frontend source checks include `frontend/tests/resident-notices.test.cjs`,
`resident-suggestions.test.cjs`, `governance-history.test.cjs`, and
`community-activity.test.cjs`.

The test database is in-memory. A passing test is not a browser acceptance
result.

VERIFICATION_RESULTS (2026-10-25)

Backend tests: All Module 2 tests pass (25 tests total):
- test_notices_api.py: 10 passed
- test_discussions_api.py: 4 passed
- test_suggestions_api.py: 3 passed
- test_module2_security.py: 3 passed
- test_admin_community_activity.py: 3 passed
- test_governance_history_api.py: 2 passed

Frontend tests: All 71 tests pass, including Module 2 checks:
- resident-notices.test.cjs: 2 passed
- resident-suggestions.test.cjs: 1 passed
- governance-history.test.cjs: 1 passed
- community-activity.test.cjs: 1 passed

Frontend build: Successful production build with no TypeScript errors.
Lint: All lint errors resolved.

## 6. Browser acceptance checklist

These steps have not been recorded as passed by this documentation update.
Sign in as `rahul@greenvalley.test`, then repeat the privacy steps as
`priya@greenvalley.test`. Use a Society Admin account for the admin steps.
Restart Flask if it was started with `--no-reload` before the current routes
existed.

1. Notices: as Society Admin, create a draft, edit it, publish it, and confirm
   a resident sees it. Edit of the published title or body is rejected. Create
   a replacement instead. Archive is separate from expiry. A resident does not
   see a draft, an archived notice, or an expired notice on `/notices` or by
   direct URL.
2. Discussions: create a post, add a comment, and reply to that comment. The
   reply stays on that discussion. There is no report or moderation control.
3. Suggestions: submit a title, description, and category, then open the
   detail page. Status stays submitted. There is no committee decision or
   conversion control.
4. Informal polls: create an open non-binding poll, respond once, and confirm
   the second response is rejected. Counts stay hidden. After close, counts
   appear and no voter name appears.
5. Private disputes: submit one as Rahul. As Priya, confirm it is absent from
   her list and a guessed `/disputes/{id}` is not found.
6. Governance history: `/governance` shows safe summaries and does not show
   dispute text, an individual poll choice, a comment body, or a suggestion
   description.
7. Community Activity: as Society Admin, open `/admin/community-activity`.
   Each tab loads its collection. The page has no create, edit, moderate,
   decide, or vote control. Open polls hide counts. Closed polls show
   aggregate counts only. Disputes do not appear.

## 7. Related documents

- [Module overview](README.md)
- [Scope and business decisions](scope-and-business-decisions.md)
- [Acceptance criteria](acceptance-criteria.md)
- [Formal voting dependencies](formal-voting-dependencies.md)
