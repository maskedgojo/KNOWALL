# KNOWALL — Phase 9 shared authorization contract

**Application:** single-society Green Valley Residency, Flask modular monolith. **Data model:** existing SQLAlchemy tables. **Migration:** none.

## Source of truth

For a signed-in account, use `GET /api/me/access`. The previous response keys remain unchanged; the API now also returns an alphabetically sorted `permissions` array. Example shape:

```json
{
  "user_id": "00000000-0000-4000-8000-000000000001",
  "email_verified": true,
  "roles": ["RESIDENT"],
  "verified_resident": true,
  "active_memberships": [{ "id": "...", "household_id": "...", "flat": {"tower_name":"B", "flat_number":"402"}, "category":"OWNER", "status":"ACTIVE", "access_state":"ACTIVE" }],
  "permissions": ["identity.profile.read", "identity.households.read", "society.notices.read"]
}
```

This response is illustrative, abbreviated and **not a copy of an actual response**; real responses may contain more permission codes and membership fields. Frontend must use the backend response dynamically, not these sample values.

## How authorization works

- A signed-in, currently active account can manage its own profile, applications and private documents as permitted by their respective endpoints.
- A verified account may submit applications and accept invitations; these endpoints still validate their own conditions.
- RESIDENT/COMMITTEE/SOCIETY_ADMIN/PLATFORM_ADMIN role **alone** does not grant resident society capabilities. A verified, active, in-date, eligible membership is required, including a valid family sponsor when applicable.
- SOCIETY_ADMIN or PLATFORM_ADMIN role with verified email grants administrative identity actions without a resident membership. User suspension disables all logged-in access.
- Future Modules 2–6 can use the permission guard **and** enforce their own domain eligibility (vote eligibility, resource ownership, booking limits, department assignment, etc.). Identity permissions do not implement those modules.
- For single-society V1, no multi-society scope or switching is implemented.
- Revoking a role, suspending/expiring a membership, or invalidating a sponsor changes the *next request's* effective permissions. Do not cache `/api/me/access` indefinitely on the frontend.

## Backend developer usage

```python
from flask import Blueprint, jsonify
from app.modules.identity.access import requires_permission, has_permission

bp = Blueprint("example_module", __name__)

@bp.get("/api/example/announcements")
@requires_permission("society.notices.read")
def announcements():
    # In a real Module 2 route: also enforce the module's own visibility rules.
    return jsonify({"announcements": []})
```

Do **not** add this sample endpoint to the KNOWALL backend; it only demonstrates decorator usage. An unknown permission raises `ValueError` when the route is registered, preventing silent permissive access.

### Existing permissions

**Account:** `identity.profile.read`, `identity.profile.update`, `identity.applications.manage_own`, `identity.documents.manage_own`, `identity.invitations.view_own`

**Verified account:** `identity.applications.submit`, `identity.invitations.accept`

**Eligible verified resident:** `identity.households.read`, `identity.invitations.create`, `society.notices.read`, `society.maintenance.create`, `society.facilities.book`, `locality.listings.suggest`, `civic.issues.create`, `civic.issues.support`

**Verified society/platform admin:** `identity.admin.manage`, `identity.admin.applications.read`, `identity.admin.applications.decide`, `identity.admin.memberships.manage`, `identity.admin.audit.read`, `identity.admin.documents.review`, `identity.invitations.create`

**Important:** Codes for society/locality/civic Modules 2–6 are capability contracts for future modules, not implemented endpoints. The owner module must still implement its routes and security policies. Formal voting rights are **not** granted globally; Module 2 determines per-ballot eligibility from membership information and its configured rules.

## API error model

- Anonymous protected request: `401` / `AUTH_REQUIRED`
- Logged-in account lacks a permission: `403` / `FORBIDDEN`
- Invalid resource / unauthorized object: endpoint-specific `403` or privacy-preserving `404`
- Mutations need `X-CSRF-Token` on all `POST`, `PATCH`, `PUT`, `DELETE` requests.

Security decisions always happen in Flask. Client permission checks should only hide/show navigation and prevent unnecessary actions; malicious callers must still fail at the server.
