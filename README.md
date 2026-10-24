# KNOWALL Phase 5 — Residential & Current-User APIs + Swagger

**Apply this to your existing working Phase 4B repository** (57 tests passing locally). It is an additive patch, except for `backend/app/__init__.py`, which is updated to register the new routes and docs. **No schema changes or migration required**.

## 1. Files

```text
backend/
  app/__init__.py                              UPDATE — preserve any custom changes
  app/api_docs.py                              NEW — /docs and /openapi.json
  app/openapi.json                             NEW — OpenAPI 3.0 specification
  app/modules/identity/residential/__init__.py NEW
  app/modules/identity/residential/routes.py   NEW
  tests/test_residential_api.py                NEW

docs/api-contracts/residential-phase5.md       NEW — frontend handoff
```

> The patch **does not** overwrite `recovery.py` (keep your SQLite datetime synchronization fix from Phase 4B), old models, old migrations, seed data, or any existing test files.

## 2. Install into KNOWALL on Windows

1. Back up / commit your last working Phase 4B state.
2. Extract the ZIP. Copy the `backend/` and `docs/` folders to the **KNOWALL project root**, merging directories.
3. If `backend/app/__init__.py` has other modifications, add only these lines rather than replacing the whole file:

   After the existing auth/recovery imports inside `create_app()`:

   ```python
   from .modules.identity.residential import residential_bp, profile_bp
   from .api_docs import api_docs_bp
   ```

   After `app.register_blueprint(recovery_bp)`:

   ```python
   app.register_blueprint(residential_bp)
   app.register_blueprint(profile_bp)
   app.register_blueprint(api_docs_bp)
   ```

4. Do **not** run `db init`, `db migrate` or `db upgrade` for Phase 5; there are no new tables.

## 3. Run Pytest

In PowerShell:

```powershell
cd C:\Users\KIIT0001\Desktop\KNOWALL\backend
.\.venv\Scripts\Activate.ps1
python -m pytest tests/test_residential_api.py -q
python -m pytest -q
```

The Phase 5 file has multiple negative and privacy tests, including parameterized invalid input cases. Your existing Phase 4B suite should remain green. **Treat actual local output as authoritative; this package has been checked for Python syntax but not executed against Flask here.**

## 4. Run Flask and Swagger

```powershell
python -m flask --app app:create_app run --debug --port 5000
```

Open:
- `http://localhost:5000/api/health` — existing health endpoint
- `http://localhost:5000/docs` — Swagger UI
- `http://localhost:5000/openapi.json` — raw OpenAPI schema
- `http://localhost:5000/api/residential/society` — public society info
- `http://localhost:5000/api/residential/towers` — public towers

Swagger UI CSS/JS are fetched from a **pinned CDN**; it needs internet access to display, but your Flask REST API and the `/openapi.json` file work locally without it. There are no new Python packages and no Docker dependency.

### Swagger: authenticated flow

1. From `http://localhost:5000/docs`, expand **GET /api/auth/csrf** → Try it out → Execute.
2. Copy `csrf_token`; click **Authorize** and paste it into the `CsrfHeader` field (do not paste it into `SessionCookie`).
3. Expand **POST /api/auth/login**, enter a fictional seeded account, e.g. `rahul@greenvalley.test` plus the password specified in your **local** `KNOWALL_SEED_RESIDENT_PASSWORD`, and Execute.
4. The browser stores Flask's HTTP-only cookie automatically. **Login rotates the CSRF token**. Copy the new `csrf_token` from the login response and update **Authorize → CsrfHeader**.
5. Try **GET /api/me/profile**, **GET /api/me/memberships**, **GET /api/me/households**, and **GET /api/me/access**.
6. Try **PATCH /api/me/profile** with `{"display_name":"Rahul Example"}`. Read the response and verify the change. Avoid changing important demo records without a backup.
7. To test tenant and family behavior, log out, refresh CSRF, and log back in as another seeded account.

For protected calls, Swagger relies on the **browser-provided** session cookie; the UI does not let you set an HTTP-only cookie manually. Stay on the Flask `localhost:5000` origin while testing.

## 5. New endpoint list

| Method | Route | Access |
|---|---|---|
| GET | `/api/residential/society` | Public |
| GET | `/api/residential/towers` | Public |
| GET | `/api/residential/towers/{tower_id}/flats?floor=4` | Public, no personal data |
| GET | `/api/residential/flats/{flat_id}` | Public, no personal data |
| GET | `/api/me/profile` | Signed in |
| PATCH | `/api/me/profile` | Signed in + CSRF |
| GET | `/api/me/memberships` | Signed in, own memberships only |
| GET | `/api/me/households` | Verified, eligible resident, own households only |
| GET | `/api/me/access` | Signed in; preliminary role/membership facts |

Membership access is computed using date validity and sponsor eligibility; database status remains unchanged. Full shared RBAC middleware and cross-module permission names come in Phase 9.

**Next:** Phase 6 onboarding applications and invitation APIs, then Phase 7 OCR, Phase 8 admin reviews, Phase 9 RBAC and Phase 10 end-to-end tests. Extend Swagger/OpenAPI for each phase rather than waiting until the end.
