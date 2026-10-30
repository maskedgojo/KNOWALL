'use client';
import {useState, type FormEvent} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, SelectField, TextareaField} from '@/components/ui';
import {pretty, shortDate} from '@/lib/format';
import {errorText, useLoad} from '@/lib/use-load';
import {operationsAdminApi, uploadTicketPhoto} from '@/lib/operations-api';
import {PhotoGallery, PhotoUpload} from './photos';
import {NEXT_TICKET_STATUS, isoFromLocal, timeRange, type MaintenanceTicket, type TicketStatus} from '@/lib/operations-types';

function TicketRow({ticket, onSaved}: {ticket: MaintenanceTicket; onSaved: () => void}) {
  const next = NEXT_TICKET_STATUS[ticket.status] ?? [];
  const [status, setStatus] = useState<TicketStatus | ''>(next[0] ?? '');
  const [message, setMessage] = useState('');
  const [assignee, setAssignee] = useState(ticket.assignee_label ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!status) return;
    setBusy(true); setError('');
    try { await operationsAdminApi.moveTicket(ticket.id, {status, message, assignee_label: assignee || undefined}); setMessage(''); onSaved(); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  return <div className="notice-card mb-3">
    <div className="between"><strong>{ticket.title}</strong><Badge value={ticket.status}/></div>
    <div className="mt-1 small muted">{pretty(ticket.issue_type)} · Flat {ticket.flat} · {ticket.reporter_display_name} · {shortDate(ticket.created_at)}{ticket.assignee_label ? ` · ${ticket.assignee_label}` : ''}</div>
    <p className="mt-1 small">{ticket.description}</p>
    <button className="text-link small mt-1" onClick={() => setOpen(!open)}>{open ? 'Hide timeline & photos' : `Timeline (${ticket.timeline.length}) & photos (${ticket.photos.length})`}</button>
    {open && <>
      <ol className="mt-2 small muted">{ticket.timeline.map((entry, index) => <li key={index}>{shortDate(entry.created_at)} — {entry.actor_display_name}: {entry.to_status ? `${pretty(entry.to_status)}. ` : `${pretty(entry.kind)}: `}{entry.message}</li>)}</ol>
      <div className="mt-3"><PhotoGallery photos={ticket.photos}/></div>
      {ticket.status !== 'CONFIRMED' && <PhotoUpload id={`fix-${ticket.id}`} label="Add fix evidence photo" onUpload={async (file, caption) => { await uploadTicketPhoto(ticket.id, file, caption); onSaved(); }}/>}
    </>}
    {next.length > 0 && <form className="stack mt-3" onSubmit={save}>
      {error && <Alert tone="warning">{error}</Alert>}
      <SelectField id={`move-${ticket.id}`} label="Move to" value={status} onChange={event => setStatus(event.target.value as TicketStatus)}>{next.map(item => <option key={item} value={item}>{pretty(item)}</option>)}</SelectField>
      {status === 'ASSIGNED' && <Field id={`assignee-${ticket.id}`} label="Assigned to" value={assignee} onChange={event => setAssignee(event.target.value)} maxLength={120} required/>}
      <Field id={`message-${ticket.id}`} label={status === 'COMPLETED' ? 'What was fixed' : 'Update for the resident'} value={message} onChange={event => setMessage(event.target.value)} maxLength={2000} required/>
      <Button type="submit" busy={busy}>Save update</Button>
    </form>}
  </div>;
}

export default function AdminMaintenance() {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.operations.manage');
  const [filter, setFilter] = useState('');
  const tickets = useLoad(async () => allowed ? operationsAdminApi.tickets(filter || undefined) : null, [allowed, filter]);
  const items = useLoad(async () => allowed ? operationsAdminApi.maintenance() : null, [allowed]);
  const [asset, setAsset] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  if (!allowed) return <PageHeading eyebrow="ADMINISTRATION" title="Maintenance" description="Limited to a verified Society Admin."/>;

  async function run(key: string, action: () => Promise<unknown>) {
    setBusy(key); setError('');
    try { await action(); items.refresh(); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(''); }
  }

  function schedule(event: FormEvent) {
    event.preventDefault();
    void run('schedule', async () => {
      await operationsAdminApi.schedule({asset, title, description, scheduled_start: isoFromLocal(start), scheduled_end: isoFromLocal(end)});
      setAsset(''); setTitle(''); setDescription('');
    });
  }

  return <>
    <PageHeading eyebrow="ADMINISTRATION" title="Maintenance" description="Triage resident repair requests and publish planned maintenance to all residents."/>
    {error && <div className="mb-4"><Alert tone="danger">{error}</Alert></div>}
    <div className="grid-2">
      <Card>
        <div className="between"><h2 className="card-title">Resident requests</h2>
          <SelectField id="ticket-filter" label="Show" value={filter} onChange={event => setFilter(event.target.value)}>
            <option value="">All</option>{['REPORTED', 'ASSIGNED', 'IN_PROGRESS', 'COMPLETED', 'REOPENED', 'CONFIRMED'].map(item => <option key={item} value={item}>{pretty(item)}</option>)}
          </SelectField>
        </div>
        <div className="mt-3">{tickets.loading ? <Loading/> : tickets.error ? <ErrorState error={tickets.error} onRetry={tickets.refresh}/> : tickets.value?.requests.length ? tickets.value.requests.map(ticket => <TicketRow key={`${ticket.id}-${ticket.status}`} ticket={ticket} onSaved={tickets.refresh}/>) : <EmptyState title="No requests" description="Nothing matches this filter."/>}</div>
      </Card>
      <div className="stack">
        <Card>
          <h2 className="card-title">Planned maintenance</h2>
          <div className="mt-3">{items.loading ? <Loading/> : items.value?.items.length ? items.value.items.map(item => <div key={item.id} className="notice-card mb-3">
            <div className="between"><strong>{item.title}</strong><Badge value={item.status}/></div>
            <div className="mt-1 small muted">{item.asset} · {timeRange(item.scheduled_start, item.scheduled_end)}</div>
            {item.status !== 'RESOLVED' && <div className="mt-2 flex gap-2">
              {item.status === 'PLANNED' && <Button variant="secondary" busy={busy === item.id} onClick={() => void run(item.id, () => operationsAdminApi.updateItem(item.id, 'Work has started.', 'IN_PROGRESS'))}>Mark started</Button>}
              <Button busy={busy === item.id} onClick={() => void run(item.id, () => operationsAdminApi.updateItem(item.id, 'Work is complete.', 'RESOLVED'))}>Mark resolved</Button>
            </div>}
          </div>) : <EmptyState title="Nothing scheduled" description="Publish planned work below."/>}</div>
        </Card>
        <Card>
          <h2 className="card-title">Schedule maintenance</h2>
          <form className="stack mt-3" onSubmit={schedule}>
            <Field id="item-asset" label="Asset" value={asset} onChange={event => setAsset(event.target.value)} placeholder="Lift B1" minLength={2} maxLength={120} required/>
            <Field id="item-title" label="Title" value={title} onChange={event => setTitle(event.target.value)} minLength={3} maxLength={160} required/>
            <TextareaField id="item-description" label="Details for residents" value={description} onChange={event => setDescription(event.target.value)} required/>
            <Field id="item-start" label="From" type="datetime-local" value={start} onChange={event => setStart(event.target.value)} required/>
            <Field id="item-end" label="Until" type="datetime-local" value={end} onChange={event => setEnd(event.target.value)} required/>
            <Button type="submit" busy={busy === 'schedule'}>Publish schedule</Button>
          </form>
        </Card>
      </div>
    </div>
  </>;
}
