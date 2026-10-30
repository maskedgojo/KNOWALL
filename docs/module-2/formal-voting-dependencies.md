# Formal voting dependencies

Proposal records can be submitted and read. They do not accept ballots, and
the API sets `voting_open` to false. There is no ballot table and no
`/api/votes` or `/api/proposals/{id}/votes` route. Governance history says
formal voting is not open and does not include a tally. Informal polls are a
separate feature: each response is labeled non-binding, counts stay hidden
until the poll closes, and voter identities are not returned.

Formal voting stays blocked until these decisions are written down:

- Per-resident or per-flat eligibility, including who represents a flat when
  an owner and a tenant both occupy it (M2-POL-04, M2-POL-05).
- When the eligible-voter snapshot is taken, and what happens if a membership
  is suspended, revoked, or expires after a vote opens (M2-POL-06).
- Whether a ballot is attributable or secret, and who may inspect ballot-level
  rows (M2-POL-07).
- Quorum, majority, tie, abstention, amendment, cancellation, and recount
  rules (M2-POL-08).
- Whether a closed proposal can be reopened, and who may cancel it (M2-POL-01,
  M2-POL-08).
- Which proposal and ballot facts may appear in resident governance history
  (M2-POL-12).

Do not infer any of these from a role, household, flat, or occupancy value.
The permission `society.voting.cast` is not registered.
