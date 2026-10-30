'use client';
import {useState} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Button, Card, EmptyState, ErrorState, Loading, PageHeading, TextareaField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {adminDisputeApi} from '@/lib/endpoints';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import type {AdminDispute, DisputeStatus} from '@/lib/types';

const FILTERS: [DisputeStatus | '', string][] = [['', 'All'], ['SUBMITTED', 'New'], ['IN_REVIEW', 'In review'], ['RESOLVED', 'Resolved']];

/** Status moves mirror Flask ADMIN_TRANSITIONS; a resolution needs a response for the resident. */
function DisputeActions({dispute, onDone}: {dispute: AdminDispute; onDone: () => void}) {
  const [response, setResponse] = useState(dispute.admin_response ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function move(status: 'IN_REVIEW' | 'RESOLVED') {
    setBusy(true); setError('');
    try { await adminDisputeApi.update(dispute.id, status, response); onDone(); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'The dispute could not be updated.'); }
    finally { setBusy(false); }
  }
  return <div className="mt-4 stack">
    <TextareaField id={`response-${dispute.id}`} label="Response to the resident" value={response} maxLength={4000} onChange={event => setResponse(event.target.value)}/>
    {error && <Alert tone="danger">{error}</Alert>}
    <div className="flex gap-2 flex-wrap">
      {dispute.status === 'SUBMITTED' && <Button type="button" variant="secondary" busy={busy} onClick={() => void move('IN_REVIEW')}>Start review</Button>}
      {dispute.status !== 'RESOLVED' && <Button type="button" busy={busy} disabled={!response.trim()} onClick={() => void move('RESOLVED')}>Mark resolved</Button>}
      {dispute.status === 'RESOLVED' && <Button type="button" variant="secondary" busy={busy} onClick={() => void move('IN_REVIEW')}>Reopen</Button>}
    </div>
  </div>;
}

export default function AdminDisputes() {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.notices.manage');
  const [filter, setFilter] = useState<DisputeStatus | ''>('');
  const load = useLoad(async () => allowed ? adminDisputeApi.list(filter) : null, [allowed, filter]);
  if (!allowed) return <PageHeading eyebrow="ADMINISTRATION" title="Disputes" description="Only a verified Society Admin can handle disputes."/>;
  return <>
    <PageHeading eyebrow="ADMINISTRATION / PRIVATE" title="Disputes" description="Private disputes raised by residents. Only the resident who raised a dispute and the Society Admin can see it. Your response is shown to that resident."/>
    <div className="mb-5 flex gap-2 flex-wrap">{FILTERS.map(([value, label]) => <Button key={label} type="button" variant={filter === value ? 'primary' : 'secondary'} onClick={() => setFilter(value)}>{label}</Button>)}</div>
    {load.loading ? <Loading label="Loading disputes…"/> : load.error ? <ErrorState error={load.error} onRetry={load.refresh}/> : load.value?.disputes.length ? <div className="stack">{load.value.disputes.map(dispute => <Card key={dispute.id}>
      <div className="between"><h2 className="card-title">{dispute.title}</h2><Badge value={dispute.status}/></div>
      <p className="mt-3 whitespace-pre-wrap">{dispute.description}</p>
      <p className="mt-3 small muted">Raised by {dispute.author_display_name} · {shortDate(dispute.created_at)}{dispute.handled_by_display_name ? ` · Last handled by ${dispute.handled_by_display_name} on ${shortDate(dispute.status_changed_at)}` : ''}</p>
      <DisputeActions key={`${dispute.id}-${dispute.status}`} dispute={dispute} onDone={load.refresh}/>
    </Card>)}</div> : <EmptyState title="No disputes" description={filter ? 'No disputes have this status.' : 'Residents have not raised a dispute yet.'}/>}
  </>;
}
