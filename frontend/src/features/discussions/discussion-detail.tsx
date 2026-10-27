'use client';
import Link from 'next/link';
import {useState, type FormEvent} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Button, Card, ErrorState, Loading, PageHeading, TextareaField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {discussionApi} from '@/lib/endpoints';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import type {DiscussionComment} from '@/lib/types';

function replies(comments: DiscussionComment[], parentId: string | null): DiscussionComment[] {
  return comments.filter(comment => (comment.parent_comment_id ?? null) === parentId);
}

function CommentThread({comments, parentId, depth, onReply}: {comments: DiscussionComment[]; parentId: string | null; depth: number; onReply: (id: string) => void}) {
  return <>{replies(comments, parentId).map(comment => <div key={comment.id} className={depth ? 'mt-3 border-l border-slate-200 pl-4' : 'notice-card mb-3'}><div className="between"><strong>{comment.author_display_name}</strong><span className="small muted">{shortDate(comment.created_at)}</span></div><p className="mt-2 whitespace-pre-wrap">{comment.body}</p><button className="text-link small mt-2" type="button" onClick={() => onReply(comment.id)}>Reply</button><CommentThread comments={comments} parentId={comment.id} depth={depth + 1} onReply={onReply}/></div>)}</>;
}

export default function DiscussionDetail({id}: {id: string}) {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.notices.read');
  const load = useLoad(async () => allowed ? discussionApi.one(id) : null, [allowed, id]);
  const [body, setBody] = useState('');
  const [parentId, setParentId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (!allowed) return <PageHeading eyebrow="RESIDENT PORTAL" title="Discussion unavailable" description="Current resident access is required to read this discussion."/>;
  if (load.loading) return <Loading label="Loading discussion…"/>;
  if (load.error || !load.value) return <ErrorState error={load.error || 'This discussion is not available.'} onRetry={load.refresh}/>;
  const {discussion, comments} = load.value;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError('');
    try {
      await discussionApi.comment(id, {body, parent_comment_id: parentId});
      setBody('');
      setParentId(null);
      load.refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'The comment could not be posted.');
    } finally {
      setBusy(false);
    }
  }

  return <>
    <PageHeading eyebrow="RESIDENT PORTAL / DISCUSSION" title={discussion.title} description={`${discussion.author_display_name} · ${shortDate(discussion.created_at)}`} action={<Link className="btn btn-secondary" href="/discussions">All discussions</Link>}/>
    <Card><p className="whitespace-pre-wrap">{discussion.body}</p></Card>
    <div className="section-space">
      <h2 className="mb-3">Comments</h2>
      {comments.length ? <CommentThread comments={comments} parentId={null} depth={0} onReply={setParentId}/> : <p className="muted">No comments yet.</p>}
      <Card>
        <h2 className="card-title">{parentId ? 'Reply to a comment' : 'Add a comment'}</h2>
        <form className="stack mt-4" onSubmit={submit}>
          {error && <Alert tone="warning">{error}</Alert>}
          {parentId && <div className="between"><span className="small muted">Replying in this thread.</span><button className="text-link small" type="button" onClick={() => setParentId(null)}>Comment on the discussion instead</button></div>}
          <TextareaField id="comment-body" label="Comment" value={body} onChange={event => setBody(event.target.value)} minLength={1} maxLength={4000} required/>
          <Button type="submit" busy={busy}>Post comment</Button>
        </form>
      </Card>
    </div>
  </>;
}
