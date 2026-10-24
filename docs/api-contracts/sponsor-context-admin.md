# Admin Application Detail — Explicit Family Sponsor Context

`GET /api/admin/applications/{application_id}` — **existing administrator-only endpoint**.

For `application.category == "FAMILY_MEMBER"`, the response adds the root-level key `sponsor_context`:

```json
{
  "application": { "...": "all existing fields unchanged" },
  "sponsor_context": {
    "membership_id": "UUID",
    "display_name": "Rahul Sharma",
    "category": "OWNER",
    "membership_status": "ACTIVE",
    "household_id": "UUID",
    "household_label": "Owner household",
    "flat_id": "UUID",
    "eligible_to_sponsor": true,
    "valid_from": "2026-01-01",
    "valid_until": null
  }
}
```

- For missing sponsor linkage: `"sponsor_context": null`.
- For an existing but expired/suspended/mismatched sponsor: show the **same explicitly linked sponsor** with `eligible_to_sponsor: false`; never select a different owner/tenant on the flat.
- For non-family categories, the original response is unchanged; `sponsor_context` is absent.
- `eligible_to_sponsor` requires active + email-verified account, currently eligible role assignment, OWNER/TENANT membership, current ACTIVE membership/date eligibility, and exact household and flat consistency.
- Don't infer occupancy from OWNER or use occupancy for sponsorship validation.
- No sponsor emails, phones, DOB, occupations, identity documents or unrelated residents are exposed in the sponsor context.

### OCR advisory

For family documents with OCR results, `application.documents[*].latest_ocr.sponsor_name_advisory` can be:

```json
{
  "status": "MATCHES_SPONSOR_NAME",
  "advisory_only": true,
  "basis": "linked_sponsor_display_name",
  "extracted_name": "Rahul Sharma"
}
```

The original `latest_ocr.comparisons.resident_name` **still compares against the applicant** and remains unchanged. An advisory name match does not verify the document or relationship, and does not auto-approve. `status` may also be `DOES_NOT_MATCH_SPONSOR_NAME` or `NAME_NOT_AVAILABLE`.

### Approval

`POST /api/admin/applications/{application_id}/decision` remains unchanged in request and response shape. On family approval Flask locks the referenced sponsor membership and performs **a fresh shared eligibility check** before creating the membership. `409 SPONSOR_INELIGIBLE` is returned if the sponsor no longer qualifies. Corrupt relationship codes return `409 INVALID_FAMILY_RELATIONSHIP`. Manual admin review remains mandatory; no action is triggered by OCR matching alone.

### Files and migration

No migration. Add `identity/access/sponsorship.py`, update admin and onboarding routes, update `app/openapi.json` and run new + full regression tests. See root `README_Sponsor_Context.md` for commands.
