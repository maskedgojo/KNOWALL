'use client';
import Link from 'next/link';
import {useState} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Button, Card, EmptyState, ErrorState, Loading, PageHeading} from '@/components/ui';
import {shortDate} from '@/lib/format';
import {errorText, useLoad} from '@/lib/use-load';
import {operationsApi} from '@/lib/operations-api';
import {timeRange} from '@/lib/operations-types';

export default function MyBookings() {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.facilities.book');
  // Capture "now" when the data loads, not during render.
  const load = useLoad(async () => allowed ? {...await operationsApi.myBookings(), loadedAt: Date.now()} : null, [allowed]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  if (!allowed) return <PageHeading eyebrow="SOCIETY OPERATIONS" title="My bookings" description="Current resident access is required."/>;

  async function cancel(id: string) {
    setBusy(id); setError('');
    try { await operationsApi.cancelBooking(id); load.refresh(); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(''); }
  }

  return <>
    <PageHeading eyebrow="SOCIETY OPERATIONS" title="My bookings" description="Every request, approval and cancellation is kept in the booking history." action={<Link className="btn btn-primary" href="/facilities">Book an amenity</Link>}/>
    {error && <div className="mb-4"><Alert tone="warning">{error}</Alert></div>}
    {load.loading ? <Loading label="Loading bookings…"/> : load.error ? <ErrorState error={load.error} onRetry={load.refresh}/> : load.value?.bookings.length ? <div className="stack">{load.value.bookings.map(booking => {
      const upcoming = new Date(booking.starts_at).getTime() > load.value!.loadedAt;
      return <Card key={booking.id}>
        <div className="between"><h2 className="card-title">{booking.facility_name}</h2><Badge value={booking.status}/></div>
        <p className="mt-2 small muted">{timeRange(booking.starts_at, booking.ends_at)} · {booking.purpose}</p>
        {booking.decision_reason && <p className="mt-2 small">Note: {booking.decision_reason}</p>}
        <ol className="mt-3 small muted">{booking.history.map((entry, index) => <li key={index}>{shortDate(entry.created_at)} — {entry.from_status ? `${entry.from_status} → ` : ''}{entry.to_status}{entry.reason ? ` (${entry.reason})` : ''}</li>)}</ol>
        {upcoming && (booking.status === 'PENDING' || booking.status === 'CONFIRMED') && <div className="mt-3"><Button variant="danger" busy={busy === booking.id} onClick={() => void cancel(booking.id)}>Cancel booking</Button></div>}
      </Card>;
    })}</div> : <EmptyState title="No bookings yet" description="Book the clubhouse or a sports court from the amenities page." action={<Link className="btn btn-secondary" href="/facilities">View amenities</Link>}/>}
  </>;
}
