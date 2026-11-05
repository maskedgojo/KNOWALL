'use client';
import Link from 'next/link';
import {useState} from 'react';
import {Alert, Badge, Button, Card, ErrorState, Loading, PageHeading, TextareaField} from '@/components/ui';
import {pretty, shortDate} from '@/lib/format';
import {errorText, useLoad} from '@/lib/use-load';
import {operationsApi, uploadTicketPhoto} from '@/lib/operations-api';
import {PhotoGallery, PhotoUpload} from './photos';

export default function TicketDetail({id}: {id: string}) {
  const load = useLoad(() => operationsApi.ticket(id), [id]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function send(action: 'CLARIFY' | 'CONFIRM' | 'REOPEN') {
    setBusy(true); setError('');
    try { const result = await operationsApi.feedback(id, action, message || undefined); load.setValue(result); setMessage(''); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  if (load.loading) return <Loading label="Loading request…"/>;
  if (load.error || !load.value) return <ErrorState error={load.error || 'Request not found.'} onRetry={load.refresh}/>;
  const ticket = load.value.request;
  return <>
    <PageHeading eyebrow="MAINTENANCE REQUEST" title={ticket.title} description={`${pretty(ticket.issue_type)} · Flat ${ticket.flat}${ticket.location_note ? ` · ${ticket.location_note}` : ''}`} action={<Link className="btn btn-secondary" href="/maintenance">All requests</Link>}/>
    <div className="grid-2">
      <Card>
        <div className="between"><h2 className="card-title">Status</h2><Badge value={ticket.status}/></div>
        <p className="mt-3">{ticket.description}</p>
        {ticket.assignee_label && <p className="mt-2 small muted">Assigned to {ticket.assignee_label}</p>}
        {error && <div className="mt-3"><Alert tone="warning">{error}</Alert></div>}
        {ticket.status !== 'CONFIRMED' && <div className="mt-4 stack">
          <TextareaField id="ticket-feedback" label={ticket.status === 'COMPLETED' ? 'Comment (required to reopen)' : 'Add a clarification'} value={message} onChange={event => setMessage(event.target.value)} maxLength={2000}/>
          <div className="flex gap-2 flex-wrap">
            {ticket.status === 'COMPLETED' ? <>
              <Button busy={busy} onClick={() => void send('CONFIRM')}>Confirm the fix</Button>
              <Button variant="danger" busy={busy} disabled={!message.trim()} onClick={() => void send('REOPEN')}>Still not fixed — reopen</Button>
            </> : <Button variant="secondary" busy={busy} disabled={!message.trim()} onClick={() => void send('CLARIFY')}>Send clarification</Button>}
          </div>
        </div>}
        {ticket.status === 'CONFIRMED' && <div className="mt-4"><Alert tone="success">You confirmed this fix. The request is closed.</Alert></div>}
      </Card>
      <Card>
        <h2 className="card-title">Photos</h2>
        <p className="small muted mt-1">Add a photo of the problem. Staff may add a photo of the finished repair.</p>
        <div className="mt-3"><PhotoGallery photos={ticket.photos}/></div>
        {ticket.status !== 'CONFIRMED' && <PhotoUpload id="ticket-photo" onUpload={async (file, caption) => { await uploadTicketPhoto(id, file, caption); load.refresh(); }}/>}
      </Card>
      <Card>
        <h2 className="card-title">Timeline</h2>
        <ol className="mt-3 stack">{ticket.timeline.map((entry, index) => <li key={index} className="notice-card">
          <div className="between"><strong className="small">{entry.to_status ? pretty(entry.to_status) : pretty(entry.kind)}</strong><span className="small muted">{shortDate(entry.created_at)}</span></div>
          {entry.message && <p className="mt-1 small">{entry.message}</p>}
          <p className="mt-1 small muted">{entry.actor_display_name}</p>
        </li>)}</ol>
      </Card>
    </div>
  </>;
}
