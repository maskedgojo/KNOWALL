'use client';
import Link from 'next/link';
import {useState, type FormEvent} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, SelectField} from '@/components/ui';
import {errorText, useLoad} from '@/lib/use-load';
import {operationsApi} from '@/lib/operations-api';
import {minuteLabel, timeRange, type Facility, type Slot} from '@/lib/operations-types';

function today() {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

const REASONS: Record<string, string> = {PAST: 'Past', OUTSIDE_BOOKING_WINDOW: 'Too far ahead', BLOCKED: 'Closed', BOOKED: 'Booked'};

export default function Facilities() {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.facilities.book');
  const list = useLoad(async () => allowed ? operationsApi.facilities() : {facilities: []}, [allowed]);
  const [selected, setSelected] = useState<Facility | null>(null);
  if (!allowed) return <PageHeading eyebrow="SOCIETY OPERATIONS" title="Amenities" description="Current resident access is required to book society amenities."/>;
  return <>
    <PageHeading eyebrow="SOCIETY OPERATIONS" title="Amenities" description="Check free slots and book shared facilities. Some facilities need committee approval before the booking is confirmed." action={<Link className="btn btn-secondary" href="/bookings">My bookings</Link>}/>
    <div className="grid-2">
      <div className="stack">
        {list.loading ? <Loading label="Loading facilities…"/> : list.error ? <ErrorState error={list.error} onRetry={list.refresh}/> : list.value?.facilities.length ? list.value.facilities.map(facility => <Card key={facility.id}>
          <div className="between"><h2 className="card-title">{facility.name}</h2><Badge value={facility.requires_approval ? 'Approval needed' : 'Instant'}/></div>
          <p className="mt-2 small muted">{facility.description || 'No description.'}</p>
          <p className="mt-2 small muted">{facility.location} · Open {minuteLabel(facility.open_minute)}–{minuteLabel(facility.close_minute)} · Up to {facility.max_minutes_per_booking} min · Book {facility.booking_window_days} days ahead{facility.max_upcoming_per_resident ? ` · Max ${facility.max_upcoming_per_resident} upcoming per resident` : ''}</p>
          <div className="mt-3"><Button variant={selected?.id === facility.id ? 'primary' : 'secondary'} onClick={() => setSelected(facility)}>Check availability</Button></div>
        </Card>) : <EmptyState title="No amenities yet" description="The society administrator has not added bookable facilities."/>}
      </div>
      {selected ? <BookingPanel key={selected.id} facility={selected}/> : <Card><EmptyState title="Choose a facility" description="Select a facility to see its free slots."/></Card>}
    </div>
  </>;
}

function BookingPanel({facility}: {facility: Facility}) {
  const [date, setDate] = useState(today);
  const slots = useLoad(() => operationsApi.availability(facility.id, date), [facility.id, date]);
  const [start, setStart] = useState<Slot | null>(null);
  const [length, setLength] = useState(1);
  const [purpose, setPurpose] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');
  const maxSlots = Math.max(1, Math.floor(facility.max_minutes_per_booking / facility.slot_minutes));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!start) return;
    setBusy(true); setError(''); setDone('');
    const ends = new Date(new Date(start.starts_at).getTime() + length * facility.slot_minutes * 60000).toISOString();
    try {
      const created = await operationsApi.book({facility_id: facility.id, starts_at: start.starts_at, ends_at: ends, purpose});
      setDone(created.booking.status === 'CONFIRMED' ? 'Booking confirmed.' : 'Booking requested. It holds the slot until an administrator decides.');
      setStart(null); setPurpose(''); slots.refresh();
    } catch (cause) { setError(errorText(cause)); slots.refresh(); }
    finally { setBusy(false); }
  }

  return <Card>
    <h2 className="card-title">Book {facility.name}</h2>
    <div className="mt-4 stack">
      {done && <Alert tone="success">{done} <Link className="text-link" href="/bookings">View my bookings</Link></Alert>}
      {error && <Alert tone="warning">{error}</Alert>}
      <Field id="booking-date" label="Date" type="date" value={date} onChange={event => { setDate(event.target.value); setStart(null); }} required/>
      {slots.loading ? <Loading label="Checking slots…"/> : slots.error ? <ErrorState error={slots.error} onRetry={slots.refresh}/> :
        <div className="flex flex-wrap gap-2" role="list" aria-label="Time slots">{slots.value?.slots.map(slot => {
          const label = new Date(slot.starts_at).toLocaleTimeString('en-IN', {hour: '2-digit', minute: '2-digit'});
          const chosen = start?.starts_at === slot.starts_at;
          return <button key={slot.starts_at} type="button" role="listitem" disabled={!slot.available} onClick={() => { setStart(slot); setLength(1); }} className={`btn ${chosen ? 'btn-primary' : 'btn-secondary'}`} title={slot.reason ? REASONS[slot.reason] : 'Available'}>{label}{!slot.available && <span className="small"> · {slot.reason ? REASONS[slot.reason] : ''}</span>}</button>;
        })}</div>}
      {start && <form className="stack" onSubmit={submit}>
        <SelectField id="booking-length" label="Duration" value={length} onChange={event => setLength(Number(event.target.value))}>
          {Array.from({length: maxSlots}, (_, i) => i + 1).map(n => <option key={n} value={n}>{n * facility.slot_minutes} minutes</option>)}
        </SelectField>
        <p className="small muted">{timeRange(start.starts_at, new Date(new Date(start.starts_at).getTime() + length * facility.slot_minutes * 60000).toISOString())}</p>
        <Field id="booking-purpose" label="Purpose" value={purpose} onChange={event => setPurpose(event.target.value)} minLength={3} maxLength={300} required/>
        <Button type="submit" busy={busy}>{facility.requires_approval ? 'Request booking' : 'Book now'}</Button>
      </form>}
    </div>
  </Card>;
}
