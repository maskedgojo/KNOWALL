# KNOWALL Module 6: Authority Resolution, Oversight & Insights

**Green Valley Residency · single-society demo · Flask + PostgreSQL + Next.js**

A validated civic issue from Module 5 becomes a trackable authority case: routed to a demo department, accepted,
worked on, escalated when overdue, resolved with photo proof, and then **verified by the affected residents**, who
can close it or reopen the same case. Demo story step 6: *the validated pothole reaches a labelled demo department,
receives progress and evidence, and Rahul verifies the result.*

> **Simulated authorities only.** Every department and official is fictional and labelled "(Demo)". No real
> government body participates, and nothing is sent to any government system. Every Module 6 screen and API
> response carries this notice.

## 1. Delivery status

| Feature (assignment card §2) | Status | Where |
|---|---|---|
| Department directory: categories, locality scope, routing desk, escalation chain | Implemented | `authority/admin.py`, `models.Department`, `JurisdictionRule`, `EscalationRule` |
| Case intake and routing from the Module 5 payload; accept / transfer / clarification | Implemented | `authority/cases.py` |
| Progress timeline: actor, time, status, optional evidence, resident-facing summary | Implemented | `CaseEvent` (append-only, per-case sequence) |
| Escalation: overdue flag, one manual escalation, explicit "simulated" acknowledgement | Implemented | `service.sweep`, `POST /cases/:id/escalate` |
| Resolution evidence: official photos, immutable history | Implemented | `ResolutionEvidence` (append-only) |
| Community verification: affected residents confirm or dispute; controlled reopen | Implemented | `authority/resident.py`, `service.apply_verdict_rules` |
| Oversight analytics: counts by stage, durations, escalations, outcomes, audit view | Implemented | `GET /api/admin/analytics/civic` |
| Resident-facing linked case tracker on the civic issue | Implemented | `features/authority/case-tracker.tsx` inside the Module 5 issue page |
| Clarification and reopen feedback (reason or photo) | Implemented | `request-clarification`, `respond-clarification`, dispute photo |
| Notifications | In-app outbox | No shared notification service exists yet; `authority_case_notifications` + `GET /api/authority/notifications` |
| Locality boundary from Module 4 | Uses the Module 5 stub | `civic_localities` until Module 4 owns the boundary |

## 2. Actors and permissions

| Actor | Who | Can |
|---|---|---|
| Coordinator | Account with the shared admin grant (`identity.admin.manage`), same as Module 5 moderation | Intake, choose department, transfer, manual escalation, controlled reopen, close after an empty verification window, manage departments and officials, analytics, run the sweep |
| Simulated official | Active, email-verified account with an active `authority_officers` row for **one** department | Accept, transfer, post progress (and revise the target date), add photos, ask the reporter, mark resolved; **only for cases currently assigned to their department** |
| Reporter | Creator of the civic issue | Track the case, answer clarifications, verify the fix |
| Affected resident | Anyone Module 5 counts as a supporter (including merged duplicates) and holding an active membership | Verify the fix once per resolution round |

Coordinators cannot act as a department, and cannot assign themselves as an official. Officials get no resident or
admin rights from this module. Every rule is enforced in Flask; the UI only hides buttons.

## 3. Case lifecycle

```text
                transfer (reason, no loops, max 3)
                 ┌───────┐
                 v       │
INTAKE ──> ROUTED ──> ACKNOWLEDGED ──> IN_PROGRESS ──> RESOLVED ──> CLOSED
                         │   ^             │   ^           │
                         v   │             v   │           v
                 CLARIFICATION_REQUESTED <─┘   │       REOPENED (same case, round + 1)
                                               └────────────┘
```

- **Resolved and closed are separate states.** Resolving opens a verification window
  (`AUTHORITY_VERIFY_WINDOW_HOURS`, default 72 h).
- **Proof is required.** With `requires_resolution_proof` (default on) a case cannot be resolved without at least one
  `RESOLUTION` photo **in the current round**. Earlier rounds' photos do not count after a reopen.
- **Verification rules** (configurable): close when confirmations reach `AUTHORITY_CLOSE_CONFIRMATIONS` (default 2)
  and outnumber disputes; reopen when disputes reach `AUTHORITY_REOPEN_DISPUTES` (default 2) and are at least the
  confirmations. A dispute needs a reason and may carry a photo.
- **Window expiry** (periodic job): more confirmations than disputes closes the case (`WINDOW_MAJORITY`); any disputes
  otherwise reopen it; no votes at all leaves it `RESOLVED` and asks a coordinator, who may close it
  (`COORDINATOR_AFTER_WINDOW`) or reopen it.
- **Overdue**: `due_at` is set at intake from the department's demo SLA (`authority_escalation_rules.threshold_hours`,
  fallback `AUTHORITY_DEFAULT_SLA_HOURS` = 168 h). An official's progress update may revise it (future, within 90 days),
  which marks open escalations as responded. A transfer does not reset the clock.
- **Append-only**: `authority_case_events`, `authority_case_transfers`, `authority_resolution_evidence` and
  `authority_resolution_verifications` refuse updates and deletes at the session level (`AppendOnlyViolation`). Every
  event has an actor, a timestamp, a reason and a per-case `sequence`, so the order is exact even when timestamps tie.
- Module 6 never edits Module 5 support or history. Its only write to Module 5 is
  `civic.handoff.acknowledge_handoff(issue_id, case_reference)` at intake.

## 4. Data model (migration `e7c3a5d2b914`, revises Module 5 `d9a4c6e1b752`)

| Table | Purpose |
|---|---|
| `authority_departments` | Simulated department: code, name, routing desk, escalation department, proof rule, `is_demo` |
| `authority_jurisdiction_rules` | Department × locality × civic category, with priority for automatic intake |
| `authority_escalation_rules` | Demo SLA hours and escalation target per department |
| `authority_officers` | Account → one department; at most one active assignment per account |
| `authority_cases` | One per canonical civic issue: reference (`AC-XXXXXXXX`), department, status, owner, due date, round, closure basis |
| `authority_case_events` | Append-only history with resident-facing summary |
| `authority_case_transfers` | Append-only reassignment log |
| `authority_escalation_events` | One per kind per due cycle (unique), so the job never escalates the same deadline twice |
| `authority_resolution_evidence` | Append-only official photos (private storage) |
| `authority_resolution_verifications` | One verdict per resident per round (unique), membership id, optional dispute photo |
| `authority_case_clarifications` | Official's question and the reporter's single answer |
| `authority_case_notifications` | In-app notification outbox (assigned, updated, escalated, verification requested, verified) |
| `authority_metric_snapshots` | Counts recorded on every sweep |

## 5. Local setup

From `backend/`, in the same environment used for the other modules:

```bash
# 1. Apply all migrations (adds the Module 6 tables after Module 5)
python -m flask --app app:create_app db upgrade

# 2. Seeds, in order. Module 6 needs KNOWALL_SEED_OFFICER_PASSWORD (12+ chars) in backend/.env
python -m scripts.seed_green_valley
python -m scripts.seed_civic_demo
python -m scripts.seed_authority_demo --with-sample-case   # flag optional

# 3. Run Flask, then the frontend (npm run dev in frontend/)
python -m flask --app app:create_app run --debug --port 5000
```

Optional settings for `backend/.env` (all have defaults, see `authority/service.py`):

| Variable / config key | Default | Meaning |
|---|---|---|
| `KNOWALL_SEED_OFFICER_PASSWORD` | (required for the seed) | Password for the five demo official accounts |
| `AUTHORITY_VERIFY_WINDOW_HOURS` | 72 | How long residents can verify a fix |
| `AUTHORITY_CLOSE_CONFIRMATIONS` | 2 | Confirmations that close a case |
| `AUTHORITY_REOPEN_DISPUTES` | 2 | Disputes that reopen a case |
| `AUTHORITY_DEFAULT_SLA_HOURS` | 168 | SLA when a department has no escalation rule |
| `AUTHORITY_MAX_TRANSFERS` | 3 | Transfers before a coordinator must decide |

The config keys are read from `app.config`; set them in `Config` or a test config.

**Periodic job.** `python -m flask --app app:create_app authority-sweep` escalates overdue cases and settles expired
verification windows. It is idempotent: re-running it, or running it after downtime, never duplicates an escalation.
Schedule it (cron / Task Scheduler) or use **Run overdue check** on `/admin/authority`.

**Demo accounts** (seed): `officer.roads@`, `officer.lights@`, `officer.sanitation@`, `officer.water@`,
`officer.ward@greenvalley.test`. The seed departments are Roads & Footpaths, Street Lighting, Sanitation & Drainage,
Water Supply, and the Ward Office, which also takes general categories and receives escalations.

## 6. Screens

| Route | Who | What |
|---|---|---|
| `/civic/:id` (Module 5 page) | Reporter, residents | Linked case tracker: same case id and status as the official view, timeline, department photos, verify / dispute, answer clarification |
| `/authority` | Simulated officials (coordinators see all) | Department queue with status and overdue filters |
| `/authority/cases/:id` | Assigned official, coordinators | Accept, transfer, progress, photos, ask reporter, resolve; coordinator escalate / reopen / close; append-only history |
| `/admin/authority` | Coordinators | Intake queue with suggested department, all cases, departments and officials, sweep |
| `/admin/analytics` | Coordinators | Counts by stage, durations, escalations, outcomes, per department, reconciliation, audit view |

## 7. Tests

```bash
cd backend  && python -m pytest tests/test_authority_api.py      # 21 API tests
cd frontend && node --test tests/authority.test.cjs              # enum/lifecycle parity, banners, wiring
```

Acceptance checklist (card §9) → tests:

| Checklist item | Test |
|---|---|
| Routed case completes acknowledge → progress → resolve → verify → close | `test_end_to_end_case_closes_after_community_verification` |
| Transfer, overdue escalation and reopen | `test_transfer_logged_and_loops_rejected`, `test_overdue_sweep_escalates_once_per_deadline`, `test_rejected_fix_reopens_same_case_then_closes`, `test_coordinator_controlled_reopen` |
| Official scope checks and append-only history | `test_only_assigned_department_can_act`, `test_revoked_official_loses_access`, `test_history_is_append_only` |
| Analytics reconcile case states and timestamps | `test_analytics_reconcile_states_and_timestamps` (also detects a tampered status) |
| Mock authority workflow labelled | `simulation_notice` asserted in API tests; banner asserted on every screen in `authority.test.cjs` |
| Resident and official views agree; rejected fix reopens the same case | `test_end_to_end…`, `test_rejected_fix_reopens_same_case_then_closes` |

Edge cases (card §7) → tests: unrelated official denied (`test_only_assigned_department_can_act`); transfer loops and
invalid transitions (`test_transfer_logged_and_loops_rejected`, `test_invalid_transitions_rejected`); resolution
without proof blocked (`test_resolution_without_proof_is_blocked`); repeat and out-of-scope verification
(`test_verification_scope_and_single_vote`); missed deadline caught up idempotently
(`test_overdue_sweep_escalates_once_per_deadline`, `test_verification_window_expiry_is_settled_once`).

## 8. Manual demo script (3 to 5 minutes)

**Success path.** Prepare with Module 5: Rahul's pothole validated, three supporters, a photo, handed off.

1. **Admin → `/admin/authority`.** The pothole is in the intake queue with the suggested Roads department. Open the
   case. Point at the "Simulated authority" banner.
2. **`officer.roads` → `/authority`.** Open the case, **Accept**, **Post progress** ("Crew scheduled Tuesday").
3. **Rahul → `/civic/:id`.** The tracker shows the same `AC-…` id, the demo department and the timeline.
4. **Official:** **Add photo** (resolution proof), then **Mark resolved**.
5. **Rahul and Priya:** "Yes, it is solved". After the second confirmation the case is **Closed**, and Module 5's
   issue shows the same status.
6. **Admin → `/admin/analytics`.** Stage counts, durations, "Reconciled", audit trail.

**Failed / edge paths** (pick one or two):

- **Rejected fix.** After step 4, Rahul and Priya choose "No, not solved" with a reason (Priya adds a photo). The
  **same case** reopens in round 2; resolving again needs a new proof photo.
- **Wrong department.** `officer.lights` opening the roads case gets `403 NOT_ASSIGNED`. Roads transfers to the Ward
  Office with a reason; trying to send it back is rejected as `TRANSFER_LOOP`.
- **Overdue.** Coordinator **Escalate** requires ticking the "simulated" acknowledgement. **Run overdue check**
  escalates an overdue case once; running it again changes nothing.
- **No proof.** **Mark resolved** without a photo returns `PROOF_REQUIRED`.

**Presentation outline.** Problem (a validated issue goes nowhere without accountability) → actors (coordinator,
simulated official, reporter, affected residents) → flow (diagram in §3) → architecture (Flask module inside the
monolith, shared Module 1 sessions, reads Module 5, owns case status) → demo → edge case → integration boundary (§9).

## 9. Integration boundary

| Direction | Contract |
|---|---|
| 5 → 6 | `civic_issue_handoffs.payload` (canonical id, category, severity, summary, location, evidence refs, support, merged duplicates). Intake requires the issue in `READY_FOR_ROUTING`. |
| 6 → 5 | One call at intake: `civic.handoff.acknowledge_handoff(issue_id, case_reference)` (routing status → `ACKNOWLEDGED`). |
| 5 reads 6 | `app.modules.authority.public.case_status_for_issue(issue_id)`, shown as `authoritative_status`. Module 5 stores no copy. |
| 1 → 6 | Sessions, CSRF, `has_permission`, active memberships (`_eligible_memberships`), admin roles. |
| 4 → 6 | Locality boundary. Uses the Module 5 `civic_localities` stub until Module 4 ships. |
| Notifications | No shared contract yet; Module 6 writes an in-app outbox that a future notification service can drain. |

**Coordinate with Module 5:** its admin screen still offers "Record authority case (demo)" for `READY_FOR_ROUTING`
issues. If a coordinator uses it with a made-up id, Module 6 intake for that issue returns `CASE_ALREADY_LINKED`. Now
that Module 6 exists, that stand-in should be removed or pointed at `/admin/authority`.
