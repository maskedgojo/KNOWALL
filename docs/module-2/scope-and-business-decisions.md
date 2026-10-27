# KNOWALL Module 2 — Scope and Business Decisions

## 1. Document status

**Phase:** 0 — planning baseline

**Policy status:** Official notice publishing is approved for a verified
SOCIETY_ADMIN through `society.notices.manage`. Every other unresolved item
below remains **PENDING TEAM DECISION**.

## 2. Verified integration constraints

| Area | Constraint |
|---|---|
| Backend | Flask modular monolith; Module 2 must join the existing application rather than introduce another backend. |
| Persistence | PostgreSQL with SQLAlchemy models and Alembic migrations. |
| Authentication | Flask-Login session cookie and CSRF-protected mutations; no JWT or second frontend authentication system. |
| Identity | Module 1 owns users, memberships, households, flats, role assignments and effective permissions. |
| Society scope | The current application is a single-society demo with singleton `society_profile` record `id=1`. |
| Access | Server routes use the existing `requires_permission(...)` pattern plus resource-level checks. |
| Voting boundary | Module 1 supplies membership, role and occupancy facts but grants no formal voting right. |
| API authority | `backend/app/openapi.json` is authoritative for existing APIs. |

## 3. Planned Module 2 scope

The approved planning scope contains these feature areas:

1. Official notices with publication, audience targeting, reads or
   acknowledgements, expiry and archive behavior.
2. Community discussions with posts, threaded comments, reporting and
   moderation actions.
3. Suggestions with triage and a traceable decision or conversion to a
   proposal.
4. Private disputes with restricted access, assignment, status history and a
   possible appeal or reopen flow.
5. Informal polls whose results are visibly non-binding.
6. Formal proposals, eligibility snapshots, ballot handling, results and a
   recorded decision.
7. Governance transparency through decision history, moderation history and
   contextual links or notifications when approved.

This list describes product scope, not an implementation guarantee or endpoint
contract. The order and detailed rules remain subject to the progress tracker
and pending decisions.

## 4. Explicit non-goals for the current release

- Multi-society discovery or switching.
- Government or municipal production integrations.
- Payments, marketplace features, food/cab services or unrelated AI features.
- Replacing Module 1 OCR, residence verification, onboarding or authentication.
- Treating a community poll as a binding vote without an approved governance
  policy.

## 5. Decision register

| ID | Decision | Status | Required team confirmation before implementation |
|---|---|---|---|
| M2-POL-01 | Governance authority model | **PARTIAL — notices only, 2026-10-25** | Notice publishing is granted to verified SOCIETY_ADMIN only, through `society.notices.manage`, with no resident membership required. Moderation, disputes, proposals, and voting remain **PENDING TEAM DECISION**. |
| M2-POL-02 | Module 2 permission codes | **PARTIAL — notices only, 2026-10-25** | `society.notices.read` stays an eligible-resident capability. `society.notices.manage` is registered and granted to SOCIETY_ADMIN only; it does not grant read or voting. Other Module 2 codes remain **PENDING TEAM DECISION**. |
| M2-POL-03 | Society scoping | **PARTIAL — notices only, 2026-10-25** | Notice V1 stores a non-null integer `society_id` referencing `society_profile.id`. The server resolves the singleton and rejects a client-supplied society id. Other Module 2 tables remain **PENDING TEAM DECISION**. |
| M2-POL-04 | Per-flat representative | **PENDING TEAM DECISION** | Define who may use a flat entitlement when owner and tenant households coexist, and how the designation is recorded. |
| M2-POL-05 | Per-proposal voter eligibility | **PENDING TEAM DECISION** | Define eligibility for owners, tenants, family members and non-occupying owners for each voting basis. |
| M2-POL-06 | Snapshot and revocation behavior | **PENDING TEAM DECISION** | Define how suspension, revocation or expiration after a vote opens affects a frozen entitlement snapshot. |
| M2-POL-07 | Ballot confidentiality | **PENDING TEAM DECISION** | Choose attributable, secret or another auditable ballot design; define who can inspect ballot-level data. |
| M2-POL-08 | Governance result rules | **PENDING TEAM DECISION** | Define quorum, majority, tie, abstention, amendment, cancellation and recount rules. |
| M2-POL-09 | Informal poll behavior | **PENDING TEAM DECISION** | Define anonymity, eligibility, result visibility and whether results may be shown before close. |
| M2-POL-10 | Dispute privacy | **PENDING TEAM DECISION** | Define reporter, respondent, handler, committee and administrator access to messages, identities, files and history. |
| M2-POL-11 | Attachments and retention | **PENDING TEAM DECISION** | Define allowed file types/sizes, private storage, download authority, retention and purge rules for Module 2. |
| M2-POL-12 | Audit ownership | **PARTIAL — notices only, 2026-10-25** | Notice V1 appends create, update, publish, archive, and replacement events to `audit_logs` with entity type `NOTICE`. Details omit the notice body. Other Module 2 audit ownership remains **PENDING TEAM DECISION**. |
| M2-POL-13 | Notification handoff | **PENDING TEAM DECISION** | Define the contract with adjacent modules for announcements, in-app notifications and event links. |

## 6. Documentation rules

- Mark unresolved choices exactly as **PENDING TEAM DECISION**.
- Update this register when a team decision is approved, with the decision
  date, owner and affected code/contracts.
- Do not backfill a policy into code, tests, seeds or API examples before it is
  approved.
- Treat the checked-in backend OpenAPI as the source of truth for current
  Module 1 integration; do not rely on the stale frontend OpenAPI copy for new
  contracts.

## 7. Related documents

- [Module overview](README.md)
- [Progress tracker](progress.md)
- [Initial acceptance criteria](acceptance-criteria.md)
