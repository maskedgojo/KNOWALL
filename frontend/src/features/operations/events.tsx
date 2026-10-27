'use client';
import {useState} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Button, Card, EmptyState, ErrorState, Loading, PageHeading} from '@/components/ui';
import {shortDate} from '@/lib/format';
import {errorText, useLoad} from '@/lib/use-load';
import {operationsApi} from '@/lib/operations-api';
import {timeRange, type SocietyEvent} from '@/lib/operations-types';

export default function Events() {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.notices.read');
  // Capture "now" when the data loads, not during render.
  const load = useLoad(async () => allowed ? {...await operationsApi.events(), loadedAt: Date.now()} : null, [allowed]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  if (!allowed) return <PageHeading eyebrow="SOCIETY OPERATIONS" title="Society events" description="Current resident access is required."/>;

  async function act(event: SocietyEvent, action: () => Promise<unknown>) {
    setBusy(event.id); setError('');
    try { await action(); load.refresh(); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(''); }
  }

  return <>
    <PageHeading eyebrow="SOCIETY OPERATIONS" title="Society events" description="RSVP to society events. When an event is full you join the waitlist and move up automatically if someone cancels."/>
    {error && <div className="mb-4"><Alert tone="warning">{error}</Alert></div>}
    {load.loading ? <Loading label="Loading events…"/> : load.error ? <ErrorState error={load.error} onRetry={load.refresh}/> : load.value?.events.length ? <div className="stack">{load.value.events.map(event => {
      const open = event.status === 'PUBLISHED' && new Date(event.starts_at).getTime() > load.value!.loadedAt;
      const active = event.my_rsvp === 'GOING' || event.my_rsvp === 'WAITLISTED';
      return <Card key={event.id}>
        <div className="between"><h2 className="card-title">{event.title}</h2><Badge value={event.status}/></div>
        <p className="mt-2 small muted">{timeRange(event.starts_at, event.ends_at)} · {event.venue} · Organised by {event.organizer_display_name}</p>
        <p className="mt-2">{event.description}</p>
        <p className="mt-2 small muted">{event.going_count} of {event.capacity} places taken{event.waitlist_count ? ` · ${event.waitlist_count} on waitlist` : ''}{event.volunteer_slots ? ` · Volunteers ${event.volunteer_count}/${event.volunteer_slots}` : ''}</p>
        {event.updates.length > 0 && <div className="mt-3"><Alert tone="info"><strong>Organiser updates</strong><ul className="mt-1">{event.updates.map((update, index) => <li key={index} className="small">{shortDate(update.created_at)} — {update.message}</li>)}</ul></Alert></div>}
        <div className="mt-3 flex gap-2 items-center flex-wrap">
          {event.my_rsvp && <Badge value={event.my_rsvp === 'GOING' ? 'Going' : event.my_rsvp === 'WAITLISTED' ? 'Waitlisted' : 'Cancelled'}/>}
          {open && !active && <Button busy={busy === event.id} onClick={() => void act(event, () => operationsApi.rsvp(event.id))}>{event.going_count >= event.capacity ? 'Join waitlist' : 'RSVP'}</Button>}
          {open && active && <Button variant="secondary" busy={busy === event.id} onClick={() => void act(event, () => operationsApi.cancelRsvp(event.id))}>Cancel RSVP</Button>}
          {event.i_volunteered && <Badge value="Volunteering"/>}
          {open && event.volunteer_slots > 0 && !event.i_volunteered && event.volunteer_count < event.volunteer_slots && <Button variant="secondary" busy={busy === event.id} onClick={() => void act(event, () => operationsApi.volunteer(event.id))}>Volunteer to help</Button>}
          {open && event.i_volunteered && <Button variant="ghost" busy={busy === event.id} onClick={() => void act(event, () => operationsApi.withdrawVolunteer(event.id))}>Stop volunteering</Button>}
        </div>
      </Card>;
    })}</div> : <EmptyState title="No events" description="Published society events will appear here."/>}
  </>;
}
