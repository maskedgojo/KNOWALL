'use client';
import Link from 'next/link';
import {useState} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Button, Card, ErrorState, Loading, PageHeading} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {pollApi} from '@/lib/endpoints';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';

export default function PollDetail({id}: {id: string}) {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.notices.read');
  const load = useLoad(async () => allowed ? pollApi.one(id) : null, [allowed, id]);
  const [choice, setChoice] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  if (!allowed) return <PageHeading eyebrow="RESIDENT PORTAL" title="Poll unavailable" description="Current resident access is required."/>;
  if (load.loading) return <Loading label="Loading poll…"/>;
  if (load.error || !load.value) return <ErrorState error={load.error || 'This poll is not available.'} onRetry={load.refresh}/>;
  const poll = load.value.poll;

  async function vote() {
    setBusy(true); setError(''); setMessage('');
    try {
      await pollApi.vote(id, choice);
      setMessage('Your non-binding response was recorded.');
      load.refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'The response could not be recorded.');
    } finally {
      setBusy(false);
    }
  }

  return <>
    <PageHeading eyebrow="RESIDENT PORTAL / INFORMAL POLL" title={poll.question} description={`Non-binding · ${shortDate(poll.opens_at)} to ${shortDate(poll.closes_at)}`} action={<Link className="btn btn-secondary" href="/polls">All polls</Link>}/>
    <Card>
      <div className="between"><Badge value={poll.status}/><span className="small muted">Not a formal vote</span></div>
      {message && <div className="mt-4"><Alert tone="success">{message}</Alert></div>}
      {error && <div className="mt-4"><Alert tone="warning">{error}</Alert></div>}
      <div className="stack mt-4">
        {poll.options.map(option => <label key={option.id} className="between"><span><input className="mr-2" type="radio" name="poll-option" value={option.id} checked={choice === option.id || poll.my_option_id === option.id} disabled={poll.status !== 'OPEN' || !!poll.my_option_id} onChange={() => setChoice(option.id)}/>{option.label}</span>{poll.status === 'CLOSED' && <span className="small muted">{option.vote_count} responses</span>}</label>)}
      </div>
      {poll.status === 'OPEN' && !poll.my_option_id && <div className="mt-4"><Button type="button" busy={busy} disabled={!choice} onClick={() => void vote()}>Submit non-binding response</Button></div>}
      {poll.status === 'SCHEDULED' && <p className="mt-4 small muted">Responses are not accepted before the opening time.</p>}
      {poll.status !== 'CLOSED' && <p className="mt-4 small muted">Response counts stay hidden until the poll closes.</p>}
    </Card>
  </>;
}
