# KNOWALL Module 1 — Next.js frontend

A copy-ready, **Flask-integrated** Next.js 16 App Router frontend for the single-society KNOWALL deployment (Green Valley Residency). Visual language based on the supplied Google Stitch Civic Precision designs: dark navy, teal, airy white cards, status labels and a compact administrator workspace.

## 1. Merge into the existing project

1. Commit/back up your current `frontend/` folder.
2. Extract `KNOWALL_Module1_Frontend.zip` **at the KNOWALL project root**. It contains a `frontend/` folder. Merge the files, allowing replacement of the original starter `src/app/page.tsx`, `globals.css`, `layout.tsx`, and `package.json`.
3. **Do not delete or replace your Flask backend.** Your existing `next.config.ts` rewrite is retained unchanged.
4. Do not copy stale `.next/`, `node_modules/` or `.env*` folders from another machine. This ZIP intentionally excludes them.

Existing `frontend/package-lock.json` is included; the project introduces no additional NPM packages.

## 2. Start Flask (Windows PowerShell, Terminal 1)

```powershell
cd C:\Users\KIIT0001\Desktop\KNOWALL\backend
.\.venv\Scripts\Activate.ps1
python -m flask --app app:create_app db current
python -m pytest -q
python -m flask --app app:create_app run --debug --no-reload --port 5000
```

Check `http://localhost:5000/openapi.json` and `http://localhost:5000/api/health`. The database enhancement migration and relevant backend tests must pass locally first.

## 3. Start Next.js (Windows PowerShell, Terminal 2)

```powershell
cd C:\Users\KIIT0001\Desktop\KNOWALL\frontend
npm ci
npm run dev
```

Open **http://localhost:3000/login**. Browser API requests go to relative `/api/*`, rewritten server-side to `http://127.0.0.1:5000/api/*`. Do not browse port 5000 for frontend pages.

For validation run:

```powershell
npm run typecheck
npm run lint
npm test
npm run build
```

## 4. Route inventory

| Audience | Route | Behavior |
|---|---|---|
| Public | `/login` | Flask session login, rotated CSRF |
| Public | `/register` | Unverified applicant registration; in-page inbox confirmation |
| Public | `/check-inbox` | Resend verification email |
| Public | `/verify-email?token=...` | Consume verification token once, user-confirmed action |
| Public | `/forgot-password` | Backend SMTP password recovery request |
| Public | `/reset-password?token=...` | Reset password; server revokes previous sessions |
| Authenticated | `/dashboard` | Real memberships, applications, access state |
| Applicant | `/onboarding` | Applications list |
| Applicant | `/onboarding/new` | Tower/flat/category/dates/occupancy draft wizard |
| Applicant | `/onboarding/{id}` | Edit/resubmit, evidence upload, private file preview, OCR history |
| Authenticated | `/invitations?token=...` | Single-use invitation acceptance and invitation history |
| Resident | `/household` | Eligible direct sponsor relationships and family invitation form |
| Authenticated | `/profile` | Private name, phone, DOB, occupation |
| Admin | `/admin` | Queue-derived summary metrics |
| Admin | `/admin/applications` | Paged status-filtered review queue |
| Admin | `/admin/applications/{id}` | Private evidence and human review decisions |
| Admin | `/admin/memberships` | Status transitions, confirmed occupancy, relationship correction |
| Admin | `/admin/invite` | Owner/tenant invitation via backend email |
| Admin | `/admin/audit` | Backend audit trail |

Future civic modules are clearly marked planned; voting is NOT implemented.

## 5. Architecture and privacy

- `src/lib/api.ts`: same-origin typed Fetch, in-memory CSRF, no mutation retry, error normalization; `src/lib/endpoints.ts`: Flask endpoint wrappers.
- `src/components/auth-provider.tsx`: **view state only** from `/api/auth/me` and `/api/me/access`; Flask provides the actual session, CSRF and authorization.
- `src/features`: auth, documents, onboarding, resident and admin features.
- `src/components`: reusable visual primitives, responsive shell and icons. No added npm dependencies.
- HTML token query parameters are stripped from the address bar on first client render. Tokens, passwords, cookies and private document bytes are not stored in localStorage or logged.
- Private files are fetched with `credentials: same-origin`, displayed as short-lived object URLs, and revoked on unmount. Verify Flask's cache-control and CSP in production.
- Upload validation: supported `document_type` enum from supplied OpenAPI, PDF/JPG/PNG, <=5 MB, PDF <=3 pages (the backend checks page count).
- OCR runs synchronously on Flask and may be slow. The UI deliberately does not invent a percentage or claim verification.
- `null` occupancy is rendered as **Not verified / Unknown**. Owner/tenant category is not itself proof of occupancy or voting eligibility.
- Resident household graph displays only explicit sponsor links returned by `/api/me/family-tree`.
- Admin approval requires explicit original-file opening and a separate human review acknowledgment when evidence is required; Flask must still independently validate it.

## 6. Verified vs. unverified

Verified in the creation environment:
- TypeScript `tsc --noEmit`: **PASS**.
- ESLint source/test lint: **PASS**.
- 10 API client / OpenAPI assertions: **PASS**.

Not verified:
- Full production build: **BLOCKED BY ENVIRONMENT** (supplied node_modules contained Windows-only Next.js SWC; offline Linux container cannot download Linux SWC). Run `npm ci` and `npm run build` on your Windows machine.
- Live Flask HTTP integration: **NOT TESTED** (no running Flask backend or database supplied).
- Gmail SMTP inbox delivery: **NOT TESTED**; verify live email and links pointing at Next.js `localhost:3000`.
- OCR result layout and administrative response adapter edge cases: **NEED LIVE SCHEMA/PAYLOAD VERIFICATION**. The Phase 7/8 OpenAPI responses are described but often lack JSON response schemas; these screens render actual backend values and do not invent metrics, documents, warnings or decisions.
- Frontend component/E2E browser tests: **NOT YET IMPLEMENTED**. The included tests cover API protocol and uploaded OpenAPI contracts; a browser-test environment is still required.

See `INTEGRATION_CHECKLIST.md` for manual tests and remaining contract requirements. Do not call this release production-ready until they pass.
