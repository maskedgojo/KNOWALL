'use client';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {useState, type FormEvent} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, TextareaField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {disputeApi} from '@/lib/endpoints';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';

export default function DisputeList() {
  const {access} = useAuth();
  const router = useRouter();
  const allowed = !!access?.permissions.includes('society.notices.read');
  const load = useLoad(async () => allowed ? disputeApi.list() : {disputes: [], pagination: {limit: 30, offset: 0}}, [allowed]);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (!allowed) return <PageHeading eyebrow="RESIDENT PORTAL" title="My disputes" description="Current resident access is required."/>;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError('');
    try {
      const created = await disputeApi.create({title, description});
      router.push(`/disputes/${created.dispute.id}`);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'The dispute could not be submitted.');
    } finally {
      setBusy(false);
    }
  }

  return <>
    <PageHeading eyebrow="RESIDENT PORTAL" title="My disputes" description="Only you and the Society Admin can see the disputes you submit. The admin reviews each one and replies here."/>
    <div className="grid-2">
      <div>
        {load.loading ? <Loading label="Loading your disputes…"/> : load.error ? <ErrorState error={load.error} onRetry={load.refresh}/> : load.value?.disputes.length ? <div className="stack">{load.value.disputes.map(dispute => <Card key={dispute.id}><div className="between"><h2 className="card-title">{dispute.title}</h2><Badge value={dispute.status}/></div><p className="mt-3 small muted">{shortDate(dispute.created_at)}</p><div className="mt-3"><Link className="text-link small" href={`/disputes/${dispute.id}`}>Open dispute</Link></div></Card>)}</div> : <EmptyState title="No disputes" description="A dispute you submit will appear only in your list and the Society Admin's review queue."/>}
      </div>
      <Card>
        <h2 className="card-title">Submit a private dispute</h2>
        <form className="stack mt-4" onSubmit={submit}>
          {error && <Alert tone="warning">{error}</Alert>}
          <Field id="dispute-title" label="Title" value={title} onChange={event => setTitle(event.target.value)} minLength={3} maxLength={160} required/>
          <TextareaField id="dispute-description" label="Description" value={description} onChange={event => setDescription(event.target.value)} minLength={1} maxLength={8000} required/>
          <Button type="submit" busy={busy}>Submit dispute</Button>
        </form>
      </Card>
    </div>
  </>;
}
