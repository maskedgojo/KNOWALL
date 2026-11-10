# Module 6 authority cases API v1

All routes are JSON over the shared Flask session. Modifying requests need the `X-CSRF-Token` header. Errors use
`{"error": {"code", "message", "fields"?}}`. Unknown JSON fields are rejected with `400 VALIDATION_ERROR`. Free text
uses the Module 5 plain-text rules (no markup, no phone numbers or email addresses). If the migration is missing,
every route returns `503 SCHEMA_NOT_READY`.

Staff responses include `simulation_notice`: departments and officials are simulated and nothing reaches a real
government body.

**Roles:** *coordinator* = shared admin grant; *official* = active `authority_officers` row (one department);
*resident* = `civic.issues.support` (active membership).

## Shared objects

**CaseStatus:** `ROUTED ACKNOWLEDGED CLARIFICATION_REQUESTED IN_PROGRESS RESOLVED REOPENED CLOSED`

**Public status** (also returned to Module 5 as `authoritative_status`):

```json
{"authority_case_id": "AC-1A2B3C4D", "case_id": "uuid", "status": "IN_PROGRESS", "status_label": "Work in progress",
 "department": {"id": 1, "name": "Roads Division (Demo)", "is_demo": true}, "is_overdue": false,
 "due_at": "", "round": 1, "reopen_count": 0, "resolved_at": null, "verification_closes_at": null,
 "closed_at": null, "closure_basis": null, "updated_at": "", "simulated": true}
```

**Case (staff)** = public status plus `civic_issue_id`, the full `department`, `owner_user_id`, `owner_display_name`,
`title`, `category`, `severity`, `community_support`, `created_at`. The detail view adds `issue` (summary, location,
reporter evidence refs, priority, merged duplicates, validated_at), `events[]` (sequence, action, from/to status,
reason, public_summary, actor_kind, actor_display_name, details, at), `transfers[]`, `escalations[]`, `evidence[]`,
`verifications[]`, `clarifications[]` and `tally`.

## Intake (coordinator)

### GET /api/authority/intake-queue
Module 5 handoffs in `PENDING_INTAKE` with no case: `{"handoffs": [{canonical_issue_id, routed_at, title, category,
severity, community_support, suggested_department}]}`.

### POST /api/authority/cases/intake
`{"canonical_issue_id": uuid, "department_id"?: int, "note"?: "0-500"}`. Without `department_id` the active
department with the lowest-priority matching jurisdiction rule is used. Calls Module 5 `acknowledge_handoff`.
`201 {"case": Case, "created": true}`. A repeat returns `200 {"created": false}` with the existing case.
Errors: 404 `HANDOFF_NOT_FOUND`; 409 `ISSUE_NOT_READY`, `OUT_OF_JURISDICTION`, `NO_DEPARTMENT`, `CASE_ALREADY_LINKED`.

## Reading (official: own department; coordinator: all)

- `GET /api/authority/cases?status=&overdue=true&department_id=&limit=&offset=` returns `{"cases", "total", "limit", "offset"}`.
- `GET /api/authority/cases/:id` returns `{"case": Case}`, or 403 `NOT_ASSIGNED` for another department's case.
- `GET /api/authority/cases/:id/issue-evidence/:evidence_id/file` returns a reporter photo listed in the handoff payload.

## Official actions (assigned department only, otherwise 403 `NOT_ASSIGNED`)

| Route | Body | From → to |
|---|---|---|
| `POST /cases/:id/acknowledge` | `{"note"?}` | ROUTED → ACKNOWLEDGED (sets owner) |
| `POST /cases/:id/progress` | `{"message": 5-1000, "public_summary"?: ≤300, "revised_due_at"?: ISO, future, ≤90 days}` | ACKNOWLEDGED / IN_PROGRESS / REOPENED → IN_PROGRESS; marks open escalations RESPONDED |
| `POST /cases/:id/evidence` | multipart `file` (PNG/JPEG ≤5 MB), `evidence_type` `PROGRESS`\|`RESOLUTION`, `caption`? | Status unchanged; at most 5 per round; `201 {"evidence"}` |
| `POST /cases/:id/resolve` | `{"summary": 10-1000}` | IN_PROGRESS → RESOLVED; opens the verification window. 409 `PROOF_REQUIRED` if no RESOLUTION photo in this round |
| `POST /cases/:id/request-clarification` | `{"question": 10-1000}` | ACKNOWLEDGED / IN_PROGRESS / REOPENED → CLARIFICATION_REQUESTED |

`POST /cases/:id/transfer` (official of the current department **or** coordinator): `{"to_department_id", "reason": 10-1000}`,
ROUTED / ACKNOWLEDGED → ROUTED with the new department. Errors: 409 `SAME_DEPARTMENT`, `OUT_OF_JURISDICTION`,
`TRANSFER_LOOP` (target already passed this case on), `TRANSFER_LIMIT`, `INVALID_STATE`.

An illegal move returns 409 `INVALID_STATE`. Every action appends an event and returns `{"case": Case}`.

## Coordinator actions

| Route | Body | Rule |
|---|---|---|
| `POST /cases/:id/escalate` | `{"reason": 10-1000, "acknowledge_simulated": true}` | Open cases; once per due cycle, otherwise 409 `ALREADY_ESCALATED` |
| `POST /cases/:id/reopen` | `{"reason": 10-1000}` | RESOLVED → REOPENED (round + 1, new due date) |
| `POST /cases/:id/close` | `{"reason": 10-1000}` | RESOLVED, window ended, zero votes; otherwise 409 `CLOSE_NOT_ALLOWED` |
| `POST /api/authority/admin/sweep` | `{}` | Runs the periodic job: `{"report": {escalated, closed, reopened, awaiting_coordinator}}` |

## Residents

### GET /api/civic/issues/:id/case-status
Any civic reader who can see the issue. A merged duplicate resolves to its canonical issue.
`{"case": null | Tracker, "canonical_issue_id"}`. **Tracker** = public status plus `timeline[]` (resident-facing
summaries only, no staff reasons), `evidence[]`, `verification` (`round, confirmed, disputed, close_threshold,
reopen_threshold, open, viewer_is_affected, viewer_can_verify, viewer_verdict`) and `open_clarification` (reporter only).

### POST /api/authority/cases/:id/verify
JSON `{"verdict": "CONFIRMED"|"DISPUTED", "reason"}`, or multipart with an optional `photo` (dispute only). A dispute
needs a 10-1000 character reason. `201 {"case": Tracker, "outcome": null|"CLOSED"|"REOPENED"}`.
Errors: 403 `NOT_AFFECTED` (not the reporter or a supporter), 403 `FORBIDDEN` (no active membership),
409 `VERIFICATION_CLOSED`, 409 `ALREADY_VERIFIED` (one per resident per round, enforced by a unique constraint).

### POST /api/authority/cases/:id/respond-clarification
Reporter only (anyone else gets 404). `{"response": 5-1000}` returns the case to its previous status.
409 `NO_OPEN_CLARIFICATION`.

### Files
- `GET /api/authority/evidence/:id/file`: official photos, for the assigned department, coordinators and residents who can view the issue.
- `GET /api/authority/verifications/:id/photo`: dispute photo, for its author, the assigned department and coordinators.

Files are served as attachments with `no-store`. Missing and forbidden both return 404.

### Notifications
`GET /api/authority/notifications` (latest 50 for the signed-in user, plus `unread`), and
`POST /api/authority/notifications/:id/read`.

## Directory (coordinator unless noted)

- `GET /api/authority/me` (any signed-in user): `{"officer": null | {id, title, department}, "is_coordinator"}`
- `GET /api/authority/departments` (staff): departments with `jurisdiction` and `escalation_rule`; coordinators also get `officers`
- `POST /api/authority/admin/departments`: `{"code", "name", "description"?, "contact_label"?, "requires_resolution_proof"?, "escalation_department_id"?}`, 409 `DEPARTMENT_EXISTS`
- `PATCH /api/authority/admin/departments/:id`: the same fields plus `is_active`
- `PUT /api/authority/admin/departments/:id/jurisdiction`: `{"categories": [IssueCategory], "priority"?: 1-1000}` replaces the coverage
- `PUT /api/authority/admin/departments/:id/escalation-rule`: `{"threshold_hours": 1-2160, "target_label"}`
- `POST /api/authority/admin/officers`: `{"email", "department_id", "title"?}`. Errors: 409 `USER_NOT_ELIGIBLE`, `ALREADY_OFFICER`, `SELF_ASSIGNMENT`
- `DELETE /api/authority/admin/officers/:id` revokes the assignment (history is kept)

## Analytics

### GET /api/admin/analytics/civic (coordinator)
`totals` (cases, open, overdue, pending_intake, transfers, reopens, reopened_cases), `by_status`, `by_department`,
`durations` (intake → acknowledge / first resolution / close: count, average, median, max hours), `escalations`,
`outcomes` (closed_by_basis, verification counts), `reconciliation` (`consistent`, `status_sum_matches_total`,
`mismatches[]`: current status vs last event, sequence gaps, missing close or resolve times, timestamp order),
`last_snapshot` and `audit` (latest 50 events).
