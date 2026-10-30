# Module 3 Operations V1 — API contract

Canonical request and response detail lives in `backend/app/openapi.json`.
All mutations need the Flask session cookie and `X-CSRF-Token`. Errors use
the shared `{"error": {"code", "message", "fields?"}}` shape. Every route
returns `503 SCHEMA_NOT_READY` until migrations `a3d5f9c1e6b2` and
`c7e2b4a91f30` are applied.

## Resident

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/api/operations/dashboard` | `society.notices.read` | Own upcoming bookings and open tickets; events, disruptions, projects |
| GET | `/api/facilities` | `society.facilities.book` | Active facilities |
| GET | `/api/facilities/{id}/availability?date=YYYY-MM-DD` | `society.facilities.book` | IST day; slot `reason` ∈ PAST, OUTSIDE_BOOKING_WINDOW, BLOCKED, BOOKED |
| POST | `/api/bookings` | `society.facilities.book` | `{facility_id, starts_at, ends_at, purpose}` → 201 PENDING/CONFIRMED; 409 `SLOT_UNAVAILABLE` / `FACILITY_UNAVAILABLE` |
| GET | `/api/bookings/me` | `society.facilities.book` | With `history[]` |
| POST | `/api/bookings/{id}/cancel` | `society.facilities.book` | Own only; before start |
| GET | `/api/events`, `/api/events/{id}` | `society.notices.read` | Drafts hidden; `going_count`, `waitlist_count`, `my_rsvp` |
| POST / DELETE | `/api/events/{id}/rsvp` | `society.notices.read` | 409 `ALREADY_RESPONDED`, `EVENT_CLOSED`; delete promotes waitlist |
| GET | `/api/maintenance` | `society.notices.read` | Planned maintenance + updates |
| POST | `/api/maintenance/requests` | `society.maintenance.create` | `{issue_type, title, description, location_note?}` |
| GET | `/api/maintenance/requests/me`, `/api/maintenance/requests/{id}` | `society.maintenance.create` | Own only; others 404 |
| POST | `/api/maintenance/requests/{id}/feedback` | `society.maintenance.create` | `{action: CLARIFY\|CONFIRM\|REOPEN, message?}` |
| GET | `/api/development`, `/api/development/{id}` | `society.notices.read` | With milestones, milestone `photos[]` and `progress_percent` |
| POST / DELETE | `/api/events/{id}/volunteer` | `society.notices.read` | `{note?}`; 409 `VOLUNTEER_SLOTS_FULL`, `ALREADY_VOLUNTEERED` |
| POST | `/api/maintenance/requests/{id}/photos` | reporter (`society.maintenance.create`) or admin | multipart `file` (JPG/PNG ≤ 5 MB) + `caption?`; max 6; 409 `PHOTO_LIMIT_REACHED` |
| GET | `/api/operations/photos/{photo_id}/file` | ticket: reporter/admin · milestone: residents/admin | Attachment download; others 404 |

`POST /api/bookings` may also return 409 `BOOKING_LIMIT_REACHED` when the
facility has `max_upcoming_per_resident` set.

## Society Admin (`society.operations.manage`)

| Method | Path | Notes |
|---|---|---|
| GET / POST | `/api/admin/facilities` | Minutes after IST midnight for `open_minute` / `close_minute` |
| PATCH | `/api/admin/facilities/{id}` | Any rule; `is_active` hides it |
| POST | `/api/admin/facilities/{id}/blackouts` | Returns `cancelled_booking_ids` |
| GET | `/api/admin/bookings?status=` | With `resident_display_name` |
| POST | `/api/bookings/{id}/decision` | `{decision: APPROVE\|REJECT, reason}`; reason required to reject |
| GET | `/api/admin/events` | Includes drafts |
| POST | `/api/events` | Creates DRAFT |
| POST | `/api/events/{id}/publish` · `/cancel` · `/close` | 409 on invalid transition |
| GET | `/api/admin/events/{id}/attendees` | Admin only |
| POST | `/api/events/{id}/attendance` | `{user_id, attended}` for a GOING resident |
| GET | `/api/admin/maintenance` | |
| POST | `/api/maintenance` | Planned notice |
| POST | `/api/maintenance/{id}/updates` | `{message, status?}` PLANNED → IN_PROGRESS → RESOLVED |
| GET | `/api/admin/maintenance/requests?status=` | With `reporter_display_name` |
| PATCH | `/api/maintenance/requests/{id}/status` | `{status, message, assignee_label?}` |
| GET | `/api/admin/development` | |
| POST / PATCH | `/api/development`, `/api/development/{id}` | COMPLETED needs all milestones complete |
| POST / PATCH | `/api/development/{id}/milestones[/{milestone_id}]` | `percent` 0–100; COMPLETED sets 100 |
| POST | `/api/development/{id}/milestones/{milestone_id}/photos` | multipart progress photo |
| POST | `/api/events/{id}/updates` | `{message}` organiser update shown to residents |

Facility create/update also accepts `max_upcoming_per_resident` (1–50, or
`null` for no cap). Event create accepts `volunteer_slots` (0–200, default 0).
The attendees response also lists `volunteers[]`.

## Audit actions

`BOOKING_REQUESTED`, `BOOKING_DECIDED`, `BOOKING_CANCELLED`, `FACILITY_CREATED`,
`FACILITY_UPDATED`, `FACILITY_BLACKOUT_ADDED`, `EVENT_CREATED`, `EVENT_PUBLISHED`,
`EVENT_CANCELLED`, `EVENT_CLOSED`, `EVENT_RSVP`, `EVENT_RSVP_CANCELLED`,
`EVENT_ATTENDANCE`, `MAINTENANCE_SCHEDULED`, `MAINTENANCE_UPDATED`,
`MAINTENANCE_REQUEST_REPORTED`, `MAINTENANCE_REQUEST_STATUS`,
`MAINTENANCE_REQUEST_FEEDBACK`, `PROJECT_CREATED`, `PROJECT_UPDATED`,
`PROJECT_MILESTONE_ADDED`, `PROJECT_MILESTONE_UPDATED`, `EVENT_VOLUNTEERED`,
`EVENT_VOLUNTEER_WITHDRAWN`, `EVENT_UPDATE_POSTED`, `OPERATION_PHOTO_ADDED`.
Details never contain ticket descriptions or file contents.
