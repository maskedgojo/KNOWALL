# KNOWALL Module 4 — Locality Intelligence & Community Discovery

## 1. Purpose

Residents find essential services around the society (pharmacies, clinics,
police, emergency and public services), see where each listing came from and
when it was last checked, follow local events and alerts, and report outdated
information. A Locality Coordinator keeps the directory accurate.

Demo story: *Rahul finds a pharmacy, notices its phone number is outdated and
reports it. The coordinator compares the old and proposed values, then
approves or rejects with a reason. Rahul sees the outcome in My corrections.*

This module follows the existing repository: a Flask blueprint, SQLAlchemy
models, one additive Alembic migration and Next.js App Router pages, using
Module 1 sessions, CSRF and permissions. Modules 1–3 were not rewritten.

**All locality data in this demo is fictional.** "Meadow Park (fictional)",
its 16 places, phone numbers (`+91 00000 …`), events and alerts are invented
and labelled "(demo)" and `FICTIONAL_DEMO`. Seeded verifications use the
`DEMO_SEED` method, so they are visibly simulated.

## 2. Status

| Feature | Status | Where |
|---|---|---|
| Locality profile, radius coverage, configurable re-verification window | Implemented | `locality/directory.py`, `/locality`, desk settings on `/locality/manage` |
| Coverage check for Module 5 (`GET /api/locality/coverage/check`) | Implemented | `directory.py` |
| Essential services directory: categories, server-side search, category filter | Implemented | `directory.py`, `/locality/places` |
| Map discovery | Implemented as a **schematic** SVG | `features/locality/shared.tsx` (`CoverageMap`). See limitations. |
| Place detail with source, last-verified date, method and stale warning | Implemented | `/locality/places/[id]` |
| Local events: resident submission, coordinator approval, upcoming/past | Implemented | `content.py`, `/locality/events`, `/locality/manage/events` |
| Sharing Module 3 society events (opt-in + Society Admin share + coordinator approval) | Implemented | `POST /api/locality/events/submit` with `source_event_id`; share section on `/locality/events` |
| Alerts with severity, source attribution, draft → publish, expiry, archive | Implemented | `content.py`, `/locality/alerts`, `/locality/manage/alerts` |
| Curated feed (pinned active alerts, events, directory updates) | Implemented | `GET /api/locality/feed`, `/locality` |
| Content reports on events and alerts | Implemented | `/locality/manage/reports` |
| Coordinator stewardship: create, edit (versioned), verify, flag for recheck, archive, restore, history | Implemented | `/locality/manage/places`, `/locality/manage/places/[id]` |
| Resident corrections, clarification round-trip, My corrections | Implemented | `corrections.py`, `/locality/corrections`, `/locality/manage/corrections` |
| Missing-service reports | Implemented | `POST /api/locality/corrections` |
| Notifications to reporters | Missing | Same blocker as Module 2/3: no notification contract. Status is visible in My corrections, and every change is in `audit_logs`. |
| Real map tiles / geocoding | Not implemented by design | See limitations. |

## 3. Permissions and roles

| Code | Who | Used for |
|---|---|---|
| `locality.read` | **New.** Eligible resident, verified Society Admin, Locality Coordinator | Browse profile, places, events, alerts, feed |
| `locality.listings.suggest` | Eligible resident (already defined by Module 1) | Corrections, missing services, event suggestions, content reports |
| `locality.manage` | **New.** `LOCALITY_COORDINATOR` role only | Everything under `/api/locality/admin/*` |
| `society.operations.manage` | Society Admin (Module 3) | Sharing an opted-in society event; listing shareable events |

- **New role `LOCALITY_COORDINATOR`** (`identity/models/role.py`). A Society
  Admin does **not** get `locality.manage` automatically. Locality stewardship
  is a separate duty, so grant the role deliberately.
- The coordinator role does not need a household membership. Someone who holds
  both RESIDENT and LOCALITY_COORDINATOR can moderate, but cannot decide their
  own correction (`403 SELF_REVIEW_FORBIDDEN`).
- Changes to shared Module 1 files are small and additive. Tell the Module 1
  owner about them:
  - `identity/access/permissions.py` adds `locality.read` and the coordinator
    permission set.
  - `identity/models/role.py` adds the enum value, widens the role check, and
    sets `length=30`.
  - The migration widens `role_assignments.role` from `VARCHAR(16)` to
    `VARCHAR(30)`, because `LOCALITY_COORDINATOR` is 20 characters.
- Frontend: coordinator screens live under `/locality/manage/*` inside the
  resident shell. `Protected admin` only admits Society or Platform Admins.
  Each screen is gated on `locality.manage`, and Flask checks every request
  again. A coordinator who is not also a resident lands on `/locality/manage`
  after login.

## 4. Rules

- **Locality scope** always comes from the configured society; the client never
  sends a locality id.
- **Verification state** is computed from stored data:
  - `ARCHIVED`
  - `NEEDS_RECHECK` (flagged by a coordinator)
  - `UNVERIFIED`
  - `STALE` (verified more than `stale_after_days` ago; default 180)
  - `VERIFIED`

  Staleness is shown to residents as a warning; it does not hide the listing.
- **Coverage:** place coordinates must fall inside the radius. A coordinator
  cannot shrink the radius while active places would fall outside it
  (`409 PLACES_OUTSIDE_COVERAGE`).
- **Sources:** every place has a `source_label`. `REAL_WORLD` places and
  `OFFICIAL_NOTICE` alerts require an http(s) source link. Links with any other
  scheme (`javascript:`, `data:`) are rejected by Flask and never rendered as
  clickable.
- **Conflict protection:**
  - Coordinator edits must send `expected_version`; a stale version returns
    `409 PLACE_VERSION_CONFLICT`.
  - Each correction snapshots the published value when it is submitted. If the
    listing changed since then, approval is refused with
    `409 PLACE_CHANGED_SINCE_SUBMISSION`.
  - Corrections and places are row-locked during a decision.
  - One reporter can have only one open correction per place and field, and at
    most 10 open corrections in total (`429`).
- **Decisions need a reason:**
  - Corrections need 5–1000 characters.
  - Events, alerts and reports need at least 3 characters.
  - The reporter sees the decision and its reason, but never the reviewer's
    identity.
- **Approving a correction:**
  - It changes only the reported field.
  - It records a `PlaceVerification` with method `CORRECTION_REVIEW`, scoped to
    that field. It is not a whole-listing verification, so a stale listing
    stays stale until a coordinator verifies all of it.
  - `MOVED_OR_CLOSED` and `DUPLICATE` archive the place.
- **Society events** reach the locality only if all of these hold:
  1. Module 3 `locality_publish_requested` is ticked.
  2. The event is PUBLISHED.
  3. The Society Admin shares it.
  4. A coordinator publishes it.

  Only title, description, venue and times are copied, plus the society name as
  organiser. RSVPs, capacity and volunteers are never copied. If Module 3
  cancels or un-shares the event, it disappears from the locality.
- **Alerts:**
  - They start as DRAFT and run for at most 30 days.
  - They become EXPIRED automatically and move to the archive.
  - An active HIGH alert is pinned first.
- **History:** every change is written to the append-only `locality_history`
  and to the shared `audit_logs` (`LOCALITY_*` actions). Residents see place
  history without actor names.

## 5. Setup

From `backend/` with the virtual environment active:

```powershell
# 1. Add to backend/.env (must differ from the admin and resident passwords, 12+ characters)
#    KNOWALL_SEED_COORDINATOR_PASSWORD=...
python -m flask --app app:create_app db upgrade    # applies e5c1a9d3f742 (Module 4)
python -m flask --app app:create_app db current    # expect e5c1a9d3f742 (head)
python -m scripts.seed_green_valley                # society and demo users (if not already seeded)
python -m scripts.seed_locality                    # locality, 6 categories, 16 places, 4 events, 3 alerts, coordinator
```

The seed can be re-run safely: it never deletes, resets or reactivates
anything. No new Python or npm package is needed. **Restart Flask and
`next dev` after upgrading.** A Flask process started before these routes
existed returns 404 for `/api/locality/*`.

| Email | Role | Password source |
|---|---|---|
| `kavya@greenvalley.test` | Locality Coordinator (no household) | `KNOWALL_SEED_COORDINATOR_PASSWORD` |
| `rahul@greenvalley.test` | Resident (can browse and report) | `KNOWALL_SEED_RESIDENT_PASSWORD` |
| `admin@greenvalley.test` | Society Admin (read and share events only) | `KNOWALL_SEED_ADMIN_PASSWORD` |

Seeded place states, for demonstrating each badge:

| State | Places |
|---|---|
| Verified | Meadow Care Pharmacy (its phone is deliberately "outdated" for the demo), Sunrise Multispeciality Hospital, Community Ambulance Point |
| Stale | Evergreen Medicals, Lakeview Police Outpost, Ward 4 Municipal Office |
| Unverified | NightOwl 24x7 Chemist, Lakeview Gas Agency |
| Flagged for recheck | Little Steps Child Clinic |
| No map location | Electricity Complaint Centre |

## 6. Tests

```powershell
cd backend;  python -m pytest tests/test_locality_api.py -q
cd frontend; node --test tests/*.test.cjs; npm run typecheck; npm run lint; npm run build
```

On Windows, `npm test` may not expand the `tests/*.test.cjs` glob. Run
`node --test` directly.

- **Backend (15 tests, in-memory SQLite) cover:**
  - directory search, filters and escaping
  - role boundaries: applicant, resident, Society Admin, Platform Admin and
    coordinator
  - the create/edit/verify/archive lifecycle, version conflicts and coverage
    shrink protection
  - the full correction flow: approve, reject, clarification, stale-snapshot
    conflict, self-review and closed-place archiving
  - resident events
  - society event sharing, with no RSVP leakage, including disappearance on
    cancellation
  - the alert lifecycle and feed
  - content reports
  - CSRF
- **SQLite caveat:** `FOR UPDATE` is a no-op in SQLite, so these tests prove the
  rules, not concurrency.
- **Frontend:** `tests/locality.test.cjs` covers:
  - nav gating
  - desk gating
  - coordinator login routing
  - that every client route exists in the Flask blueprint
  - that decisions carry a reason
  - the `expected_version` edit
  - fictional, stale and source labels
  - safe links
  - that no RSVP data is shown
  - the schematic map label

## 7. Manual demo script

1. Sign in as `rahul@greenvalley.test`.
   1. Open **Locality → Essential services**.
   2. Note the fictional-data banner, the category filter and the schematic map.
      Hovering a result highlights its marker, and clicking a marker scrolls to
      its result.
2. Search `pharmacy` and open **Meadow Care Pharmacy (demo)**.
   - It shows the source, last-verified date and method, and the "Verified"
     badge.
   - Open **Evergreen Medicals (demo)** to see the stale warning.
3. On Meadow Care, choose **Report outdated information** and pick *Phone
   number is wrong*.
   1. Enter `+91 00000 19999` with a reason, then submit.
   2. The listing still shows the old number.
   3. **My corrections** shows *Pending*.
4. Sign out. Sign in as `admin@greenvalley.test`.
   - Under **Locality** there is no desk.
   - `/locality/manage` shows "Only a Locality Coordinator can open this desk",
     and the API returns 403.
5. Sign in as `kavya@greenvalley.test`. You land on the **Locality desk**,
   whose work queue shows one correction.
   1. Open **Corrections**. The review shows *When reported* / *Published now*
      / *Proposed*.
   2. Try **Approve** with no reason: the button stays disabled, and the API
      returns 400.
   3. Enter "Called the shop and confirmed the new number." and approve.
6. Sign back in as Rahul.
   - The pharmacy shows `+91 00000 19999`.
   - Its history shows *Correction Applied*.
   - **My corrections** shows *Approved* with the reason, and no reviewer name.
   - The **Locality overview** feed shows "Listing corrected".
7. **Rejection path:** report a phone change on another pharmacy. As Kavya,
   **Reject** it with a reason. Rahul sees *Rejected* and the reason.
8. **Clarification path:** report an address change. As Kavya, choose **Ask
   for clarification**. As Rahul, reply from **My corrections**; it returns to
   *Pending*.
9. **Conflict:** submit a phone correction, then as Kavya edit that phone
   directly on the place page. The correction review now warns *Listing
   changed since report*, and approval is blocked.
10. **Events:**
    1. As Rahul, choose **Local events → Suggest an event**; it is pending.
    2. As Kavya, publish it under **Events**.
    3. As `admin@…`, in **Society events** create an event with *Request
       locality listing* ticked.
    4. Then, on **Locality → Share society events**, share it. As Kavya,
       publish it.
    5. Residents see "Shared by the society" with no RSVP counts.
11. **Alerts:**
    1. As Kavya, create an Official Notice alert. Without a link it is
       refused.
    2. Publish it; it is pinned on the overview.
    3. As Rahul, **Report a problem** on it.
    4. As Kavya, under **Reports**, choose **Archive the content** with a
       reason.

## 8. Limitations

- **Schematic map, not a street map.** The locality and every listing are
  fictional. Real map tiles would place invented businesses on real streets,
  which is misleading. The SVG shows distance and direction from the society
  centre, within the coverage circle. A coordinator could swap in a tile map
  once real, sourced `REAL_WORLD` data exists. No map library or API key was
  added.
- **Seed coordinates are not a survey.** The centre (20.3000, 85.8200) is an
  arbitrary placeholder point. No claim is made about what is actually
  located there.
- No geocoding: coordinates are entered by hand.
- No notifications (see Status).
- Only one locality per society, matching the single-society Module 1 design.
- The text search is a database `ILIKE` and is not ranked.

## 9. Cross-module boundaries

- **Module 1:**
  - Reuses sessions, CSRF, `requires_permission`, `audit_logs` and
    `users.display_name`.
  - Adds the `LOCALITY_COORDINATOR` role and `locality.read` (see §3).
  - Granting the coordinator role uses the existing `role_assignments` table.
    The seed grants it to Kavya.
- **Module 3:**
  - Reads `society_events` only to share opted-in published events.
  - No Module 3 file was changed.
  - RSVP, capacity and volunteer data are never read into locality responses.
- **Module 5 (not implemented here):**
  - It can call `GET /api/locality/coverage/check?latitude=&longitude=` and
    `GET /api/locality/places?category=` (emergency categories carry
    `is_emergency: true`).
  - Category keys are stable: `pharmacy`, `hospital_clinic`, `police`,
    `emergency`, `public_service`, `other_service`.
- **API contract:** all 37 locality operations (34 paths) are documented in
  `backend/app/openapi.json` under the tag *Locality (Module 4)*.
