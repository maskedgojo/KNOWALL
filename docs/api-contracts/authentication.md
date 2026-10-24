# KNOWALL Module 1 — Authentication Contract (Phase 4A)

**API base path:** `/api/auth` (through the Next.js `/api/:path*` rewrite to Flask). **All browser requests use the same Next.js origin**, e.g. `http://localhost:3000/api/auth/...`. No separate CORS configuration is needed for this flow. `Content-Type: application/json` is required for JSON writes. Session authentication is by an HTTP-only cookie, **not JWT or localStorage**.

## CSRF requirements

1. Browser calls `GET /api/auth/csrf` on initial load (no login required).
2. The JSON body is `{"csrf_token":"<opaque random string>"}`. The browser also receives a signed HTTP-only session cookie.
3. The client sends `X-CSRF-Token: <value>` on **all modifying `/api/*` requests** (`POST`, `PUT`, `PATCH`, `DELETE`), including register and login.
4. Successful login **rotates the CSRF token**. Use the `csrf_token` returned by login for further mutations (or refetch `/csrf`). Successful logout also returns a new guest token.
5. When CSRF fails, backend returns `403` / `CSRF_REQUIRED`. To recover after refresh, call `/csrf` again.

`fetch` defaults to `credentials: "same-origin"`, but adding `credentials: "include"` for same-origin calls is fine. **Use `/api/...`, not direct browser calls to `127.0.0.1:5000`**. Avoid mixing `localhost` and `127.0.0.1` as browser origins.

## Endpoints

### GET `/api/auth/csrf` — 200 (public)

```json
{"csrf_token":"opaque-token"}
```

### POST `/api/auth/register` — 201 (public; CSRF header required)

```json
{
  "display_name": "Aarav Sharma",
  "email": "aarav@example.test",
  "password": "ExamplePassphrase!2026",
  "phone": "+919876543210"
}
```

`phone` is optional. Name: 2–120 characters. Password: 12–128 characters. Email is stored normalized to lowercase; duplicates rejected. The user receives the `APPLICANT` role only. No verified membership is created.

```json
{
  "message": "Account created. Email verification will be required before resident onboarding.",
  "user": {
    "id": "uuid-string",
    "display_name": "Aarav Sharma",
    "email": "aarav@example.test",
    "phone": "+919876543210",
    "email_verified": false,
    "account_status": "ACTIVE"
  }
}
```

Registration does **not** sign in automatically; call login explicitly. Phase 4B will add email verification. Until then, newly registered accounts correctly report `email_verified: false` and must not receive verified-resident privileges.

Errors: `400 VALIDATION_ERROR` (`fields` object), `409 EMAIL_ALREADY_REGISTERED`, `415 UNSUPPORTED_MEDIA_TYPE`, `403 CSRF_REQUIRED`.

### POST `/api/auth/login` — 200 (public; CSRF header required)

Request:

```json
{"email":"aarav@example.test","password":"ExamplePassphrase!2026"}
```

Response:

```json
{
  "user": {
    "id": "uuid-string",
    "display_name": "Aarav Sharma",
    "email": "aarav@example.test",
    "phone": "+919876543210",
    "email_verified": false,
    "account_status": "ACTIVE"
  },
  "csrf_token":"new-opaque-token"
}
```

Errors: `401 INVALID_CREDENTIALS` (same generic message for unknown user, incorrect password, suspended or disabled account); `400 VALIDATION_ERROR`; `403 CSRF_REQUIRED`.

### GET `/api/auth/me` — 200 (signed-in user)

```json
{"user":{"id":"uuid-string","display_name":"Aarav Sharma","email":"aarav@example.test","phone":null,"email_verified":false,"account_status":"ACTIVE"}}
```

Signed-out, suspended, or disabled accounts get `401 AUTH_REQUIRED`.

### POST `/api/auth/logout` — 200 (signed-in user; CSRF header required)

```json
{"message":"Logged out.","csrf_token":"new-guest-token"}
```

Errors: `401 AUTH_REQUIRED`, `403 CSRF_REQUIRED`.

## Common error response

```json
{"error":{"code":"VALIDATION_ERROR","message":"Check the submitted fields.","fields":{"email":"Enter a valid email address."}}}
```

The API does **not** return password hashes, raw tokens other than the CSRF token needed by the browser, memberships or inferred resident privileges. Later phases will provide `GET /api/me/access` for actual permissions.

## Example minimal browser client

```typescript
let csrfToken: string | null = null;

export async function initializeAuth() {
  const res = await fetch('/api/auth/csrf', { cache: 'no-store' });
  if (!res.ok) throw new Error('Unable to initialize session');
  csrfToken = (await res.json()).csrf_token as string;
}

export async function login(email: string, password: string) {
  if (!csrfToken) await initializeAuth();
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken! },
    body: JSON.stringify({ email, password }),
    credentials: 'same-origin',
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body.error?.message ?? 'Login failed');
  csrfToken = body.csrf_token; // rotated on login
  return body.user;
}
```

This illustrates the protocol only. The frontend chat should implement proper typed services and error handling; it should not use a singleton module token as a final app-wide state architecture without considering tab lifecycle, SSR and refresh.

## Important boundaries

- Password recovery / verification tokens: **Phase 4B**, not available yet.
- Invitation acceptance, onboarding, membership, OCR, and RBAC: later phases.
- No token in `localStorage`; the session cookie is HTTP-only.
- Cookie `Secure` must be `true` on HTTPS deployment. V1 local HTTP uses `false`.
- CSRF protects cookie-authenticated browser writes; rate-limiting / brute-force defense must be added and verified before any public deployment. The V1 module should not be exposed to the public internet yet.
- Flasks's default signed-cookie sessions cannot revoke every previously issued cookie globally on password reset. Phase 4B and final hardening must address invalidation strategy if public deployment is planned.
