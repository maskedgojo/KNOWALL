'use client';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {useState, type FormEvent} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, TextareaField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {proposalApi} from '@/lib/endpoints';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';

export default function ProposalList() {
  const {access} = useAuth();
  const router = useRouter();
  const allowed = !!access?.permissions.includes('society.notices.read');
  const load = useLoad(async () => allowed ? proposalApi.list() : {proposals: [], pagination: {limit: 30, offset: 0}}, [allowed]);
  const [title, setTitle] = useState('');
  const [summary, setSummary] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (!allowed) return <PageHeading eyebrow="RESIDENT PORTAL" title="Proposals" description="Current resident access is required."/>;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError('');
    try {
      const created = await proposalApi.create({title, summary});
      router.push(`/proposals/${created.proposal.id}`);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'The proposal could not be submitted.');
    } finally {
      setBusy(false);
    }
  }

  return <>
    <PageHeading eyebrow="RESIDENT PORTAL" title="Proposals" description="A proposal is not an informal poll and cannot be voted on yet. The Society Admin reviews each proposal and records an approve or reject decision."/>
    <div className="grid-2">
      <div>
        {load.loading ? <Loading label="Loading proposals…"/> : load.error ? <ErrorState error={load.error} onRetry={load.refresh}/> : load.value?.proposals.length ? <div className="stack">{load.value.proposals.map(proposal => <Card key={proposal.id}><div className="between"><h2 className="card-title">{proposal.title}</h2><Badge value={proposal.status}/></div><p className="mt-3">{proposal.summary}</p><div className="mt-3 between"><span className="small muted">{proposal.author_display_name} · {shortDate(proposal.created_at)}</span><Link className="text-link small" href={`/proposals/${proposal.id}`}>Open proposal</Link></div></Card>)}</div> : <EmptyState title="No proposals" description="Submit a proposal. It will not open a ballot."/>}
      </div>
      <Card>
        <h2 className="card-title">Submit a proposal</h2>
        <form className="stack mt-4" onSubmit={submit}>
          {error && <Alert tone="warning">{error}</Alert>}
          <Field id="proposal-title" label="Title" value={title} onChange={event => setTitle(event.target.value)} minLength={3} maxLength={160} required/>
          <TextareaField id="proposal-summary" label="Summary" value={summary} onChange={event => setSummary(event.target.value)} minLength={1} maxLength={8000} required/>
          <Button type="submit" busy={busy}>Submit proposal</Button>
        </form>
      </Card>
    </div>
  </>;
}
