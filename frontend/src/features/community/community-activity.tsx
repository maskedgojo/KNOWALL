'use client';
import {useState} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Badge, Button, Card, EmptyState, ErrorState, Loading, PageHeading} from '@/components/ui';
import {communityActivityApi} from '@/lib/endpoints';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import type {AdminDiscussionComment} from '@/lib/types';

type Section = 'discussions' | 'suggestions' | 'polls' | 'proposals';

function replies(comments: AdminDiscussionComment[], parentId: string | null): AdminDiscussionComment[] {
  return comments.filter(comment => (comment.parent_comment_id ?? null) === parentId);
}

function CommentThread({comments, parentId, depth}: {comments: AdminDiscussionComment[]; parentId: string | null; depth: number}) {
  return <>{replies(comments, parentId).map(comment => <div key={comment.id} className={depth ? 'mt-3 border-l border-slate-200 pl-4' : 'notice-card mb-3'}><div className="between"><strong>{comment.author_display_name}</strong><span className="small muted">{shortDate(comment.created_at)}</span></div><p className="mt-2 whitespace-pre-wrap">{comment.body}</p><CommentThread comments={comments} parentId={comment.id} depth={depth + 1}/></div>)}</>;
}

export default function CommunityActivity() {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.notices.manage');
  const [section, setSection] = useState<Section>('discussions');
  const [discussionId, setDiscussionId] = useState<string | null>(null);
  const discussions = useLoad(async () => allowed && section === 'discussions' ? communityActivityApi.discussions() : null, [allowed, section]);
  const thread = useLoad(async () => allowed && discussionId ? communityActivityApi.discussion(discussionId) : null, [allowed, discussionId]);
  const suggestions = useLoad(async () => allowed && section === 'suggestions' ? communityActivityApi.suggestions() : null, [allowed, section]);
  const polls = useLoad(async () => allowed && section === 'polls' ? communityActivityApi.polls() : null, [allowed, section]);
  const proposals = useLoad(async () => allowed && section === 'proposals' ? communityActivityApi.proposals() : null, [allowed, section]);
  if (!allowed) return <PageHeading eyebrow="ADMINISTRATION" title="Community Activity" description="Only a verified Society Admin can review community activity."/>;

  return <>
    <PageHeading eyebrow="ADMINISTRATION / READ ONLY" title="Community Activity" description="Review discussions, suggestions, informal polls, and proposals. This page cannot create, edit, moderate, or decide anything. Private disputes are not shown."/>
    <div className="mb-5 flex gap-2 flex-wrap">
      {([['discussions', 'Discussions'], ['suggestions', 'Suggestions'], ['polls', 'Informal polls'], ['proposals', 'Proposals']] as const).map(([value, label]) => <Button key={value} type="button" variant={section === value ? 'primary' : 'secondary'} onClick={() => { setSection(value); setDiscussionId(null); }}>{label}</Button>)}
    </div>
    {section === 'discussions' && (discussions.loading ? <Loading label="Loading discussions…"/> : discussions.error ? <ErrorState error={discussions.error} onRetry={discussions.refresh}/> : discussions.value?.discussions.length ? <div className="stack">{discussions.value.discussions.map(discussion => <Card key={discussion.id}><div className="between"><h2 className="card-title">{discussion.title}</h2><Badge value={`${discussion.comment_count} comments`}/></div><p className="mt-3 whitespace-pre-wrap">{discussion.body}</p><p className="mt-3 small muted">{discussion.author_display_name} · {shortDate(discussion.created_at)}</p><div className="mt-3"><Button type="button" variant="secondary" onClick={() => setDiscussionId(discussion.id)}>Read comments</Button></div>{discussionId === discussion.id && <div className="mt-4">{thread.loading ? <Loading label="Loading comments…"/> : thread.error ? <ErrorState error={thread.error} onRetry={thread.refresh}/> : thread.value?.comments.length ? <CommentThread comments={thread.value.comments} parentId={null} depth={0}/> : <p className="muted">No comments yet.</p>}</div>}</Card>)}</div> : <EmptyState title="No discussions" description="Eligible residents have not started a discussion yet."/>)}
    {section === 'suggestions' && (suggestions.loading ? <Loading label="Loading suggestions…"/> : suggestions.error ? <ErrorState error={suggestions.error} onRetry={suggestions.refresh}/> : suggestions.value?.suggestions.length ? <div className="stack">{suggestions.value.suggestions.map(suggestion => <Card key={suggestion.id}><div className="between"><h2 className="card-title">{suggestion.title}</h2><Badge value={suggestion.status}/></div><p className="mt-3 whitespace-pre-wrap">{suggestion.description}</p><p className="mt-3 small muted">{suggestion.category} · {suggestion.author_display_name} · {shortDate(suggestion.created_at)}</p><p className="mt-3 small muted">Committee decisions are not available.</p></Card>)}</div> : <EmptyState title="No suggestions" description="Eligible residents have not submitted a suggestion yet."/>)}
    {section === 'polls' && (polls.loading ? <Loading label="Loading polls…"/> : polls.error ? <ErrorState error={polls.error} onRetry={polls.refresh}/> : polls.value?.polls.length ? <div className="stack">{polls.value.polls.map(poll => <Card key={poll.id}><div className="between"><h2 className="card-title">{poll.question}</h2><Badge value={poll.status}/></div><p className="mt-3 small muted">Non-binding · {shortDate(poll.opens_at)} to {shortDate(poll.closes_at)}</p><div className="stack mt-4">{poll.options.map(option => <div className="between" key={option.id}><span>{option.label}</span>{poll.status === 'CLOSED' ? <span className="small muted">{option.vote_count} responses</span> : null}</div>)}</div>{poll.status !== 'CLOSED' && <p className="mt-4 small muted">Results stay hidden until this poll closes. Individual responses are not shown.</p>}</Card>)}</div> : <EmptyState title="No informal polls" description="Eligible residents have not created a poll yet."/>)}
    {section === 'proposals' && (proposals.loading ? <Loading label="Loading proposals…"/> : proposals.error ? <ErrorState error={proposals.error} onRetry={proposals.refresh}/> : proposals.value?.proposals.length ? <div className="stack">{proposals.value.proposals.map(proposal => <Card key={proposal.id}><div className="between"><h2 className="card-title">{proposal.title}</h2><Badge value={proposal.status}/></div><p className="mt-3 whitespace-pre-wrap">{proposal.summary}</p><p className="mt-3 small muted">{proposal.author_display_name} · {shortDate(proposal.created_at)}</p><p className="mt-3 small muted">Voting is not open. This record has no ballot or result.</p></Card>)}</div> : <EmptyState title="No proposals" description="Eligible residents have not submitted a proposal yet."/>)}
  </>;
}
