# Community discussions

Eligible residents with `society.notices.read` can list and create society-wide
discussions and add threaded comments. The server uses society profile id `1`
and rejects a client-supplied society id.

`society.discussions.participate` and `society.discussions.moderate` are not
registered. Reporting, closing, and moderation are not implemented. Audit
events are `DISCUSSION_CREATED` and `COMMENT_CREATED` on entity type
`DISCUSSION`. Details store the title or comment id, not the text.

A comment parent must be null or a comment in the same discussion. A parent
from another discussion returns `409` `COMMENT_PARENT_MISMATCH`.

Migration `e4b8c2d71a05` revises `c3a91e7b4d20` and creates `discussions` and
`discussion_comments` only. It has not been applied by this change.
