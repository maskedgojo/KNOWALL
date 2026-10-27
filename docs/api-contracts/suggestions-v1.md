# Resident suggestions

Eligible residents with `society.notices.read` can list and submit society-wide
suggestions. Each suggestion stores a title, description, category, author,
society id, timestamps, and status. The server sets status to `SUBMITTED`.
Clients cannot send `society_id`, author, or status.

Categories are `MAINTENANCE`, `SAFETY`, `AMENITIES`, `COMMUNITY`, and `OTHER`.
Title length is 3–160 characters. Description length is 1–8000 characters.

There is no update or decision route. `society.suggestions.decide` is not
registered, so committee triage, approval, and proposal links are not
implemented. `SUGGESTION_CREATED` is written to `audit_logs` with title,
category, and status. The description is omitted.

Migration `f1c7a4e82b30` revises `e4b8c2d71a05` and creates `suggestions` only.
It has not been applied by this change.
