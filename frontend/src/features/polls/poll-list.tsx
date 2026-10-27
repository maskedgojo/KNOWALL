'use client';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {useState, type FormEvent} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, TextareaField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {pollApi} from '@/lib/endpoints';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';

function localValue(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export default function PollList() {
  const {access} = useAuth();
  const router = useRouter();
  const allowed = !!access?.permissions.includes('society.notices.read');
  const load = useLoad(async () => allowed ? pollApi.list() : {polls: [], pagination: {limit: 30, offset: 0}}, [allowed]);
  const [question, setQuestion] = useState('');
  const [first, setFirst] = useState('');
  const [second, setSecond] = useState('');
  const [opens, setOpens] = useState(() => localValue(new Date().toISOString()));
  const [closes, setCloses] = useState(() => localValue(new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString()));
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (!allowed) return <PageHeading eyebrow="RESIDENT PORTAL" title="Informal polls" description="Current resident access is required."/>;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError('');
    try {
      const created = await pollApi.create({
        question,
        options: [first, second],
        opens_at: new Date(opens).toISOString(),
        closes_at: new Date(closes).toISOString(),
      });
      router.push(`/polls/${created.poll.id}`);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'The poll could not be created.');
    } finally {
      setBusy(false);
    }
  }

  return <>
    <PageHeading eyebrow="RESIDENT PORTAL" title="Informal polls" description="These polls are explicitly non-binding. They are not formal society votes. Counts stay hidden until a poll closes."/>
    <div className="grid-2">
      <div>
        {load.loading ? <Loading label="Loading polls…"/> : load.error ? <ErrorState error={load.error} onRetry={load.refresh}/> : load.value?.polls.length ? <div className="stack">{load.value.polls.map(poll => <Card key={poll.id}><div className="between"><h2 className="card-title">{poll.question}</h2><Badge value={poll.status}/></div><p className="mt-3 small muted">Non-binding · Closes {shortDate(poll.closes_at)}</p><div className="mt-3"><Link className="text-link small" href={`/polls/${poll.id}`}>Open poll</Link></div></Card>)}</div> : <EmptyState title="No informal polls" description="Create a non-binding poll for eligible residents."/>}
      </div>
      <Card>
        <h2 className="card-title">New non-binding poll</h2>
        <form className="stack mt-4" onSubmit={submit}>
          {error && <Alert tone="warning">{error}</Alert>}
          <TextareaField id="poll-question" label="Question" value={question} onChange={event => setQuestion(event.target.value)} minLength={3} maxLength={200} required/>
          <Field id="poll-option-a" label="Choice 1" value={first} onChange={event => setFirst(event.target.value)} maxLength={80} required/>
          <Field id="poll-option-b" label="Choice 2" value={second} onChange={event => setSecond(event.target.value)} maxLength={80} required/>
          <Field id="poll-opens" label="Opens" type="datetime-local" value={opens} onChange={event => setOpens(event.target.value)} required/>
          <Field id="poll-closes" label="Closes" type="datetime-local" value={closes} onChange={event => setCloses(event.target.value)} required/>
          <Button type="submit" busy={busy}>Create non-binding poll</Button>
        </form>
      </Card>
    </div>
  </>;
}
