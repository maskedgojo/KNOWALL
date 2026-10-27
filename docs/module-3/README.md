# KNOWALL Module 3 — Society Operations & Engagement

## 1. Purpose

Residents book shared amenities, join society events, follow planned
maintenance and development projects, and report internal faults and track
the fix. Demo story step 3: *Rahul books a clubhouse slot, files a common-area
maintenance ticket, and tracks the fix.*

The team pack proposes Prisma. This module follows the existing repository
instead: Flask blueprints, SQLAlchemy models, Alembic migrations and the
Next.js App Router, with Module 1 sessions and permissions.

## 2. Status

| Feature | Status | Where |
|---|---|---|
| Amenity catalogue, rules, activate/deactivate | Implemented | `backend/app/modules/operations/facilities.py`, `/facilities`, `/admin/facilities` |
| Availability search, booking, approval or auto-confirm, cancel, history | Implemented | same |
| Conflict prevention | Implemented | Facility row locked (`SELECT … FOR UPDATE`) before the overlap check. PENDING and CONFIRMED bookings both hold the slot. |
| Blackout dates | Implemented | Overlapping held bookings are cancelled and the reason is stored in their history. |
| Events, RSVP, capacity, waitlist promotion, attendance | Implemented | `events.py`, `/events`, `/admin/events` |
| Event volunteers (limited places) and organiser updates | Implemented | `events.py`; volunteer roster is admin-only |
| Per-resident booking cap (`max_upcoming_per_resident`, optional) | Implemented | `facilities.py`; checked under the facility lock |
| Planned maintenance notices with updates | Implemented | `maintenance.py`, `/maintenance`, `/admin/maintenance` |
| Resident maintenance tickets: reported → assigned → in progress → completed → confirmed or reopened | Implemented | `maintenance.py`, `/maintenance/requests/[id]` |
| Development projects and milestones | Implemented | `development.py`, `/development`, `/admin/development` |
| Operations dashboard | Implemented | `dashboard.py`, card on `/dashboard` |
| Photo evidence on tickets (problem + fix) and milestones | Implemented | `photos.py`. JPG/PNG ≤ 5 MB, max 6 per record, stored privately via Module 1's `identity/documents/storage.py` in `OCR_PRIVATE_DIR`. Ticket photos follow ticket privacy. |
| Notifications (booking approved, event reminder, outage) | Missing | Same blocker as Module 2 M2-POL-13: no notification contract yet. Every change is in `audit_logs`. |
| Delegated committee roles | Missing | Needs a new Module 1 role; only a Society Admin manages operations. |
| Locality publishing of events (Module 4) | Hand-off flag only | `society_events.locality_publish_requested`. Nothing is published by Module 3. |

## 3. Permissions

| Code | Who | Used for |
|---|---|---|
| `society.facilities.book` | Eligible resident (already registered by Module 1) | Facilities, availability, own bookings |
| `society.maintenance.create` | Eligible resident (already registered by Module 1) | Own maintenance tickets |
| `society.notices.read` | Eligible resident | Events/RSVP, maintenance schedule, projects, dashboard |
| `society.operations.manage` | **New.** Verified `SOCIETY_ADMIN` only | All management routes |

`society.operations.manage` was added to `SOCIETY_ADMIN_PERMISSIONS` in
`backend/app/modules/identity/access/permissions.py`, and to the allowed set in
`backend/tests/test_module2_scaffold.py`. Tell the Module 1 owner.

## 4. Rules

- Times are stored in UTC. Facility hours are minutes after local midnight in
  IST (`SOCIETY_TZ` in `operations/common.py`).
- A booking must start on a slot boundary from opening time, last a multiple
  of the slot length, stay within hours and `max_minutes_per_booking`, not
  start in the past, and start within `booking_window_days`.
- One RSVP row per resident per event. Over capacity → `WAITLISTED`. When a
  `GOING` resident cancels, the oldest waitlisted resident becomes `GOING`.
  Rejoining after cancelling goes to the back of the queue.
- Tickets are private. Another resident gets 404, like private disputes.
  Residents cannot set ticket status; they can only CLARIFY, or CONFIRM/REOPEN
  after COMPLETED.
- A project can be marked COMPLETED only when every milestone is COMPLETED.
- Booking history, ticket timelines and maintenance updates are append-only.

## 5. Setup

From `backend/` with the virtual environment active:

```powershell
python -m flask --app app:create_app db upgrade    # applies a3d5f9c1e6b2, then c7e2b4a91f30
python -m flask --app app:create_app db current    # expect c7e2b4a91f30 (head)
python -m scripts.seed_green_valley                # adds Clubhouse, Badminton Court, a capacity-3 event,
                                                   # Lift B1 servicing and a lobby renovation project
```

No new Python or npm package and no new environment variable. Restart Flask
after upgrading; a process started with `--no-reload` before these routes
existed returns 404 for them.

## 6. Tests

```powershell
cd backend;  python -m pytest tests/test_operations_api.py -q
cd frontend; npm test; npm run typecheck; npm run lint; npm run build
```

The backend tests use in-memory SQLite, where `FOR UPDATE` is a no-op. They
prove the overlap rule, not concurrency. Concurrency must be checked on
PostgreSQL (see the manual script, step 3).

## 7. Manual demo script

1. Admin (`admin@greenvalley.test`) → **Amenities & bookings**. Confirm Clubhouse
   (approval) and Badminton Court (instant) exist.
2. Rahul → **Amenities** → Clubhouse → pick tomorrow 10:00 → request. Status
   PENDING. The 10:00 slot now shows *Booked*.
3. Priya → try the same Clubhouse slot → *That time is already booked*.
   For concurrency, send two `POST /api/bookings` for one slot at the same
   moment against PostgreSQL. Exactly one returns 201.
4. Admin → approve. Rahul → **My bookings** shows PENDING → CONFIRMED. Cancel
   it and the history shows the third step.
5. Admin → block the Badminton Court over a confirmed booking → the resident
   sees it CANCELLED with the reason.
6. Priya → **Maintenance** → report "Leaking shared pipe" (Plumbing). Rahul
   cannot open its URL (404).
7. Admin → **Maintenance** → assign "Plumber Ravi" → In progress → Completed.
8. Priya → open the request → *Still not fixed — reopen* with a reason. Admin
   completes it again → Priya confirms. The timeline shows every step.
9. Admin → **Society events**. The seeded Diwali event has capacity 3. Four
   residents RSVP and the fourth is waitlisted. One cancels and the waitlisted
   resident becomes Going.
10. Admin → **Development projects** → update a milestone and add a progress
    photo → residents see the new percentage and photo on **Development projects**.
11. Priya → open her ticket → upload a JPG of the leak. Admin → **Maintenance** →
    *Timeline & photos* → add a fix photo. Rahul cannot open either photo.
12. Admin → create an event with 1 volunteer place and post an update. Rahul
    volunteers; Priya sees no *Volunteer* button because the place is taken.
13. Admin → add a facility with *Max upcoming bookings per resident* = 1.
    Rahul's second booking there is refused with `BOOKING_LIMIT_REACHED`.

Failure paths to show: overlapping booking (409), booking outside hours (400),
resident calling an admin route (403), another resident opening a ticket (404),
completing a project with open milestones (400).

## 8. Cross-module boundaries

- Module 1: identity, membership and permissions. Bookings and tickets store
  the resident's active `membership_id`. Tickets also store the `flat_id`.
- Module 2: notices stay in Module 2. Planned maintenance is a separate,
  operations-specific feed.
- Module 4: may read `locality_publish_requested` events after its own review.
  It must never receive RSVP or attendee lists.
- Module 5: public roads and streetlights are civic issues, not tickets.

See [operations-v1 contract](../api-contracts/operations-v1.md) and
`backend/app/openapi.json` (tags *Society Operations*, *Society Operations — Admin*).
