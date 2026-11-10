# KNOWALL Module 5 — Civic Issue Reporting & Community Priority

*From a local concern to a validated shared case.*

## 1. Purpose

A verified resident reports a problem on public infrastructure near Green Valley Residency (a pothole,
a dead streetlight), sees whether it is already reported, and gathers support. A coordinator validates
it, links duplicates, and hands a traceable payload to Module 6. Demo story step 5: *Rahul pins an
outside-road pothole, attaches a picture, sees potential duplicates and gathers support.*

The team pack proposes Next.js APIs and Prisma. This module follows the existing repository instead:
Flask blueprints, SQLAlchemy models, Alembic migrations, and the Next.js App Router as UI only, using
Module 1 sessions and permissions.

**Scope line.** Civic issues are *public locality infrastructure only*. Problems inside the society
belong to Module 3 (maintenance tickets) or Module 2 (suggestions, disputes). Do not add a
"common area" category here.

## 2. Status

| Feature | Status | Where |
|---|---|---|
| Create issue (category, severity, pin, landmark, privacy), save as draft | Implemented | `civic/issues.py`, `/civic/new` |
| Scope check (inside the coverage circle), field and content validation | Implemented | `civic/issues.py`, `civic/common.py` |
| Private JPG/PNG evidence, authorised download, max 5 per issue | Implemented | `civic/evidence.py` |
| Duplicate suggestions (same category, open, within 150 m) | Implemented | `civic/duplicates.py` |
| Support: one per verified account, DB unique constraint | Implemented | `civic/support.py` |
| Transparent priority (support + age + severity) with stored snapshots | Implemented | `civic/priority.py` |
| Lifecycle: draft, submitted, under review, needs info, validated, ready for routing, rejected, merged, withdrawn | Implemented | `civic/service.py` |
| Coordinator review, validate, needs-info, reject, merge | Implemented | `civic/moderation.py`, `/admin/civic` |
| Abuse reports and moderator disposition (dismiss, redact, correct, remove) | Implemented | `issues.py`, `moderation.py` |
| Reporter timeline and canonical link after a merge | Implemented | `issues.py`, `/civic/[id]` |
| Route to Module 6 with a payload keyed by the canonical issue id | Implemented | `civic/handoff.py` |
| Display of Module 6 case status | Hook only | `service.authority_status()` returns null until Module 6 ships |
| Notifications | Missing | Same blocker as Modules 2 and 3: no notification contract yet. Every change is in `audit_logs`. |
| Real map tiles | Not included | The area map is an offline SVG; no external service is called. |

## 3. Permissions

| Code | Who | Used for |
|---|---|---|
| `civic.issues.create` | Eligible resident (Module 1) | Create, read, edit own, evidence, report a concern |
| `civic.issues.support` | Eligible resident (Module 1) | Support and withdraw support |
| `identity.admin.manage` | Society or platform admin (Module 1) | **All moderation and routing** |

`identity.admin.manage` is a stand-in. Module 1 has no `civic.issues.moderate` yet. When it adds one,
change the single constant `MODERATE_PERMISSION` in `backend/app/modules/civic/common.py`. Unknown
permission names fail closed, so do not guess one.

The server decides every permission. Frontend gating only hides links.

## 4. Business rules

- Only residents with an active membership can create, read or support. Applicants get 403.
- **Visibility.** Other residents see an issue only in `SUBMITTED`, `UNDER_REVIEW`, `VALIDATED`,
  `READY_FOR_ROUTING`, or `MERGED`. Drafts, needs-info, rejected and withdrawn issues are visible to the
  reporter and coordinators only. Missing and not-allowed both return the same 404.
- **Support** opens only after validation (`VALIDATED`, `READY_FOR_ROUTING`). The reporter cannot support
  their own issue. One support per account, enforced by a unique constraint, so a second session or a
  race returns `ALREADY_SUPPORTED` and the count does not move. Withdrawing is allowed only while
  `VALIDATED`.
- **Merging.** A merge is a coordinator decision, never automatic. The duplicate becomes `MERGED` and
  keeps its history. Supporters are combined **by identity**: a canonical issue's count is the distinct
  accounts that supported it or any duplicate, plus the reporters of its duplicates, minus its own
  reporter. Nothing is deleted. Merging requires the same category, an open target, and no handoff on the
  duplicate. Reports more than 150 m apart need `acknowledge_distance: true`.
- **Privacy.** Reporter contact details are never returned. Other residents see "A resident" unless the
  reporter chose `PUBLIC_NAME`. Photos are `PRIVATE` by default (reporter and coordinators);
  the reporter may choose `RESIDENTS`, and a coordinator can change it. Descriptions containing HTML,
  phone numbers or email addresses are rejected.
- **Readiness for routing.** `VALIDATED`, at least 3 supporters (`CIVIC_MIN_SUPPORTERS`, default 3) and at
  least one photo. The server returns what is missing.
- **Priority** = 2 per supporter (max 20 counted) + 0.5 per day open (max 30 counted) + severity points
  (LOW 0, MEDIUM 5, HIGH 10, CRITICAL 20). Bands: LOW below 15, MEDIUM 15-34, HIGH 35 and above. The
  response lists every input and says it does not guarantee authority action. No ML.
- **History.** Every state change writes an append-only `civic_issue_transitions` row with actor role,
  from, to and reason. Reasons are shown only to the reporter and coordinators.
- A reporter may create at most 10 issues per rolling day.

## 5. Lifecycle

```
DRAFT -> SUBMITTED -> UNDER_REVIEW -> VALIDATED -> READY_FOR_ROUTING -> (Module 6 owns the case)
            |  ^            |            |
            v  |            v            v
         NEEDS_INFO      REJECTED      MERGED      WITHDRAWN (reporter, from DRAFT/SUBMITTED/NEEDS_INFO)
```

`SUBMITTED` may also go straight to `VALIDATED`, `NEEDS_INFO`, `REJECTED` or `MERGED`. `NEEDS_INFO`
returns to `SUBMITTED` when the reporter resubmits. `READY_FOR_ROUTING`, `REJECTED`, `MERGED` and
`WITHDRAWN` are terminal for this module.

## 6. Data model (migration `d9a4c6e1b752`)

`civic_localities` (stub, see section 8), `civic_issues`, `civic_issue_evidence`, `civic_issue_supports`
(unique issue+user), `civic_duplicate_links` (one row per duplicate), `civic_issue_transitions`,
`civic_priority_snapshots`, `civic_issue_reports` (unique issue+reporter), `civic_issue_handoffs`
(unique per issue, JSON payload).

## 7. Files

```
backend/app/modules/civic/   models, common, service, priority, issues, duplicates, support,
                             evidence, moderation, handoff
backend/migrations/versions/d9a4c6e1b752_module5_civic_issues.py
backend/scripts/seed_civic_demo.py
backend/tests/test_civic_api.py                  (32 tests)
frontend/src/lib/civic-{types,api,geo}.ts
frontend/src/features/civic/                     parts, issue-list, report-wizard, issue-detail, admin-civic
frontend/src/app/civic/{page,new/page,[id]/page}.tsx, frontend/src/app/admin/civic/page.tsx
frontend/tests/civic.test.cjs
docs/api-contracts/civic-issues-v1.md
```

Edits outside this module are limited to: ten added lines in `backend/app/__init__.py` (one model import,
six blueprint imports, a three-line registration loop) and two nav entries in `frontend/src/components/shell.tsx`.

## 8. Integration with other modules

| Module | Contract | State |
|---|---|---|
| 1 Identity | Uses `requires_permission`, `has_permission`, `AuditLog`, private storage (`identity/documents/storage.py`). Needs `civic.issues.moderate` (see section 3). | Working |
| 4 Locality | Needs a locality row with centre, radius and a `locality_id`. Module 5 ships a **stub** `civic_localities` seeded for Green Valley. The Module 4 owner should replace it with their table instead of keeping two copies. | Stub |
| 6 Authority | Module 5 sends the payload below. Module 6 should call `civic.handoff.acknowledge_handoff(issue_id, authority_case_id)` when it creates a case, and expose `app.modules.authority.public.case_status_for_issue(issue_id) -> dict | None`. Module 5 displays that status and never stores its own. | Hook ready, Module 6 pending |

Until Module 6 exists, `POST /api/civic/issues/:id/handoff/acknowledge` (admin only) simulates the intake.

**Routing payload** (`civic_issue_handoffs.payload`): `canonical_issue_id`, `category`, `severity`, `title`,
`summary`, `location {locality_id, latitude, longitude, address_hint}`, `evidence [{evidence_id, mime_type,
caption, visibility}]`, `community_support`, `priority`, `merged_duplicate_issue_ids`, `validated_at`,
`demonstration_data: true`. It never contains the reporter's email, phone or user id.

**Migration heads.** The migration revises `c7e2b4a91f30`. If another module also revises it, Alembic reports
two heads. Resolve with `flask db merge heads` once the team agrees an order.

## 9. Local setup

```bash
cd backend
pip install -r requirements.txt
flask db upgrade
python -m scripts.seed_green_valley      # Module 1 demo accounts (needs the seed password env vars)
python -m scripts.seed_civic_demo        # civic coverage area + 3 fictional issues
flask run                                # http://127.0.0.1:5000
```

```bash
cd frontend
npm install
npm run dev                              # http://localhost:3000, /api/* is proxied to Flask
```

Optional environment variable: `CIVIC_MIN_SUPPORTERS` (default 3). Evidence is stored under
`OCR_PRIVATE_DIR` like Module 1 documents.

Tests:

```bash
cd backend && python -m pytest tests/test_civic_api.py
cd frontend && npm run typecheck && npm run lint && npm test
```

The backend tests use an in-memory SQLite schema and never touch the project database. They were run on
SQLite only; run the migration and seed against PostgreSQL before the demo.

The seed creates: Rahul's pothole and Maya's near-duplicate (both `SUBMITTED`), and Priya's streetlight
(`VALIDATED`, supported by Amit and Sneha).

## 10. Manual test script

Sign in as the accounts from the Module 1 seed (`rahul`, `priya`, `amit`, `sneha`, `maya`,
`admin` at `@greenvalley.test`).

**Success path**

1. Rahul: **Civic issues > Report an issue**. Click the map near the centre, choose *Road damage*, enter a
   title and a 20+ character description, continue. See the nearby match from the seed, choose
   *None of these*, attach a JPG, **Submit report**. State is *Submitted*.
2. Admin: **Administration > Civic issues**. Open Rahul's report, **Start review**, then **Validate**.
3. Priya, Amit, Sneha: open the report, **Support this issue**. Count reaches 3.
4. Admin: choose **Hand off for routing**. State becomes *Ready for routing*. Record a demo case id.
5. Rahul: open his report. The timeline shows the validation, the handoff and the case id on the same issue.

**Duplicate path**

1. Maya's seeded report is a near-duplicate. Admin: validate Rahul's, then on Maya's choose
   **Merge into another report**, pick Rahul's. Maya sees *Merged* with a link to the main report; Rahul's
   count includes Maya once.

**Failure and edge paths**

| Try | Expected |
|---|---|
| Support a report that is still *Submitted* | `NOT_OPEN_FOR_SUPPORT` |
| Support twice, or from a second browser | `ALREADY_SUPPORTED`; count unchanged |
| Support your own report | `OWN_ISSUE` |
| Pin outside the dashed circle | "outside the area covered" |
| Put a phone number or `<script>` in the description | Field error |
| Upload a `.pdf` or a renamed text file | `INVALID_DOCUMENT` |
| Resident opens `/admin/civic` or calls an admin route | 403 |
| Hand off with fewer than 3 supporters or no photo | `NOT_READY_FOR_ROUTING` listing what is missing |
| Merge two reports far apart | `LOCATIONS_TOO_FAR` until the coordinator confirms |
| Another resident opens a private photo link | 404 |

## 11. Demo script (3-5 minutes)

1. **Problem (20 s).** Public-road problems get lost; duplicates fragment support.
2. **Actors.** Resident, neighbours, coordinator, and the Module 6 authority workspace.
3. **Report (60 s).** Rahul pins the pothole, adds a photo, sees the nearby match, submits.
4. **Validate and support (60 s).** Coordinator validates; two neighbours support; show the priority card and its inputs.
5. **Edge case (45 s).** Maya's duplicate: merge it, show the canonical link and that the count is not inflated; show a repeat-support rejection.
6. **Handoff (45 s).** Route the case, show the payload fields and the reporter's timeline.
7. **Architecture (30 s).** Flask blueprints over shared Module 1 auth; stub locality; Module 6 hook.
8. **Boundary.** Module 5 stops at `READY_FOR_ROUTING`; the authority owns what happens next.

## 12. Open decisions for the team

1. Dedicated `civic.issues.moderate` permission or a coordinator role from Module 1.
2. Module 4 takes over `civic_localities`.
3. Module 6 confirms the payload, the `acknowledge_handoff` call, and the case-status hook.
4. Whether the reporter should count as a supporter (currently excluded; the threshold is 3 neighbours).
5. Photo visibility default (currently private) and who may publish photos.
6. Notification events once a shared contract exists.
