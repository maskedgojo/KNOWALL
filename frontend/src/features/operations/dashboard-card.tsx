'use client';
import Link from 'next/link';
import {Badge, Card, ErrorState, Loading} from '@/components/ui';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import {operationsApi} from '@/lib/operations-api';
import {timeRange} from '@/lib/operations-types';

/** Resident dashboard summary for Module 3. Render only for residents with society.notices.read. */
export default function OperationsCard() {
  const load = useLoad(() => operationsApi.dashboard(), []);
  if (load.loading) return <Card><Loading label="Loading society operations…"/></Card>;
  if (load.error || !load.value) return <Card><ErrorState error={load.error || 'Unavailable.'} onRetry={load.refresh}/></Card>;
  const {bookings, events, disruptions, projects, my_open_requests} = load.value;
  const row = (key: string, href: string, title: string, meta: string, status?: string) => <Link key={key} href={href} className="notice-card mb-2 block"><div className="between"><strong className="small">{title}</strong>{status && <Badge value={status}/>}</div><div className="small muted mt-1">{meta}</div></Link>;
  return <div className="grid-2">
    <Card>
      <div className="card-head"><h2 className="card-title">My upcoming bookings & requests</h2><Link href="/bookings" className="text-link small">All bookings →</Link></div>
      {bookings.length || my_open_requests.length ? <>
        {bookings.map(b => row(b.id, '/bookings', b.facility_name, timeRange(b.starts_at, b.ends_at), b.status))}
        {my_open_requests.map(t => row(t.id, `/maintenance/requests/${t.id}`, t.title, 'Maintenance request', t.status))}
      </> : <p className="small muted">No upcoming bookings or open repair requests. <Link href="/facilities" className="text-link">Book an amenity</Link>.</p>}
    </Card>
    <Card>
      <div className="card-head"><h2 className="card-title">Around the society</h2><Link href="/events" className="text-link small">Events →</Link></div>
      {disruptions.map(d => row(d.id, '/maintenance', `${d.asset}: ${d.title}`, timeRange(d.scheduled_start, d.scheduled_end), d.status))}
      {events.map(e => row(e.id, '/events', e.title, `${shortDate(e.starts_at)} · ${e.venue}`))}
      {projects.map(p => row(p.id, '/development', p.title, 'Development project', p.status))}
      {!disruptions.length && !events.length && !projects.length && <p className="small muted">No upcoming events, outages or active projects.</p>}
    </Card>
  </div>;
}
