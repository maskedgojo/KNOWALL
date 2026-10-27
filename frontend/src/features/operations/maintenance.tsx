'use client';
import Link from 'next/link';
import {useState, type FormEvent} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, SelectField, TextareaField} from '@/components/ui';
import {pretty, shortDate} from '@/lib/format';
import {errorText, useLoad} from '@/lib/use-load';
import {operationsApi} from '@/lib/operations-api';
import {TICKET_TYPES, timeRange, type TicketType} from '@/lib/operations-types';

export default function Maintenance() {
  const {access} = useAuth();
  const canRead = !!access?.permissions.includes('society.notices.read');
  const canReport = !!access?.permissions.includes('society.maintenance.create');
  const schedule = useLoad(async () => canRead ? operationsApi.maintenance() : null, [canRead]);
  const tickets = useLoad(async () => canReport ? operationsApi.myTickets() : null, [canReport]);
  const [issueType, setIssueType] = useState<TicketType>('PLUMBING');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [location, setLocation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (!canRead && !canReport) return <PageHeading eyebrow="SOCIETY OPERATIONS" title="Maintenance" description="Current resident access is required."/>;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError('');
    try {
      await operationsApi.report({issue_type: issueType, title, description, location_note: location || undefined});
      setTitle(''); setDescription(''); setLocation(''); tickets.refresh();
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  return <>
    <PageHeading eyebrow="SOCIETY OPERATIONS" title="Maintenance" description="Planned work inside the society, and your private repair requests. Public roads and streetlights are reported as civic issues instead."/>
    <div className="grid-2">
      <div className="stack">
        <Card>
          <h2 className="card-title">Report a problem</h2>
          <form className="stack mt-4" onSubmit={submit}>
            {error && <Alert tone="warning">{error}</Alert>}
            <SelectField id="ticket-type" label="Type" value={issueType} onChange={event => setIssueType(event.target.value as TicketType)}>
              {TICKET_TYPES.map(type => <option key={type} value={type}>{pretty(type)}</option>)}
            </SelectField>
            <Field id="ticket-title" label="Title" value={title} onChange={event => setTitle(event.target.value)} minLength={3} maxLength={160} required/>
            <TextareaField id="ticket-description" label="What is wrong?" value={description} onChange={event => setDescription(event.target.value)} maxLength={4000} required/>
            <Field id="ticket-location" label="Where (optional)" value={location} onChange={event => setLocation(event.target.value)} maxLength={160}/>
            <Button type="submit" busy={busy} disabled={!canReport}>Submit request</Button>
          </form>
        </Card>
        <Card>
          <h2 className="card-title">My requests</h2>
          <p className="small muted mt-1">Only you and the society administrators can see these.</p>
          <div className="mt-3">{tickets.loading ? <Loading label="Loading requests…"/> : tickets.error ? <ErrorState error={tickets.error} onRetry={tickets.refresh}/> : tickets.value?.requests.length ? tickets.value.requests.map(ticket => <Link key={ticket.id} href={`/maintenance/requests/${ticket.id}`} className="notice-card mb-3 block"><div className="between"><strong>{ticket.title}</strong><Badge value={ticket.status}/></div><div className="mt-1 small muted">{pretty(ticket.issue_type)} · {ticket.flat} · Updated {shortDate(ticket.updated_at)}</div></Link>) : <EmptyState title="No requests" description="Report a lift, plumbing or common-area fault above."/>}</div>
        </Card>
      </div>
      <Card>
        <h2 className="card-title">Planned maintenance</h2>
        <div className="mt-3">{schedule.loading ? <Loading label="Loading schedule…"/> : schedule.error ? <ErrorState error={schedule.error} onRetry={schedule.refresh}/> : schedule.value?.items.length ? schedule.value.items.map(item => <div key={item.id} className="notice-card mb-3">
          <div className="between"><strong>{item.title}</strong><Badge value={item.status}/></div>
          <div className="mt-1 small muted">{item.asset} · {timeRange(item.scheduled_start, item.scheduled_end)}</div>
          <p className="mt-2 small">{item.description}</p>
          {item.updates.length > 0 && <ul className="mt-2 small muted">{item.updates.map((update, index) => <li key={index}>{shortDate(update.created_at)} — {update.message}</li>)}</ul>}
        </div>) : <EmptyState title="No planned work" description="Scheduled lift, water or power maintenance will appear here."/>}</div>
      </Card>
    </div>
  </>;
}
