# KNOWALL Phase 7 — Private document & Surya OCR API contract

**Backend:** Flask, cookie-based login + `X-CSRF-Token` for POST, no new migration.

**Swagger:** `/docs` serves the updated `app/openapi.json`. **Security:** every document endpoint requires a signed-in account; private evidence is accessible only to its applicant and an authorized society/platform administrator. Approved/rejected applications cannot be reprocessed; OCR never approves an application.

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/documents/upload` | Multipart file upload for the caller's own application, returns metadata and document ID |
| GET | `/api/documents/application/{application_id}` | List document metadata for an application |
| GET | `/api/documents/{document_id}` | Private metadata for authorized users |
| GET | `/api/documents/{document_id}/file` | Download original file as an attachment; no-store |
| POST | `/api/documents/{document_id}/ocr` | On-demand Surya extraction, candidate fields, comparison/warnings; CPU call may take time |
| GET | `/api/documents/{document_id}/ocr` | OCR run history |

## Upload request

`multipart/form-data` with fields:

- `application_id`: UUID from Phase 6
- `document_type`: `OCCUPANCY_LETTER`, `RENTAL_AGREEMENT`, or `OTHER_RESIDENCE_EVIDENCE`
- `file`: actual PDF/JPG/PNG file, max **5 MB**, PDF at most **3 pages**, unencrypted

CSRF: `GET /api/auth/csrf` first. Add response's `csrf_token` to the `X-CSRF-Token` header. After login, fetch CSRF again because login rotates it.

Example response to upload (`201`):

```json
{
  "document": {
    "id": "...uuid...",
    "application_id": "...uuid...",
    "document_type": "OCCUPANCY_LETTER",
    "filename": "fictional_occupancy_letter.png",
    "mime_type": "image/png",
    "size_bytes": 31112,
    "uploaded_at": "2026-10-22T12:00:00+00:00",
    "download_url": "/api/documents/...uuid.../file"
  }
}
```

Response to OCR (`200`) contains an `ocr` object with `status`, `extracted_text`, `extracted_fields`, `comparison_results`, `warnings`, timestamps, and `reused` (boolean).

`comparison_results` looks like:

```json
{
  "tower": {"entered":"B", "extracted":"D", "status":"MISMATCH"},
  "flat_number": {"entered":"402", "extracted":"402", "status":"MATCH"}
}
```

OCR is evidence assistance, **not authenticity verification**. An administrator must review the original document and any warnings before approval in Phase 8.

## Important error outcomes

- `400 INVALID_DOCUMENT`: unsupported, corrupted, oversize, encrypted, or oversized PDF page count
- `401 AUTH_REQUIRED`: no authenticated cookie
- `403 EMAIL_VERIFICATION_REQUIRED` or `CSRF_REQUIRED`
- `404 DOCUMENT_NOT_FOUND`: private document missing or inaccessible
- `409 INVALID_APPLICATION_STATE`: application cannot receive evidence or OCR
- `409 OCR_IN_PROGRESS`: extraction already in progress
- `503 OCR_UNAVAILABLE`: model error. Original upload is still available for manual review.

## Lifecycle constraint

The Flask demo should run as a **single process** (`--no-reload`), so the Surya model loads only once in that process. PostgreSQL row locking reduces duplicate OCR claims in competing requests; this is not a distributed job system or a production queue.

After Flask exits, Surya's supported `SURYA_INFERENCE_KEEP_ALIVE=1` setting leaves llama-server alive. Run `backend/scripts/stop_surya_windows.ps1` to stop only the process recorded in Surya's sentinel file. The PowerShell script refuses to stop an unrelated PID.
