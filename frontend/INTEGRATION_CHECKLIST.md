# KNOWALL — local integration and release checklist

## Backend must be ready before frontend testing

- [ ] Updated family/profile/occupancy/relationship migration applied; `flask db current` reports expected head.
- [ ] `python -m pytest -q` passes, including enhancement auth/access, memberships, family-tree and privacy tests.
- [ ] Flask serves all listed routes under `/api` with current `backend/app/openapi.json`.
- [ ] SMTP test sends a real verification email to a controlled inbox. Links must point to frontend `/verify-email?token=...` and `/reset-password?token=...` on `localhost:3000` in development.
- [ ] Session cookies set and rotate correctly through Next rewrite. Check cookie `Path`, `SameSite`, `Secure` behavior for HTTP development and HTTPS deployment.
- [ ] Flask private evidence responses prevent caching and require session authorization. PDF/JPG/PNG headers and content disposition permit secure preview/download.

## Browser smoke paths

- [ ] `/login`: wrong password, unverified email, verified admin, verified resident; login redirects correctly. Confirm CSRF rotates.
- [ ] `/register`: creates unverified applicant; check inbox screen displayed; no membership granted.
- [ ] `/check-inbox` and `/verify-email?token=...`: real inbox, valid token, expired (24h), reused, wrong token, resend rate limit (429).
- [ ] `/forgot-password` and `/reset-password?token=...`: 30-minute expiry, reused token, old sessions revoked, login after reset.
- [ ] `/onboarding/new`: fetch live towers/flats; owner/tenant draft; optional date range; nullable occupancy.
- [ ] `/onboarding/{id}`: draft edit, evidence upload with valid document enum, PDF <=3 pages and <=5 MB, invalid formats, CSRF rejection, original private download, OCR success/warnings/503, submit for review.
- [ ] `/invitations?token=...`: email-bound family acceptance, sponsor relationship, null/yes/no occupancy, expired (7-day), reused token, wrong verified email; submit accepted draft separately.
- [ ] Admin `/admin/applications`: paginated statuses, detail privacy, inspect all original files, OCR warnings, correct decision values, reason, acknowledgment and duplicate decision protection.
- [ ] `/admin/memberships`: suspend, revoke, reinstate (only allowed backend transitions), confirm occupancy, edit family relationship WITHOUT modifying sponsor link.
- [ ] `/household`: eligible resident only, only own household, explicit sponsor graph, separate owner/tenant households in same flat; null occupancy shows Unknown.
- [ ] `/profile`: private DOB and occupation not exposed in household page, allowed updates persisted.
- [ ] `/admin/audit`: server audit entries only; no private text/PII leaks to other users.
- [ ] Suspended/expired user: access state refresh and no unauthorized resident actions. Unauthorized admin attempt returns 403; unauthorized private evidence returns 404/403 per backend.
- [ ] Session expiry (401), `403 CSRF_REQUIRED`, `409` conflict, `413`, `415`, `429`, `503`, network interruption. No auto replay of mutations.
- [ ] Mobile (375px), tablet (768px) and desktop (1440px): keyboard navigation, focus ring, form validation, responsive tables, modal/decision confirmation, reduced-motion preference.

## Integration contract notes

1. The supplied OpenAPI v0.9.1 describes authenticated document and administrator API responses without detailed JSON `schema` in many places. `src/features/admin/helpers.ts` and `src/features/documents/documents.tsx` use defensive read-only adapters. Validate real JSON payloads before claiming the full review and OCR views are complete; expand `openapi.json` response schemas once confirmed by backend.
2. Admin queue metrics use only backend-reported `pagination.total`; no fake statistics are displayed if absent.
3. `/api/me/family-tree` has a precise schema and is used to render **direct** sponsor relationships. No inferred genealogical links.
4. Document upload `document_type` is exactly one of `RENTAL_AGREEMENT`, `OCCUPANCY_LETTER`, `OTHER_RESIDENCE_EVIDENCE` per supplied OpenAPI; do not add other values without backend contract changes.
5. Family members must accept invitation before drafting; they should not be forced to upload evidence unless the backend requires it.
6. Browser origin stays `http://localhost:3000`; backend is reached only by server rewrite to 127.0.0.1:5000.
7. Browser/E2E and component tests are an outstanding release gate; the included Node tests check API-client behavior, not full workflows.
