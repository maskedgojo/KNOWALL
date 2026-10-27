'use client';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {useState, type FormEvent} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, TextareaField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {discussionApi} from '@/lib/endpoints';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';

export default function DiscussionList() {
  const {access} = useAuth();
  const router = useRouter();
  const allowed = !!access?.permissions.includes('society.notices.read');
  const load = useLoad(async () => allowed ? discussionApi.list() : {discussions: [], pagination: {limit: 30, offset: 0}}, [allowed]);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (!allowed) return <PageHeading eyebrow="RESIDENT PORTAL" title="Discussions" description="Current resident access is required to join society discussions."/>;

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError('');
    try {
      const created = await discussionApi.create({title, body});
      router.push(`/discussions/${created.discussion.id}`);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'The discussion could not be created.');
    } finally {
      setBusy(false);
    }
  }

  return <>
    <PageHeading eyebrow="RESIDENT PORTAL" title="Discussions" description="Conversations for eligible residents of Green Valley Residency. Reporting and moderation are not available yet."/>
    <div className="grid-2">
      <div>
        {load.loading ? <Loading label="Loading discussions…"/> : load.error ? <ErrorState error={load.error} onRetry={load.refresh}/> : load.value?.discussions.length ? <div className="stack">{load.value.discussions.map(discussion => <Card key={discussion.id}><div className="between"><h2 className="card-title">{discussion.title}</h2><span className="small muted">{discussion.comment_count} {discussion.comment_count === 1 ? 'comment' : 'comments'}</span></div><p className="mt-3">{discussion.body}</p><div className="mt-3 between"><span className="small muted">{discussion.author_display_name} · {shortDate(discussion.created_at)}</span><Link className="text-link small" href={`/discussions/${discussion.id}`}>Open discussion</Link></div></Card>)}</div> : <EmptyState title="No discussions yet" description="Start a conversation for other eligible residents."/>}
      </div>
      <Card>
        <h2 className="card-title">Start a discussion</h2>
        <form className="stack mt-4" onSubmit={create}>
          {error && <Alert tone="warning">{error}</Alert>}
          <Field id="discussion-title" label="Title" value={title} onChange={event => setTitle(event.target.value)} minLength={3} maxLength={160} required/>
          <TextareaField id="discussion-body" label="Message" value={body} onChange={event => setBody(event.target.value)} minLength={1} maxLength={8000} required/>
          <Button type="submit" busy={busy}>Post discussion</Button>
        </form>
      </Card>
    </div>
  </>;
}
