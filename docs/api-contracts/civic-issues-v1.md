# Civic Issues API v1 (Module 5)

Base path `/api/civic`. Same-origin session cookie; every write needs the `X-CSRF-Token` header from
`GET /api/auth/csrf`. Responses use `Cache-Control: no-store`.

Errors share one shape: `{"error": {"code": "...", "message": "...", "fields": {"field": "..."}}}`
(`fields` only when relevant).

## Permissions

| Marker | Requirement |
|---|---|
| **R** | `civic.issues.create` (eligible resident). Coordinators may also read. |
| **S** | `civic.issues.support` (eligible resident) |
| **A** | `identity.admin.manage` (moderator stand-in, see the module README) |

Unauthenticated: 401 `AUTH_REQUIRED`. Authenticated without the permission: 403 `FORBIDDEN`.
Missing and not-visible resources both return 404.

## Issue object

```json
{
  "id": "uuid", "locality_id": 1, "title": "", "description": "",
  "category": "ROAD_DAMAGE", "severity": "HIGH", "state": "VALIDATED",
  "latitude": 20.2964, "longitude": 85.8248, "address_hint": "",
  "privacy": "ANONYMOUS | PUBLIC_NAME | null", "reporter_display_name": "A resident",
  "viewer_is_reporter": false, "support_count": 2, "viewer_has_supported": false,
  "evidence_count": 1,
  "evidence": [{"id": "uuid", "caption": "", "visibility": "PRIVATE", "mime_type": "image/png", "created_at": ""}],
  "priority": {"score": 14.0, "band": "LOW",
               "inputs": {"supporters": 2, "supporter_points": 4, "days_open": 0.0, "age_points": 0.0,
                          "severity": "HIGH", "severity_points": 10},
               "formula": "", "disclaimer": ""},
  "canonical_issue_id": null,
  "handoff": {"routing_status": "PENDING_INTAKE", "routed_at": "", "authority_case_id": null, "acknowledged_at": null},
  "created_at": "", "submitted_at": "", "validated_at": "", "updated_at": ""
}
```

`reporter_user_id` appears for coordinators only. `privacy` is shown to the reporter and coordinators only.
The detail endpoint adds `authoritative_status` (Module 6, null until integrated) and, to the reporter and
coordinators, `readiness: {unmet: [...], required_supporters: 3}`. Contact details are never returned.

Enums. Category: `ROAD_DAMAGE STREETLIGHT GARBAGE DRAINAGE WATER_SUPPLY FOOTPATH TRAFFIC PUBLIC_SPACE OTHER`.
Severity: `LOW MEDIUM HIGH CRITICAL`. State: `DRAFT SUBMITTED UNDER_REVIEW NEEDS_INFO VALIDATED
READY_FOR_ROUTING REJECTED MERGED WITHDRAWN`.

## Resident endpoints

### GET /locality — R
`{"locality": {"id", "name", "center_lat", "center_lon", "radius_m", "required_supporters", "max_evidence_per_issue"}}`

### GET /issues — R
Query: `mine=true` (own issues, every state), `category`, `severity`, `state`, `q` (title or description),
`near_lat`+`near_lon`+`radius_m` (10-5000), `sort=recent|support|priority`, `limit` (1-100, default 30),
`offset`. Without `mine`, only community-visible states are returned.
Response `{"issues": [Issue], "total", "limit", "offset"}`.

### POST /issues — R
Body: `title` (8-160), `description` (20-2000), `category`, `latitude`, `longitude`; optional `severity`
(default MEDIUM), `address_hint` (max 160), `privacy` (default ANONYMOUS), `save_as_draft` (default false).
Text must be plain: no HTML, phone numbers or email addresses. The point must be inside the coverage circle.
`201 {"issue": Issue, "similar": [Issue + match]}`. `similar` lists nearby open matches and never merges.
Errors: 400 `VALIDATION_ERROR`, 429 `RATE_LIMITED` (10 per rolling day), 503 `LOCALITY_NOT_CONFIGURED`.

### GET /issues/similar — R
Query: `category`, `lat`, `lon` (required); `title`, `radius_m` (10-500, default 150), `exclude_id`.
`{"similar": [Issue + {"match": {"distance_m", "title_similarity", "match_score"}}], "radius_m", "note"}`.
Max 5, same category, open states, within the radius. Text alone never matches.

### GET /issues/:id — R
`{"issue": Issue}`. 404 `ISSUE_NOT_FOUND`.

### PATCH /issues/:id — R, reporter, DRAFT or NEEDS_INFO
Any of `title description category severity latitude longitude address_hint privacy`. 409 `INVALID_STATE`.

### POST /issues/:id/submit — R, reporter
Body `{"note": "optional"}`. DRAFT or NEEDS_INFO to SUBMITTED. 409 `INVALID_STATE`.

### DELETE /issues/:id — R, reporter
Soft withdraw from DRAFT, SUBMITTED or NEEDS_INFO. History is kept. 409 `INVALID_STATE`.

### GET /issues/:id/timeline — R
`{"issue_id", "state", "events": [...], "support_count", "priority", "authoritative_status"}`.
Events: `{"type": "STATE_CHANGE", "from_state", "to_state", "actor_role", "reason", "at"}`,
`{"type": "ROUTED", "routing_status", "at"}`, `{"type": "AUTHORITY_ACKNOWLEDGED", "authority_case_id", "at"}`.
`reason` is empty for anyone but the reporter and coordinators.

### POST /issues/:id/support — S
`201 {"support_count", "viewer_has_supported": true, "priority"}`.
Errors: 404 `ISSUE_NOT_FOUND`; 409 `NOT_OPEN_FOR_SUPPORT` (not yet validated), `ALREADY_SUPPORTED`,
`OWN_ISSUE`, `ISSUE_MERGED` (`fields.canonical_issue_id`).

### DELETE /issues/:id/support — S
Only while `VALIDATED`. Errors: 409 `INVALID_STATE`, 404 `NOT_SUPPORTING`.

### POST /issues/:id/report — R
Body `{"concern_type": "ABUSIVE|SENSITIVE_IMAGE|PERSONAL_INFO|FALSE_INFO|OFF_TOPIC|OTHER", "concern": "10-1000 chars"}`.
`201 {"report": {"id", "status": "OPEN"}}`. Errors: 409 `OWN_ISSUE`, `ALREADY_REPORTED`.

### POST /issues/:id/evidence — R, reporter
`multipart/form-data`: `file` (JPG or PNG, max 5 MB), optional `caption`, `visibility` (`PRIVATE` default or
`RESIDENTS`). Allowed in DRAFT, SUBMITTED, NEEDS_INFO, UNDER_REVIEW, VALIDATED. Max 5 per issue.
`201 {"evidence": {...}}`. Errors: 400 `INVALID_DOCUMENT`, 409 `EVIDENCE_LIMIT_REACHED`, `INVALID_STATE`,
415 `UNSUPPORTED_MEDIA_TYPE`, 503 `UPLOAD_FAILED`.

### DELETE /issues/:id/evidence/:evidenceId — R, reporter
`{"removed": true}`. Same states as upload.

### GET /evidence/:id/file — R
Downloads the original as an attachment. Reporter, coordinators and (for `RESIDENTS` photos on visible issues)
other residents only. Otherwise 404 `EVIDENCE_NOT_FOUND`.

## Coordinator endpoints (A)

All return `{"issue": Issue}` (with detail fields) unless stated. Illegal moves return 409 `INVALID_STATE`.

| Method and path | Body | Effect |
|---|---|---|
| GET `/admin/issues` | query `state`, `limit`, `offset` | Queue; default SUBMITTED, UNDER_REVIEW, NEEDS_INFO, VALIDATED. `{issues, total, limit, offset}` |
| POST `/admin/issues/:id/review` | none | SUBMITTED to UNDER_REVIEW |
| POST `/admin/issues/:id/validate` | `note?`, `severity?` | to VALIDATED; stores a priority snapshot |
| POST `/admin/issues/:id/needs-info` | `reason` (5-500) | to NEEDS_INFO; the reporter sees the reason |
| POST `/admin/issues/:id/reject` | `reason` (5-500) | to REJECTED |
| POST `/admin/issues/:id/merge` | `canonical_issue_id`, `reason`, `acknowledge_distance?` | `{duplicate, canonical}`; duplicate becomes MERGED |
| POST `/admin/evidence/:id/visibility` | `visibility` | Share or hide a photo |
| GET `/admin/reports` | query `status=OPEN|RESOLVED` | `{reports: [...]}` |
| POST `/admin/reports/:id/resolve` | `disposition`, `note` | See below |

Merge errors: 422 `LOCATIONS_TOO_FAR` (over 150 m without `acknowledge_distance`), 409 `CATEGORY_MISMATCH`,
`INVALID_CANONICAL`, `INVALID_STATE` (already routed or already merged), 400 (target equals source).
Merging a canonical issue repoints its existing duplicates to the new canonical.

Report dispositions: `DISMISSED`; `REDACTED` (description replaced, original kept for moderators, photos
made private); `CORRECTION_REQUESTED` (issue to NEEDS_INFO); `REMOVED` (issue to REJECTED). A report resolves
once: 409 `INVALID_STATE` afterwards.

## Hand-off (A)

### POST /issues/:id/route
Requires `VALIDATED`, at least `required_supporters` supporters and one photo. Moves the issue to
`READY_FOR_ROUTING`, stores the payload and a priority snapshot.
`201 {"handoff": {"id", "canonical_issue_id", "routing_status": "PENDING_INTAKE", "routed_at",
"authority_case_id": null, "acknowledged_at": null, "payload": {...}}, "issue": Issue}`.
Errors: 409 `NOT_READY_FOR_ROUTING` (`fields.criterion_N` explains each gap), `ALREADY_ROUTED`.

Payload keys: `canonical_issue_id category severity title summary location evidence community_support priority
merged_duplicate_issue_ids validated_at demonstration_data`.

### POST /issues/:id/handoff/acknowledge
Body `{"authority_case_id": "3-64 chars"}`. Demonstration stand-in for Module 6 intake; sets
`routing_status` to `ACKNOWLEDGED`. Same id again returns 200; a different id returns 409 `CASE_ALREADY_LINKED`;
an unrouted issue returns 404 `HANDOFF_NOT_FOUND`.

## Module 6 integration points

| Direction | Contract |
|---|---|
| 5 to 6 | The routing payload above, keyed by `canonical_issue_id`, which stays stable forever. |
| 6 to 5 | Call `app.modules.civic.handoff.acknowledge_handoff(issue_id, authority_case_id)` and commit. |
| 5 reads 6 | `app.modules.authority.public.case_status_for_issue(issue_id) -> dict | None`, shown as `authoritative_status`. |

## Common errors

`VALIDATION_ERROR` 400, `UNSUPPORTED_MEDIA_TYPE` 415, `ISSUE_NOT_FOUND` 404, `INVALID_STATE` 409,
`RATE_LIMITED` 429, `SCHEMA_NOT_READY` 503 (migration not applied), `LOCALITY_NOT_CONFIGURED` 503.
