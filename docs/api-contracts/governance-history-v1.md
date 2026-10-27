# Governance history

Eligible residents with `society.notices.read` can read
`GET /api/governance/history`. The route reads the existing `audit_logs` table.
It does not add a table or a permission.

A row is included only when its record belongs to society profile id `1` and
the event is already appropriate for residents:

- `NOTICE_PUBLISHED` for a notice in this society
- `NOTICE_ARCHIVED` only when that notice was published
- `DISCUSSION_CREATED` and `COMMENT_CREATED`
- `SUGGESTION_CREATED`

Draft notice edits, identity events, and rows whose record is not in this
society are omitted. The response contains `id`, `occurred_at`, `event_type`,
`summary`, and `resource_path`. It does not contain raw `details`, actor ids,
emails, tokens, notice or comment text, or suggestion descriptions.

`resource_path` is set only when the resident can still open that record.
Results use the same limit and offset bounds as other Module 2 lists, ordered
by newest event first. No migration is required.
