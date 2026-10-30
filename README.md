# KNOWALL — Module 1: Identity, OCR & Resident Access Management

**Green Valley Residency · Single-society demo · Flask + PostgreSQL + Next.js**

> **Documentation baseline:** 24 October 2026. This README **replaces the historical Phase 5-only README**. It describes the consolidated Module 1 design through shared authorization, family/profile enhancements, sponsor-aware review, and the revised **direct family activation** policy. The latest policy patch and live cross-application workflows still require final verification against each teammate's actual checkout; do not treat this document as a production certification.

## 1. Overview

KNOWALL is a residential community-management and civic-engagement platform divided into six integrated modules. **Module 1 is the shared identity and residential-access foundation**. It connects user accounts to the correct flat and household, handles Owner/Tenant verification, manages sponsor-based Family Member access, and publishes effective permissions for the other modules.

**Scope:** one fictional property, **Green Valley Residency**, with **4 towers (A–D)** and **240 flats (60 per tower)**. No multi-society switching, payments, government integrations, Redis, Docker, or separate authentication/AI microservice is required for this release.

### Delivery / verification status

| Area | Implementation | Verification note |
|---|---|---|
| Phases 1–9: models, auth, onboarding, OCR, admin, shared access | Implemented; earlier local regression suites reported passing | Retest after applying newer patches |
| Family/profile, occupancy and sponsor-aware admin context | Patch delivered | Confirm applied migration, API behavior and tests locally |
| Revised direct Family Member activation | Patch delivered | **Live Gmail + PostgreSQL + browser E2E confirmation pending** |
| Exceptional evidence requests and household directory | Patch delivered | Verify storage permissions, review cycle and retention command locally |
| Next.js integration | Frontend pages and integration patches delivered | Final full browser E2E, production build and concurrency checks are pending |

**Module 4 (Locality Intelligence & Community Discovery)** is documented in [`docs/module-4/README.md`](docs/module-4/README.md): migration `e5c1a9d3f742`, `python -m scripts.seed_locality`, and the new `KNOWALL_SEED_COORDINATOR_PASSWORD` setting.

**The backend owns identity and permissions.** Frontend visibility checks never replace Flask authorization. OCR never authenticates a document or approves a resident. Voting policy and ballots belong to **Module 2**.

## 2. Tech stack

| Layer | Technology / purpose |
|---|---|
| Backend | Python, Flask application factory, modular monolith |
| Database | PostgreSQL; SQLAlchemy / Flask-SQLAlchemy; Flask-Migrate / Alembic |
| Authentication | Flask-Login, HTTP-only session cookies, CSRF token for modifying requests |
| Passwords and recovery | Werkzeug password hashes, expiring one-time email verification and password-reset tokens |
| Email | Python `smtplib`; console mode for local demos or Gmail/other SMTP provider |
| OCR | **Surya OCR 2 (`surya-ocr==0.22.1`)** via llama.cpp/`llama-server` for on-demand extraction |
| File storage | Local private, random-key storage outside public/static folders; content/type/size checks |
| Frontend | Next.js 16 App Router, React, TypeScript strict mode, Tailwind CSS v4, typed Fetch API client |
| API documentation | OpenAPI 3.0 (`backend/app/openapi.json`), Swagger UI at `/docs` |
| Testing | Pytest (Flask); TypeScript/lint/frontend tests; manual Swagger and live E2E checks |

**Local development endpoints**

- Next.js: `http://localhost:3000`
- Flask: `http://127.0.0.1:5000` (Swagger can be opened at `http://localhost:5000/docs`)
- The browser calls **relative `/api/*`**; Next.js rewrites requests to Flask. Do not create a second Next.js API/authentication backend.

```text
Browser → Next.js :3000 → /api/* rewrite → Flask :5000
                                             │
                    ┌────────────────────────┼──────────────────┐
                    ↓                        ↓                  ↓
              PostgreSQL              Private files        Surya OCR 2
                                   (Owner/Tenant proof)  → llama.cpp
```

## 3. Implemented features

| Area | Capabilities |
|---|---|
| Society directory | Fictional society profile, towers, flats and floor filtering; no private occupant data in public endpoints |
| Accounts | Register, login, logout, `/me`, email verification/resend, forgot/reset password, profile update |
| Hybrid onboarding | Owner/Tenant self-applications **or** admin invitations; draft, submit, correction, rejection and approval |
| Household model | User ≠ flat ≠ household ≠ membership. Separate Owner and Tenant households can share one flat |
| Sponsored family access | Eligible Owner/Tenant sends invitation to a verified email; valid acceptance creates ACTIVE family membership directly |
| Personal / family details | Display name, email, optional phone, birth date and occupation; sponsor relationship and household tree |
| Occupancy | Resident self-declaration is separate from nullable **administrator-confirmed** occupancy |
| Document verification | Private Owner/Tenant PDF/JPG/PNG upload, authorized download, stored OCR results, field comparisons and warnings |
| Human review | Admin application queue, approve/reject/correction with reasoning, private evidence and audit history |
| Member administration | Directory, suspend/reinstate/revoke, relationship correction, occupancy confirmation |
| Household directory | Admin-only household-grouped view with sponsor, family links, validity and effective access |
| Exceptional evidence | Admin requests targeted additional proof; member uploads privately; admin accepts/rejects/cancels |
| Shared authorization | Reusable permission decorator, live membership/sponsor/date checks, scoped resident/admin capabilities |
| Audit | Tracks sensitive decisions, membership changes, family activation and evidence workflows |

### Final onboarding rules

**A. Owner or Tenant — application-based approval**

1. User registers and verifies their own email, then logs in.
2. User selects Tower / Flat and `OWNER` or `TENANT`, or accepts an administrator's invitation.
3. **Self-application** creates a draft; an accepted Owner/Tenant invitation returns an application draft.
4. Applicant provides relevant details, optional declared occupancy and required residence evidence.
5. Flask stores the evidence privately; Surya extracts candidate text/fields on demand. Mismatches are advisory.
6. Applicant submits; admin inspects the **original document** and any OCR findings.
7. Admin approves, rejects or requests correction. Approval creates/activates the eligible membership and access; rejected/correction cases do not silently gain access.
8. Tenant validity dates are enforced; an Owner and Tenant can coexist at a flat in **different households**.

**B. New Family Member — invitation-based direct activation**

1. An **eligible, verified Owner or Tenant** invites a Family Member to their **specific existing household and flat**.
2. Invitee signs into their **own account**, verifies the invited email, and opens the **single-use email link**.
3. Flask validates token, expiry, email, sponsor's effective membership/role, exact household/flat, relationship rules and duplicates.
4. `POST /api/invitations/accept` atomically creates an **ACTIVE `FAMILY_MEMBER` membership**, links its `sponsor_membership_id`, records the declared relationship, updates invitation/audit records and returns effective access.
5. Frontend refreshes `/api/auth/me`, `/api/me/access`, and `/api/me/memberships`, then goes directly to the resident dashboard.

**No routine admin approval, uploaded document, OCR or application submission for new family invitations.** Relationship labels are declared, not independently legally verified. **Existing historical pending family applications remain pending** and are not silently auto-approved.

**C. Exception: targeted evidence review**

Admin may request a specific household member's evidence **with a reason**. The member receives an in-app request, uploads authorized private evidence, and an admin reviews/resolves it. Merely having a pending request **does not suspend membership**. Evidence is not automatically sent to Surya.

**D. Eligibility, suspension and voting**

Membership's stored `status=ACTIVE` does **not** always mean effective access. A date-expired membership, suspended account or ineligible sponsor can remove effective resident capabilities; the original database row remains available for audit. **Household membership alone never grants voting rights**; Module 2 determines voter eligibility by proposal and policy.

### Invitation acceptance contract (important for the frontend)

`POST /api/invitations/accept` requires a Flask session, verified matching email and `X-CSRF-Token`.

```json
{
  "token": "TOKEN_FROM_PRIVATE_EMAIL_LINK",
  "relationship_to_sponsor": "SPOUSE",
  "declared_current_occupant": true
}
```

For `OWNER` / `TENANT`, **omit** `relationship_to_sponsor`. On success (HTTP 201), inspect `outcome`:

| `outcome` | Returned result | Frontend next action |
|---|---|---|
| `FAMILY_MEMBERSHIP_ACTIVATED` | `membership` + refreshed access; `application: null` | Refetch identity/access/memberships → `/dashboard` |
| `APPLICATION_DRAFT_CREATED` | `application` with `id`, `status: DRAFT`; `membership: null` | Continue `/onboarding/[id]`, evidence and admin approval |

**Use the response's `outcome`, not assumptions based on UI labels.** Invalid, mismatched-email, expired or reused invitations and ineligible sponsors are rejected by Flask.

## 4. Data model and boundaries

The relevant model groups are:

- **Identity:** `users`, `auth_tokens`, `role_assignments`, `audit_logs`.
- **Residence:** singleton `society_profile`, `towers`, `flats`, `households`.
- **Membership:** `memberships` (`user_id`, `household_id`, `category`, status, dates, `sponsor_membership_id`, declared relationship and occupancy attributes).
- **Onboarding:** `membership_applications`, `invitations`, `application_reviews`.
- **Evidence:** `verification_documents`, `ocr_results`, plus `member_evidence_requests` for exceptional requests.

**Critical constraints:** a membership identifies a person in a specific household; households reference a flat; sponsor links reference a **specific membership**, not any person in that flat; no broad owner inference is permitted when a tenant household also exists. Existing relationships and legacy review records are retained on policy migration.

Other KNOWALL modules should consume the stable user/membership/flat IDs and effective permissions. They must not independently mint verified resident status, expose original documents or implement their own login system.

## 5. Project structure (key locations)

```text
KNOWALL/
├── backend/
│   ├── app/
│   │   ├── __init__.py                  # Flask create_app / blueprint registration
│   │   ├── config.py                    # env-driven configuration
│   │   ├── api_docs.py                  # /docs, /openapi.json
│   │   ├── openapi.json                 # canonical OpenAPI specification
│   │   └── modules/identity/
│   │       ├── models/                # SQLAlchemy tables and enums
│   │       ├── auth/                  # authentication/session
│   │       ├── residential/           # society, tower, flat, me
│   │       ├── onboarding/            # applications/invitations
│   │       ├── documents/             # private upload / Surya OCR
│   │       ├── admin/                 # reviewer and member APIs
│   │       ├── access/                # shared effective-permission policy
│   │       └── member_evidence/       # exceptional proof requests
│   ├── migrations/versions/          # committed Alembic revisions
│   ├── scripts/                      # demo seed, OCR test, Windows cleanup
│   ├── tests/                        # Pytest suites
│   ├── private_uploads/              # local private evidence: never commit
│   ├── requirements.txt
│   ├── requirements-phase4a.txt
│   ├── requirements-phase7.txt
│   └── .env                          # untracked secrets, not committed
├── frontend/                         # Next.js App Router frontend
└── docs/api-contracts/               # team-facing feature API contracts
```

Folder names shown above reflect the consolidated patches. Confirm actual paths in your integrated checkout; do **not** recreate or overwrite files blindly if your repository has diverged.

## 6. Local setup — Windows PowerShell

### 6.1 Prerequisites

- Git; a compatible Python installation; Node.js/npm suitable for the checked-in Next.js version.
- PostgreSQL server and a database administration client (`psql` or pgAdmin).
- For **live OCR**: Windows x64 llama.cpp build with `llama-server.exe`; internet for first-time model download.
- Optional for **real emails**: a dedicated Gmail account with 2-Step Verification and an App Password, or another SMTP provider. Not required for `console` mode.

> Reuse an **existing working `backend/.venv`** if you already have it. Python/version upgrades on a working installation should be performed in a separate environment first.

### 6.2 Create PostgreSQL database (first-time setup only)

In `psql` while logged in as an authorized PostgreSQL admin, run these as **separate statements** (choose a strong, local-only password):

```sql
CREATE ROLE knowall_user WITH LOGIN PASSWORD 'REPLACE_WITH_STRONG_PASSWORD';
CREATE DATABASE knowall_dev OWNER knowall_user;
```

If that role/database already exists, **do not recreate or delete it**. Set credentials in `backend/.env` to match your actual PostgreSQL installation. URL-encode special characters in the password within a connection URL.

### 6.3 Python dependencies

From PowerShell at the repository root:

```powershell
cd backend
py -m venv .venv                       # first install only
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-phase4a.txt
```

**Surya 2 dependency compatibility:** do not install the **unmodified older** `requirements-phase7.txt` if it still says `Pillow>=11,<13`. That requirement conflicts with Surya 0.22.1, which requires `Pillow>=10.2,<11`. **Correct that file** to use `Pillow>=10.2,<11`, or install the compatible packages directly:

```powershell
python -m pip install "pymupdf>=1.25,<2" "Pillow>=10.2,<11" "surya-ocr==0.22.1"
python -m pip check
```

The other feature patches do not require a new Python package. For a team installation, keep one reviewed and pinned dependency lock/requirements set instead of independently guessing latest versions.

### 6.4 Configure `backend/.env`

Create `.env` from `.env.example` if absent, then adjust the values below. **Use placeholders in shared documentation; secrets belong only on each developer's machine.**

```dotenv
# PostgreSQL / Flask
DATABASE_URL=postgresql+psycopg://knowall_user:REPLACE_DB_PASSWORD@localhost:5432/knowall_dev
SECRET_KEY=REPLACE_WITH_LONG_RANDOM_FLASK_SECRET
COOKIE_SECURE=false

# Fictional local-only seeded users; must differ from one another
KNOWALL_SEED_ADMIN_PASSWORD=REPLACE_WITH_AT_LEAST_12_CHAR_ADMIN_PASSWORD
KNOWALL_SEED_RESIDENT_PASSWORD=REPLACE_WITH_AT_LEAST_12_CHAR_RESIDENT_PASSWORD

# Website / verification & recovery
FRONTEND_BASE_URL=http://localhost:3000
MAIL_DELIVERY_MODE=console
MAIL_FROM=noreply@knowall.local

# Set these when switching MAIL_DELIVERY_MODE=smtp:
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=YOUR_GMAIL_ADDRESS
SMTP_PASSWORD=YOUR_GOOGLE_APP_PASSWORD

# Private OCR evidence (absolute path recommended)
OCR_PRIVATE_DIR=C:/path/to/KNOWALL/backend/private_uploads
SURYA_INFERENCE_BACKEND=llamacpp
SURYA_INFERENCE_KEEP_ALIVE=1
SURYA_INFERENCE_PARALLEL=1
LLAMA_CPP_BINARY=C:/tools/llama.cpp/llama-server.exe
```

For local HTTP use `COOKIE_SECURE=false`; behind real HTTPS it must be `true`. Do not commit `.env`, private uploads, PostgreSQL dumps, raw verification tokens or Gmail App Passwords. Ensure `.gitignore` protects those paths.

### 6.5 Apply committed database migrations

From `backend/`:

```powershell
python -m flask --app app:create_app db current
python -m flask --app app:create_app db upgrade
python -m flask --app app:create_app db current
```

**Expected latest revision for the consolidated family-policy patch:** `7cfa926bd410` (following `5b1f8d7ac921`). If your local checkout is behind, merge the missing migrations **in revision order** before upgrading. Do **not** run `flask db init`, regenerate old revisions, reset the database, run `db.create_all()` or wipe pending family applications. Back up any populated PostgreSQL database before an upgrade.

### 6.6 Seed fictional demo users (only after migrations)

```powershell
python -m scripts.seed_green_valley
```

The seed is designed to be repeat-safe, creates **4 towers / 240 flats**, and does not reset existing demo passwords on rerun. It creates verified **fictional** `.test` identities for convenient demos—these are *not real email-verified accounts*.

| Email | Demo role / residence | Password source |
|---|---|---|
| `admin@greenvalley.test` | Society administrator | `KNOWALL_SEED_ADMIN_PASSWORD` |
| `rahul@greenvalley.test` | Owner, B-402 | `KNOWALL_SEED_RESIDENT_PASSWORD` |
| `priya@greenvalley.test` | Rahul's sponsored family, B-402 | `KNOWALL_SEED_RESIDENT_PASSWORD` |
| `amit@greenvalley.test` | Tenant, B-402 (separate household) | `KNOWALL_SEED_RESIDENT_PASSWORD` |
| `sneha@greenvalley.test` | Amit's sponsored family, B-402 | `KNOWALL_SEED_RESIDENT_PASSWORD` |
| `maya@greenvalley.test` | Applicant with draft tenant application, C-301 | `KNOWALL_SEED_RESIDENT_PASSWORD` |

**Security:** The shared *demo* resident password is a seed convenience only. Real registration uses individually chosen passwords and separate hashes. Do not give real users these test credentials or expect `.test` addresses to receive SMTP emails.

### 6.7 Configure and smoke-test Surya OCR 2

1. Download the **Windows x64 llama.cpp** release and extract it outside Git, for example `C:\tools\llama.cpp`.
2. Confirm the actual location of `llama-server.exe` and its companion DLLs; update `LLAMA_CPP_BINARY` above. Surya uses the `llamacpp` backend without Docker.
3. Keep `SURYA_INFERENCE_KEEP_ALIVE=1`: Surya keeps its inference server alive between requests and avoids its problematic normal-exit cleanup callback observed on Windows.
4. From `backend/`, after installing the latest team OCR kit beside it, run:

```powershell
python scripts\ocr_smoke_test_surya2_keepalive.py ..\KNOWALL_Surya2_Updated_Team_Kit\ocr_samples\fictional_occupancy_letter.png
```

The model may download weights the first time. An HF Hub unauthenticated-rate warning is not necessarily an inference failure. The fictional PNG is testing material, not genuine residence proof.

When completely finished, **stop Flask first** and then stop the project-owned OCR server safely:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_surya_windows.ps1
```

The cleanup script checks process ownership before stopping it. If it does not recognize the process, investigate rather than terminating unrelated processes. A successful OCR extraction does not, by itself, prove clean Windows subprocess shutdown.

### 6.8 Configure real verification emails (optional for local demo)

`MAIL_DELIVERY_MODE=console` prints verification/recovery links in the Flask terminal. To deliver real email, configure `MAIL_DELIVERY_MODE=smtp`, set `MAIL_FROM` to your verified sender address and provide valid SMTP credentials. Gmail typically requires a Google **App Password** with 2-Step Verification; do not use the ordinary Gmail login password.

**Flow:** Register → verify via `/verify-email?token=...` on Next.js → frontend submits token to Flask → login. Password reset links open `/reset-password?token=...`. Verification links last **24 hours** and password-reset tokens **30 minutes** by the current backend configuration. Test delivery using a real inbox you control, not seeded `.test` emails.

### 6.9 Start the backend and frontend

**Terminal A — Flask:**

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m flask --app app:create_app run --debug --no-reload --port 5000
```

Use `--no-reload` so the development reloader does not spawn duplicate OCR inference servers.

**Terminal B — Next.js:**

```powershell
cd frontend
npm install
npm run dev
```

Ensure `frontend/next.config.*` includes a rewrite equivalent to:

```js
{ source: '/api/:path*', destination: 'http://127.0.0.1:5000/api/:path*' }
```

Test `http://localhost:3000` (browser) and `http://localhost:5000/docs` (Swagger). Open email invitation links on **port 3000** under `/invitations/accept?token=...`; the Flask email config must use `FRONTEND_BASE_URL=http://localhost:3000` locally.

## 7. API reference

**Authoritative specification:** `backend/app/openapi.json`, served as `GET /openapi.json`. The following summary is the endpoint inventory of the latest consolidated patch; request bodies/response fields should always be verified in the actual OpenAPI document.

### Authentication and account recovery

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/auth/csrf` | Initialize/refresh CSRF |
| POST | `/api/auth/register` | Create an unverified account |
| POST | `/api/auth/login` | Login, rotate CSRF |
| GET | `/api/auth/me` | Current session user |
| POST | `/api/auth/logout` | Logout |
| POST | `/api/auth/verification/resend` | Resend email verification |
| POST | `/api/auth/verify-email` | Verify one-time email token |
| POST | `/api/auth/password/forgot` | Request reset link |
| POST | `/api/auth/password/reset` | Reset password and invalidate prior sessions |

### Public residential reference and current user

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Process health check |
| GET | `/api/residential/society` | Single-society profile |
| GET | `/api/residential/towers` | Four towers |
| GET | `/api/residential/towers/{tower_id}/flats` | Flats, optional `?floor=4` |
| GET | `/api/residential/flats/{flat_id}` | Public flat details |
| GET / PATCH | `/api/me/profile` | Own profile and updates |
| GET | `/api/me/access` | Effective roles/permissions |
| GET | `/api/me/memberships` | Own memberships |
| GET | `/api/me/households` | Own eligible household info |
| GET | `/api/me/family-tree` | Sponsor links in own household |

### Applications, invitations and documents

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/membership/applications` | New Owner/Tenant draft |
| GET | `/api/membership/applications/me` | My applications |
| GET / PATCH | `/api/membership/applications/{application_id}` | View/edit own application |
| POST | `/api/membership/applications/{application_id}/submit` | Submit/resubmit |
| POST | `/api/invitations` | Issue eligible invitation |
| GET | `/api/invitations/me` | Invitations addressed to verified user |
| POST | `/api/invitations/accept` | Accept: draft for Owner/Tenant, direct membership for Family |
| POST | `/api/documents/upload` | Private application evidence |
| GET | `/api/documents/application/{application_id}` | Evidence for an application |
| GET | `/api/documents/{document_id}` | Private document metadata |
| GET | `/api/documents/{document_id}/file` | Authorized private download |
| POST / GET | `/api/documents/{document_id}/ocr` | Start / retrieve Surya extraction |

### Administrator review and directory

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/admin/applications` | Paged review queue |
| GET | `/api/admin/applications/{application_id}` | Detail, evidence, reviews, linked sponsor context where applicable |
| POST | `/api/admin/applications/{application_id}/decision` | Human decision for Owner/Tenant and historical family applications |
| GET | `/api/admin/memberships` | Membership directory |
| PATCH | `/api/admin/memberships/{membership_id}/status` | Suspend/reinstate/revoke |
| PATCH | `/api/admin/memberships/{membership_id}/occupancy` | Admin-confirmed occupancy |
| PATCH | `/api/admin/memberships/{membership_id}/relationship` | Correct declared relationship with audit |
| GET | `/api/admin/households` | Household-grouped member directory |
| GET | `/api/admin/audit-logs` | Authorized audit events |

### Exceptional member evidence

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/admin/memberships/{membership_id}/evidence-requests` | Ask member for specific evidence |
| GET | `/api/admin/evidence-requests` | Admin evidence queue |
| GET | `/api/me/evidence-requests` | Own evidence requests |
| POST | `/api/me/evidence-requests/{entry_id}/upload` | Private member upload |
| GET | `/api/member-evidence/{entry_id}/file` | Owner/authorized-admin private file access |
| POST | `/api/admin/evidence-requests/{entry_id}/resolve` | Accept/reject/cancel request |

**Not implemented / not promised in this Module 1 contract:** sent-invitation history (`GET /api/invitations/sent`), token-free invitation acceptance, formal polling/voting endpoints, or other Modules 2–6 APIs. Do not call unimplemented routes from the frontend.

## 8. Test, verify and demo

### Automated backend tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pip check
python -m pytest -q
```

Useful focused suites, where present in the merged checkout:

```powershell
python -m pytest tests/test_residential_api.py -q
python -m pytest tests/test_onboarding_api.py -q
python -m pytest tests/test_document_api.py -q
python -m pytest tests/test_admin_api.py -q
python -m pytest tests/test_access_policy.py -q
python -m pytest tests/test_family_profile_enhancement.py -q
python -m pytest tests/test_admin_family_sponsor_context.py -q
python -m pytest tests/test_family_auto_activation.py -q
```

Earlier phases were confirmed passing in the user's local environment, but **do not invent a final test count** for the new family-auto-activation/evidence patch. Record the actual output of the **latest** full regression run. The unit suite uses mock OCR for speed; a separate **live Surya** test and PostgreSQL concurrency test are required to demonstrate those paths.

### Swagger authenticated verification

1. Open `http://localhost:5000/docs`.
2. Run `GET /api/auth/csrf`, copy `csrf_token` into **Authorize → CsrfHeader**.
3. Login through `POST /api/auth/login`; the browser saves its HTTP-only Flask cookie.
4. **Replace the Swagger CSRF token** after login because authentication rotates it.
5. Test own `/api/me/*`, Owner/Tenant application, document upload/OCR, admin approval and subsequent permissions.
6. For family, invite from an eligible Owner/Tenant; open the email with matching verified recipient; accept and confirm `FAMILY_MEMBERSHIP_ACTIVATED` **without** an application.
7. Check admin household directory, exceptional evidence request, sponsor suspension and recovery, and unauthorized access from a different account.

### Essential real end-to-end acceptance checks

- [ ] Register with a **real mailbox** → receive SMTP verification → verify → login.
- [ ] Owner self-application → private upload → OCR → admin review → active membership.
- [ ] Tenant invitation → draft → tenant dates/documents → admin approval.
- [ ] Family invitation → email/token validation → **immediate ACTIVE membership** → resident dashboard and household view.
- [ ] Different verified email cannot accept an invitation intended for someone else; expired/reused tokens fail.
- [ ] Suspend/revoke/expire sponsor → dependent family **effective access** becomes ineligible.
- [ ] Admin-only household directory shows Owner and Tenant households separately on a shared flat.
- [ ] Exceptional evidence request → notification → private upload → resolution; no automatic suspension.
- [ ] Privacy: another resident cannot access documents, sponsor context or administrator endpoints.
- [ ] Legacy pending family applications remain unchanged after migrations.
- [ ] PostgreSQL concurrent family accepts and sponsor revocation produce safe, consistent results.
- [ ] Frontend typecheck, lint, component tests, production build, and full live E2E flow pass.

## 9. Security and operational notes

- **Sessions and CSRF:** browser uses Flask HTTP-only cookies and `X-CSRF-Token` on mutations; no JWT/NextAuth/Nodemailer or second auth source. Avoid using different browser hostnames for one session.
- **Email and tokens:** verification and invitation links are secret, single-use and expiring. Never log/store them in frontend analytics or localStorage. Seed `.test` identities are for development only.
- **File privacy:** PDFs/JPGs/PNGs are validated, stored outside public folders and retrieved via authenticated Flask endpoints. Owner/Tenant evidence is limited to **5 MiB per document**. OCR results are advisory, not identity or legal proof.
- **Family and role access:** declared family relationship is not formally verified. Role assignments alone never override sponsor, membership-date or account-status eligibility.
- **Exceptional evidence:** one open request per membership; a request does not itself revoke access. A restricted, audited CLI purges eligible stored attachments **90 days after resolution** (subject to applicable retention policy):

  ```powershell
  python -m flask --app app:create_app purge-expired-member-evidence
  ```

- **Migrations:** never manually insert verified memberships/roles just to satisfy frontend screens. Do not drop/reseed populated databases or auto-approve legacy applications.
- **Voting:** this module provides membership/ownership/occupancy facts, but **Module 2** implements voter designation, per-flat policies and ballot uniqueness.

## 10. Common issues

| Symptom | First check |
|---|---|
| `pip check` reports Surya/Pillow mismatch | Replace old Pillow `>=11` requirement with `>=10.2,<11` and reinstall compatible release |
| `psycopg` connection failure | PostgreSQL server running, user/database created, `DATABASE_URL` accurate |
| `flask db upgrade` reports missing revision | Patch/migration files merged in order; check `db current`, `db heads`; do not reset DB |
| No verification email | `MAIL_DELIVERY_MODE`; SMTP credentials/App Password; spam folder; Flask logs; real recipient mailbox |
| Invitation email opens 404 | Ensure Next.js `/invitations/accept` page exists and `FRONTEND_BASE_URL` points to port **3000** |
| `401` / CSRF error | Signed-in cookie present; obtain/refresh CSRF after login and attach to POST/PATCH |
| Owner invitation shows sponsor relationship field | Frontend must render relationship input **only** for `FAMILY_MEMBER` |
| Family member sent to admin-review flow | Branch on `outcome=FAMILY_MEMBERSHIP_ACTIVATED`, not older application assumptions |
| OCR is slow or interrupted | CPU Surya can take minutes; inspect persisted result rather than blindly retrying mutation |
| Surya prints `KeyboardInterrupt` while exiting | Use keep-alive and validated `stop_surya_windows.ps1`, no Flask auto-reloader |
| Family member appears ACTIVE but cannot use resident feature | Inspect **effective** sponsor/account/membership eligibility, not stored status only |
| Swagger UI unavailable offline | Swagger assets use CDN; REST API and `/openapi.json` still work locally |

## 11. Cross-module handoff

Modules 2–6 should consume: user ID, household ID, membership ID, flat/tower context, account status and **current effective permissions**. Use the shared Flask `requires_permission(...)` policy for protected routes. Do not duplicate membership approval, change resident status behind Module 1's back, infer sponsor from flat owner, or query private identity documents unless a specifically authorized interface is established.

For Next.js, the source of truth is the checked-in **`backend/app/openapi.json`** and the contracts in `docs/api-contracts/`, particularly:

- `residential-phase5.md` — residential and current-user API baseline.
- `documents-phase7.md` — evidence upload and Surya OCR.
- `permissions-phase9.md` and `frontend-integration-handoff.md` — shared authorization.
- `module1-family-profile-occupancy.md` — family relationships, profile and occupancy.
- `sponsor-context-admin.md` — historical family reviewer context.
- `family-auto-activation-and-evidence.md` — **finalized family policy** and exception workflow.

Some filenames may be absent if patches were not yet merged. Use the newest **actual backend OpenAPI**; never overwrite it with an older frontend copy.

---

**Maintainer note:** This is the **completed Module 1 functional scope**, not a claim that every deployment-specific check has passed. Each teammate must record local migration revision, backend test results, live OCR/SMTP checks and browser end-to-end results before marking their installation fully verified.
