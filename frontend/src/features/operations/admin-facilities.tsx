'use client';
import {useState, type FormEvent} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, SelectField} from '@/components/ui';
import {errorText, useLoad} from '@/lib/use-load';
import {operationsAdminApi} from '@/lib/operations-api';
import {isoFromLocal, minuteLabel, timeRange} from '@/lib/operations-types';

const toMinute = (value: string) => { const [h, m] = value.split(':').map(Number); return h * 60 + m; };

export default function AdminFacilities() {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.operations.manage');
  const facilities = useLoad(async () => allowed ? operationsAdminApi.facilities() : null, [allowed]);
  const [filter, setFilter] = useState('PENDING');
  const bookings = useLoad(async () => allowed ? operationsAdminApi.bookings(filter || undefined) : null, [allowed, filter]);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');
  const [opens, setOpens] = useState('06:00');
  const [closes, setCloses] = useState('22:00');
  const [slot, setSlot] = useState(60);
  const [maxMinutes, setMaxMinutes] = useState(120);
  const [approval, setApproval] = useState(true);
  const [cap, setCap] = useState('');
  const [blackoutFor, setBlackoutFor] = useState('');
  const [blackStart, setBlackStart] = useState('');
  const [blackEnd, setBlackEnd] = useState('');
  const [blackReason, setBlackReason] = useState('');
  if (!allowed) return <PageHeading eyebrow="ADMINISTRATION" title="Amenities & bookings" description="Limited to a verified Society Admin."/>;

  async function run(key: string, action: () => Promise<unknown>, success: string) {
    setBusy(key); setError(''); setMessage('');
    try { await action(); setMessage(success); facilities.refresh(); bookings.refresh(); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(''); }
  }

  function create(event: FormEvent) {
    event.preventDefault();
    void run('create', () => operationsAdminApi.createFacility({
      name, location, open_minute: toMinute(opens), close_minute: toMinute(closes), slot_minutes: slot,
      max_minutes_per_booking: maxMinutes, requires_approval: approval,
      max_upcoming_per_resident: cap ? Number(cap) : null,
    }), 'Facility added.');
  }

  function blackout(event: FormEvent) {
    event.preventDefault();
    void run('blackout', async () => {
      const result = await operationsAdminApi.blackout(blackoutFor, {starts_at: isoFromLocal(blackStart), ends_at: isoFromLocal(blackEnd), reason: blackReason});
      setBlackReason('');
      return result;
    }, 'Facility blocked. Overlapping bookings were cancelled and residents can see the reason.');
  }

  return <>
    <PageHeading eyebrow="ADMINISTRATION" title="Amenities & bookings" description="Manage facility rules, approve booking requests and block facilities for repairs."/>
    {message && <div className="mb-4"><Alert tone="success">{message}</Alert></div>}
    {error && <div className="mb-4"><Alert tone="danger">{error}</Alert></div>}
    <div className="grid-2">
      <Card>
        <div className="between"><h2 className="card-title">Booking requests</h2>
          <SelectField id="booking-filter" label="Show" value={filter} onChange={event => setFilter(event.target.value)}>
            <option value="PENDING">Pending</option><option value="CONFIRMED">Confirmed</option><option value="CANCELLED">Cancelled</option><option value="REJECTED">Rejected</option><option value="">All</option>
          </SelectField>
        </div>
        <div className="mt-3">{bookings.loading ? <Loading label="Loading bookings…"/> : bookings.error ? <ErrorState error={bookings.error} onRetry={bookings.refresh}/> : bookings.value?.bookings.length ? bookings.value.bookings.map(booking => <div key={booking.id} className="notice-card mb-3">
          <div className="between"><strong>{booking.facility_name}</strong><Badge value={booking.status}/></div>
          <div className="mt-1 small muted">{timeRange(booking.starts_at, booking.ends_at)} · {booking.resident_display_name}</div>
          <p className="mt-1 small">{booking.purpose}</p>
          {booking.status === 'PENDING' && <div className="mt-2 flex gap-2">
            <Button busy={busy === booking.id} onClick={() => void run(booking.id, () => operationsAdminApi.decide(booking.id, 'APPROVE'), 'Booking approved.')}>Approve</Button>
            <Button variant="danger" busy={busy === booking.id} onClick={() => { const reason = window.prompt('Reason for rejecting this booking?'); if (reason) void run(booking.id, () => operationsAdminApi.decide(booking.id, 'REJECT', reason), 'Booking rejected.'); }}>Reject</Button>
          </div>}
        </div>) : <EmptyState title="Nothing here" description="No bookings match this filter."/>}</div>
      </Card>
      <div className="stack">
        <Card>
          <h2 className="card-title">Facilities</h2>
          <div className="mt-3">{facilities.loading ? <Loading/> : facilities.error ? <ErrorState error={facilities.error} onRetry={facilities.refresh}/> : facilities.value?.facilities.length ? facilities.value.facilities.map(facility => <div key={facility.id} className="notice-card mb-3">
            <div className="between"><strong>{facility.name}</strong><Badge value={facility.is_active ? 'ACTIVE' : 'DISABLED'}/></div>
            <div className="mt-1 small muted">{minuteLabel(facility.open_minute)}–{minuteLabel(facility.close_minute)} · {facility.slot_minutes}-min slots · {facility.requires_approval ? 'Needs approval' : 'Auto-confirm'} · {facility.max_upcoming_per_resident ? `Max ${facility.max_upcoming_per_resident} upcoming per resident` : 'No per-resident limit'}</div>
            <div className="mt-2 flex gap-2">
              <Button variant="secondary" onClick={() => setBlackoutFor(facility.id)}>Block for repairs</Button>
              <Button variant="ghost" busy={busy === facility.id} onClick={() => void run(facility.id, () => operationsAdminApi.updateFacility(facility.id, {is_active: !facility.is_active}), facility.is_active ? 'Facility hidden from residents.' : 'Facility reactivated.')}>{facility.is_active ? 'Deactivate' : 'Reactivate'}</Button>
            </div>
          </div>) : <EmptyState title="No facilities" description="Add the clubhouse or a sports court below."/>}</div>
        </Card>
        {blackoutFor && <Card>
          <h2 className="card-title">Block {facilities.value?.facilities.find(item => item.id === blackoutFor)?.name}</h2>
          <form className="stack mt-3" onSubmit={blackout}>
            <Field id="blackout-start" label="From" type="datetime-local" value={blackStart} onChange={event => setBlackStart(event.target.value)} required/>
            <Field id="blackout-end" label="Until" type="datetime-local" value={blackEnd} onChange={event => setBlackEnd(event.target.value)} required/>
            <Field id="blackout-reason" label="Reason shown to residents" value={blackReason} onChange={event => setBlackReason(event.target.value)} minLength={3} maxLength={300} required/>
            <div className="flex gap-2"><Button type="submit" variant="danger" busy={busy === 'blackout'}>Block and cancel bookings</Button><Button variant="ghost" onClick={() => setBlackoutFor('')}>Close</Button></div>
          </form>
        </Card>}
        <Card>
          <h2 className="card-title">Add facility</h2>
          <form className="stack mt-3" onSubmit={create}>
            <Field id="facility-name" label="Name" value={name} onChange={event => setName(event.target.value)} minLength={2} maxLength={120} required/>
            <Field id="facility-location" label="Location" value={location} onChange={event => setLocation(event.target.value)} maxLength={160}/>
            <div className="grid-2"><Field id="facility-opens" label="Opens" type="time" value={opens} onChange={event => setOpens(event.target.value)} required/><Field id="facility-closes" label="Closes" type="time" value={closes} onChange={event => setCloses(event.target.value)} required/></div>
            <div className="grid-2"><Field id="facility-slot" label="Slot length (min)" type="number" min={15} max={480} value={slot} onChange={event => setSlot(Number(event.target.value))}/><Field id="facility-max" label="Longest booking (min)" type="number" min={15} max={1440} value={maxMinutes} onChange={event => setMaxMinutes(Number(event.target.value))}/></div>
            <Field id="facility-cap" label="Max upcoming bookings per resident" type="number" min={1} max={50} value={cap} onChange={event => setCap(event.target.value)} hint="Leave blank for no limit."/>
            <label className="flex gap-2 items-center small"><input type="checkbox" checked={approval} onChange={event => setApproval(event.target.checked)}/> Bookings need admin approval</label>
            <Button type="submit" busy={busy === 'create'}>Add facility</Button>
          </form>
        </Card>
      </div>
    </div>
  </>;
}
