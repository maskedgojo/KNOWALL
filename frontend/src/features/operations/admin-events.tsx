'use client';
import {useState, type FormEvent} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, TextareaField} from '@/components/ui';
import {errorText, useLoad} from '@/lib/use-load';
import {operationsAdminApi} from '@/lib/operations-api';
import {isoFromLocal, timeRange, type SocietyEvent} from '@/lib/operations-types';

export default function AdminEvents() {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.operations.manage');
  const load = useLoad(async () => allowed ? operationsAdminApi.events() : null, [allowed]);
  const [open, setOpen] = useState<string | null>(null);
  const attendees = useLoad(async () => open ? operationsAdminApi.attendees(open) : null, [open]);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [venue, setVenue] = useState('');
  const [starts, setStarts] = useState('');
  const [ends, setEnds] = useState('');
  const [capacity, setCapacity] = useState(50);
  const [volunteers, setVolunteers] = useState(0);
  const [updateText, setUpdateText] = useState('');
  const [locality, setLocality] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  if (!allowed) return <PageHeading eyebrow="ADMINISTRATION" title="Society events" description="Limited to a verified Society Admin."/>;

  async function run(key: string, action: () => Promise<unknown>, success: string) {
    setBusy(key); setError(''); setMessage('');
    try { await action(); setMessage(success); load.refresh(); attendees.refresh(); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(''); }
  }

  function create(event: FormEvent) {
    event.preventDefault();
    void run('create', async () => {
      await operationsAdminApi.createEvent({title, description, venue, starts_at: isoFromLocal(starts), ends_at: isoFromLocal(ends), capacity, volunteer_slots: volunteers, locality_publish_requested: locality});
      setTitle(''); setDescription(''); setVenue('');
    }, 'Draft event created. Publish it when ready.');
  }

  const actions = (event: SocietyEvent) => <div className="mt-2 flex gap-2 flex-wrap">
    {event.status === 'DRAFT' && <Button busy={busy === event.id} onClick={() => void run(event.id, () => operationsAdminApi.eventAction(event.id, 'publish'), 'Event published.')}>Publish</Button>}
    {event.status === 'PUBLISHED' && <Button variant="secondary" busy={busy === event.id} onClick={() => void run(event.id, () => operationsAdminApi.eventAction(event.id, 'close'), 'Event closed.')}>Close event</Button>}
    {(event.status === 'DRAFT' || event.status === 'PUBLISHED') && <Button variant="danger" busy={busy === event.id} onClick={() => void run(event.id, () => operationsAdminApi.eventAction(event.id, 'cancel'), 'Event cancelled.')}>Cancel</Button>}
    {event.status !== 'DRAFT' && <Button variant="ghost" onClick={() => setOpen(open === event.id ? null : event.id)}>{open === event.id ? 'Hide attendees' : 'Attendees'}</Button>}
  </div>;

  return <>
    <PageHeading eyebrow="ADMINISTRATION" title="Society events" description="Create, publish and close events. RSVPs over capacity join a waitlist automatically."/>
    {message && <div className="mb-4"><Alert tone="success">{message}</Alert></div>}
    {error && <div className="mb-4"><Alert tone="danger">{error}</Alert></div>}
    <div className="grid-2">
      <div className="stack">{load.loading ? <Loading/> : load.error ? <ErrorState error={load.error} onRetry={load.refresh}/> : load.value?.events.length ? load.value.events.map(event => <Card key={event.id}>
        <div className="between"><h2 className="card-title">{event.title}</h2><Badge value={event.status}/></div>
        <p className="mt-1 small muted">{timeRange(event.starts_at, event.ends_at)} · {event.venue} · {event.going_count}/{event.capacity} going · {event.waitlist_count} waitlisted{event.volunteer_slots ? ` · ${event.volunteer_count}/${event.volunteer_slots} volunteers` : ''}{event.locality_publish_requested ? ' · Locality opt-in requested' : ''}</p>
        {event.updates.length > 0 && <ul className="mt-2 small muted">{event.updates.map((update, index) => <li key={index}>Update: {update.message}</li>)}</ul>}
        {actions(event)}
        {open === event.id && <div className="mt-3">
          {(event.status === 'DRAFT' || event.status === 'PUBLISHED') && <form className="flex gap-2 items-end mb-3" onSubmit={submit => { submit.preventDefault(); void run(`u-${event.id}`, async () => { await operationsAdminApi.postEventUpdate(event.id, updateText); setUpdateText(''); }, 'Update posted to residents.'); }}>
            <Field id={`event-update-${event.id}`} label="Post an update to residents" value={updateText} onChange={change => setUpdateText(change.target.value)} maxLength={2000} required/>
            <Button type="submit" variant="secondary" busy={busy === `u-${event.id}`}>Post</Button>
          </form>}
          <strong className="small">Attendees</strong>
          {attendees.loading ? <Loading/> : attendees.value?.attendees.length ? attendees.value.attendees.map(person => <div key={person.user_id} className="between py-1 small">
            <span>{person.display_name} · <Badge value={person.status}/></span>
            {person.status === 'GOING' && <label className="flex gap-1 items-center"><input type="checkbox" checked={person.attended} onChange={change => void run(person.user_id, () => operationsAdminApi.attendance(event.id, person.user_id, change.target.checked), 'Attendance saved.')}/> Attended</label>}
          </div>) : <p className="small muted">No RSVPs yet.</p>}
          {event.volunteer_slots > 0 && <><strong className="small mt-3 block">Volunteers</strong>{attendees.value?.volunteers.length ? attendees.value.volunteers.map(person => <div key={person.user_id} className="py-1 small">{person.display_name}{person.note ? ` — ${person.note}` : ''}</div>) : <p className="small muted">No volunteers yet.</p>}</>}
        </div>}
      </Card>) : <EmptyState title="No events" description="Create the first society event."/>}</div>
      <Card>
        <h2 className="card-title">New event</h2>
        <form className="stack mt-3" onSubmit={create}>
          <Field id="event-title" label="Title" value={title} onChange={event => setTitle(event.target.value)} minLength={3} maxLength={160} required/>
          <TextareaField id="event-description" label="Description" value={description} onChange={event => setDescription(event.target.value)} required/>
          <Field id="event-venue" label="Venue" value={venue} onChange={event => setVenue(event.target.value)} minLength={2} maxLength={160} required/>
          <Field id="event-starts" label="Starts" type="datetime-local" value={starts} onChange={event => setStarts(event.target.value)} required/>
          <Field id="event-ends" label="Ends" type="datetime-local" value={ends} onChange={event => setEnds(event.target.value)} required/>
          <Field id="event-capacity" label="Capacity" type="number" min={1} max={5000} value={capacity} onChange={event => setCapacity(Number(event.target.value))} required/>
          <Field id="event-volunteers" label="Volunteer places (0 = none needed)" type="number" min={0} max={200} value={volunteers} onChange={event => setVolunteers(Number(event.target.value))}/>
          <label className="flex gap-2 items-center small"><input type="checkbox" checked={locality} onChange={event => setLocality(event.target.checked)}/> Request locality listing (Module 4 reviews it; RSVP lists are never shared)</label>
          <Button type="submit" busy={busy === 'create'}>Create draft</Button>
        </form>
      </Card>
    </div>
  </>;
}
