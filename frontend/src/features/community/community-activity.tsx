'use client';
import {useState} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Button, Card, EmptyState, ErrorState, Loading, PageHeading, TextareaField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {communityActivityApi} from '@/lib/endpoints';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import type {AdminDiscussion, AdminDiscussionComment, AdminProposal} from '@/lib/types';

type Section = 'discussions' | 'suggestions' | 'polls' | 'proposals';

function replies(comments: AdminDiscussionComment[], parentId: string | null): AdminDiscussionComment[] {
  return comments.filter(comment => (comment.parent_comment_id ?? null) === parentId);
}

function CommentThread({comments, parentId, depth}: {comments: AdminDiscussionComment[]; parentId: string | null; depth: number}) {
  return <>{replies(comments, parentId).map(comment => <div key={comment.id} className={depth ? 'mt-3 border-l border-slate-200 pl-4' : 'notice-card mb-3'}><div className="between"><strong>{comment.author_display_name}</strong><span className="small muted">{shortDate(comment.created_at)}</span></div><p className="mt-2 whitespace-pre-wrap">{comment.body}</p><CommentThread comments={comments} parentId={comment.id} depth={depth + 1}/></div>)}</>;
}

const failure = (cause: unknown, fallback: string) => cause instanceof ApiError ? cause.message : fallback;

/** Soft-hide: the post is kept and can be restored; residents stop seeing it. */
function DiscussionModeration({discussion, onDone}: {discussion: AdminDiscussion; onDone: () => void}) {
  const [reason, setReason] = useState('');
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function run(action: () => Promise<unknown>) {
    setBusy(true); setError('');
    try { await action(); setOpen(false); setReason(''); onDone(); }
    catch (cause) { setError(failure(cause, 'The discussion could not be updated.')); }
    finally { setBusy(false); }
  }
  if (discussion.hidden) return <div className="mt-3"><Alert tone="warning">Hidden from residents by {discussion.hidden_by_display_name || 'a Society Admin'} on {shortDate(discussion.hidden_at)}. Reason: {discussion.hidden_reason}</Alert>{error && <div className="mt-2"><Alert tone="danger">{error}</Alert></div>}<div className="mt-3"><Button type="button" variant="secondary" busy={busy} onClick={() => void run(() => communityActivityApi.restoreDiscussion(discussion.id))}>Restore for residents</Button></div></div>;
  if (!open) return <Button type="button" variant="ghost" onClick={() => setOpen(true)}>Hide from residents</Button>;
  return <div className="mt-3 stack">
    <TextareaField id={`hide-${discussion.id}`} label="Reason for hiding (kept in the audit trail)" value={reason} maxLength={500} onChange={event => setReason(event.target.value)}/>
    {error && <Alert tone="danger">{error}</Alert>}
    <div className="flex gap-2 flex-wrap"><Button type="button" variant="danger" busy={busy} disabled={reason.trim().length < 3} onClick={() => void run(() => communityActivityApi.hideDiscussion(discussion.id, reason))}>Hide discussion</Button><Button type="button" variant="secondary" disabled={busy} onClick={() => setOpen(false)}>Cancel</Button></div>
  </div>;
}

/** One recorded decision per proposal; this is not a vote. */
function ProposalDecision({proposal, onDone}: {proposal: AdminProposal; onDone: () => void}) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (proposal.status !== 'SUBMITTED') return <p className="mt-3 small muted">{proposal.status === 'APPROVED' ? 'Approved' : 'Rejected'} by {proposal.decided_by_display_name || 'a Society Admin'} on {shortDate(proposal.decided_at)}.{proposal.decision_note ? ` Note: ${proposal.decision_note}` : ''}</p>;
  async function decide(decision: 'APPROVED' | 'REJECTED') {
    setBusy(true); setError('');
    try { await communityActivityApi.decideProposal(proposal.id, decision, note); onDone(); }
    catch (cause) { setError(failure(cause, 'The decision could not be saved.')); }
    finally { setBusy(false); }
  }
  return <div className="mt-4 stack">
    <TextareaField id={`decision-${proposal.id}`} label="Decision note for residents (optional)" value={note} maxLength={1000} onChange={event => setNote(event.target.value)}/>
    {error && <Alert tone="danger">{error}</Alert>}
    <div className="flex gap-2 flex-wrap"><Button type="button" busy={busy} onClick={() => void decide('APPROVED')}>Approve</Button><Button type="button" variant="danger" disabled={busy} onClick={() => void decide('REJECTED')}>Reject</Button></div>
    <p className="small muted">A decision is final and visible to residents in governance history.</p>
  </div>;
}

const SECTIONS = [['discussions', 'Discussions'], ['suggestions', 'Suggestions'], ['polls', 'Informal polls'], ['proposals', 'Proposals']] as const;

// `only` pins the view to one section (used by the per-section admin nav routes).
export default function CommunityActivity({only}: {only?: Section} = {}) {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.notices.manage');
  const [chosen, setSection] = useState<Section>('discussions');
  const section = only ?? chosen;
  const title = only ? SECTIONS.find(([value]) => value === only)![1] : 'Community Activity';
  const [discussionId, setDiscussionId] = useState<string | null>(null);
  const discussions = useLoad(async () => allowed && section === 'discussions' ? communityActivityApi.discussions() : null, [allowed, section]);
  const thread = useLoad(async () => allowed && discussionId ? communityActivityApi.discussion(discussionId) : null, [allowed, discussionId]);
  const suggestions = useLoad(async () => allowed && section === 'suggestions' ? communityActivityApi.suggestions() : null, [allowed, section]);
  const polls = useLoad(async () => allowed && section === 'polls' ? communityActivityApi.polls() : null, [allowed, section]);
  const proposals = useLoad(async () => allowed && section === 'proposals' ? communityActivityApi.proposals() : null, [allowed, section]);
  if (!allowed) return <PageHeading eyebrow="ADMINISTRATION" title={title} description="Only a verified Society Admin can review community activity."/>;

  return <>
    <PageHeading eyebrow="ADMINISTRATION / COMMUNITY" title={title} description={only === 'discussions' ? 'Review resident discussions. Hide a post that breaks community rules; it can be restored later.' : only === 'proposals' ? 'Review resident proposals and record an approve or reject decision. Formal voting is not open.' : only ? `Review ${title.toLowerCase()} from eligible residents. This view is read only.` : 'Review discussions, suggestions, informal polls, and proposals. Hide discussions and decide proposals from their own pages. Private disputes are not shown here.'}/>
    {!only && <div className="mb-5 flex gap-2 flex-wrap">
      {SECTIONS.map(([value, label]) => <Button key={value} type="button" variant={section === value ? 'primary' : 'secondary'} onClick={() => { setSection(value); setDiscussionId(null); }}>{label}</Button>)}
    </div>}
    {section === 'discussions' && (discussions.loading ? <Loading label="Loading discussions…"/> : discussions.error ? <ErrorState error={discussions.error} onRetry={discussions.refresh}/> : discussions.value?.discussions.length ? <div className="stack">{discussions.value.discussions.map(discussion => <Card key={discussion.id}><div className="between"><h2 className="card-title">{discussion.title}</h2><div className="flex gap-2">{discussion.hidden && <Badge value="HIDDEN"/>}<Badge value={`${discussion.comment_count} comments`}/></div></div><p className="mt-3 whitespace-pre-wrap">{discussion.body}</p><p className="mt-3 small muted">{discussion.author_display_name} · {shortDate(discussion.created_at)}</p><div className="mt-3 flex gap-2 flex-wrap"><Button type="button" variant="secondary" onClick={() => setDiscussionId(discussion.id)}>Read comments</Button>{!discussion.hidden && <DiscussionModeration discussion={discussion} onDone={discussions.refresh}/>}</div>{discussion.hidden && <DiscussionModeration discussion={discussion} onDone={discussions.refresh}/>}{discussionId === discussion.id && <div className="mt-4">{thread.loading ? <Loading label="Loading comments…"/> : thread.error ? <ErrorState error={thread.error} onRetry={thread.refresh}/> : thread.value?.comments.length ? <CommentThread comments={thread.value.comments} parentId={null} depth={0}/> : <p className="muted">No comments yet.</p>}</div>}</Card>)}</div> : <EmptyState title="No discussions" description="Eligible residents have not started a discussion yet."/>)}
    {section === 'suggestions' && (suggestions.loading ? <Loading label="Loading suggestions…"/> : suggestions.error ? <ErrorState error={suggestions.error} onRetry={suggestions.refresh}/> : suggestions.value?.suggestions.length ? <div className="stack">{suggestions.value.suggestions.map(suggestion => <Card key={suggestion.id}><div className="between"><h2 className="card-title">{suggestion.title}</h2><Badge value={suggestion.status}/></div><p className="mt-3 whitespace-pre-wrap">{suggestion.description}</p><p className="mt-3 small muted">{suggestion.category} · {suggestion.author_display_name} · {shortDate(suggestion.created_at)}</p><p className="mt-3 small muted">Committee decisions are not available.</p></Card>)}</div> : <EmptyState title="No suggestions" description="Eligible residents have not submitted a suggestion yet."/>)}
    {section === 'polls' && (polls.loading ? <Loading label="Loading polls…"/> : polls.error ? <ErrorState error={polls.error} onRetry={polls.refresh}/> : polls.value?.polls.length ? <div className="stack">{polls.value.polls.map(poll => <Card key={poll.id}><div className="between"><h2 className="card-title">{poll.question}</h2><Badge value={poll.status}/></div><p className="mt-3 small muted">Non-binding · {shortDate(poll.opens_at)} to {shortDate(poll.closes_at)}</p><div className="stack mt-4">{poll.options.map(option => <div className="between" key={option.id}><span>{option.label}</span>{poll.status === 'CLOSED' ? <span className="small muted">{option.vote_count} responses</span> : null}</div>)}</div>{poll.status !== 'CLOSED' && <p className="mt-4 small muted">Results stay hidden until this poll closes. Individual responses are not shown.</p>}</Card>)}</div> : <EmptyState title="No informal polls" description="Eligible residents have not created a poll yet."/>)}
    {section === 'proposals' && (proposals.loading ? <Loading label="Loading proposals…"/> : proposals.error ? <ErrorState error={proposals.error} onRetry={proposals.refresh}/> : proposals.value?.proposals.length ? <div className="stack">{proposals.value.proposals.map(proposal => <Card key={proposal.id}><div className="between"><h2 className="card-title">{proposal.title}</h2><Badge value={proposal.status}/></div><p className="mt-3 whitespace-pre-wrap">{proposal.summary}</p><p className="mt-3 small muted">{proposal.author_display_name} · {shortDate(proposal.created_at)}</p><p className="mt-3 small muted">Voting is not open. This record has no ballot or tally.</p><ProposalDecision proposal={proposal} onDone={proposals.refresh}/></Card>)}</div> : <EmptyState title="No proposals" description="Eligible residents have not submitted a proposal yet."/>)}
  </>;
}
