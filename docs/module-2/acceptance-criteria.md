# KNOWALL Module 2 — Acceptance Criteria

## 1. Status and use

These criteria separate what can be accepted from the current repository and
what remains conditional. They do not approve a governance, privacy, role,
retention, or voting policy. Formal voting is not implemented.

## 2. Shared criteria for every implemented route

- Mutations use the Flask session and `X-CSRF-Token`.
- Identity, membership, and effective access come from Module 1.
- Flask enforces authorization. A hidden navigation link is not access control.
- Implemented behavior matches `backend/app/openapi.json`.
- Module 1 onboarding, resident approval, private evidence, and authentication
  stay unchanged.

## 3. Criteria the current implementation can meet

### 3.1 Official notices

Notice V1 follows [the notice contract](../api-contracts/notices-v1.md):

- A verified Society Admin with `society.notices.manage` can create a draft,
  edit that draft, publish it, archive it, and correct a published notice by
  creating a replacement draft.
- Published title, body, and expiry are immutable.
- The audience is the whole configured society. A resident with current
  `society.notices.read` can view a notice only while it is published,
  unarchived, and unexpired. Other resident reads return 404.
- Expiry hides the notice. It does not archive it.
- Audit entries for create, update, publish, archive, and replacement omit the
  notice body.

Notice categories, audience targeting, pinning, attachments, and read
acknowledgements are missing. They are not part of this acceptance bar.

### 3.2 Discussions and suggestions

- An eligible resident can create, list, and open a discussion in the
  configured society, and can add a comment or a reply whose parent belongs to
  that same discussion.
- An eligible resident can submit and open a suggestion with a title,
  description, and category. The server sets the author, society, and status
  `SUBMITTED`.
- Forged society, author, and status fields are rejected.

Discussion reporting is missing. Discussion moderation and committee
suggestion decisions are blocked until M2-POL-01 names the authority and the
Module 1 owner registers the permission. Linking a suggestion to a proposal is
missing.

### 3.3 Private disputes

- A resident can submit a dispute and can list or read only their own.
- Another resident, including one who guesses an id, receives 404.
- Dispute title and description do not appear in governance history or
  Community Activity.
- There is no handler, response, appeal, reopen, or evidence route. Those stay
  blocked by M2-POL-10 and M2-POL-11.

### 3.4 Informal polls and proposal records

- An informal poll is labeled non-binding in the API and the resident page.
- One signed-in eligible resident can respond once. A second response is
  rejected. The database unique constraint is `(poll_id, user_id)`.
- A response outside the open window is rejected. Counts are null until the
  poll closes. Voter identities are not returned.
- A resident can submit and read a proposal. `voting_open` is false. There is
  no ballot and no result.

Formal voting is not implemented. Per-resident and per-flat eligibility,
representative selection, eligibility snapshots, formal one-ballot rules,
deadlines, quorum, results, and recorded decisions stay blocked by M2-POL-04
through M2-POL-08. Informal anonymity and early results stay blocked by
M2-POL-09. The one-response behavior above is the current poll rule, not an
approved formal ballot rule.

### 3.5 Governance history and Community Activity

- `GET /api/governance/history` returns safe summaries for the configured
  society. It does not return raw audit details, actor ids, dispute events,
  comment bodies, suggestion descriptions, or individual poll responses.
- A history link is present only when the current resident can still open that
  record.
- A verified Society Admin can browse discussions, comments, suggestions,
  informal polls, and proposals at `/admin/community-activity`. The page is
  read-only. Closed polls show aggregate counts. Open polls do not show
  results. Resident ids and voter identities are not shown. Disputes are not
  shown.

Published minutes are missing. Contextual notifications are blocked by
M2-POL-13.

## 4. Conditional criteria

These apply only after the named decision is approved. They are not current
acceptance tests:

- Reports and moderation actions are visible only to actors named by the
  approved moderation policy.
- A suggestion can be triaged and, when approved, linked to a proposal without
  losing its history.
- An authorized dispute handler can access only the fields permitted by
  M2-POL-10. Appeals, reopening, and evidence follow M2-POL-10 and M2-POL-11.
- A formal ballot is accepted at most once per the approved entitlement.
- A closed proposal rejects edits and votes. Early results and ballot
  inspection follow M2-POL-07, M2-POL-08, and M2-POL-09.
- A completed proposal produces a result without exposing ballot data beyond
  the approved confidentiality rule.

## 5. Verification

Each implemented slice needs backend tests for success, validation, anonymous
access, and unauthorized access; an OpenAPI entry; frontend coverage where a
page exists; and one recorded manual privacy or authorization check. The
browser checklist in [the progress tracker](progress.md) is that manual check.
It has not been recorded as passed.

## 6. Related documents

- [Module overview](README.md)
- [Scope and business decisions](scope-and-business-decisions.md)
- [Progress tracker](progress.md)
- [Formal voting dependencies](formal-voting-dependencies.md)
