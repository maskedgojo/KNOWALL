'use client';
import Link from 'next/link';
import {useAuth} from '@/components/auth-provider';
import {Badge, Card, EmptyState, ErrorState, Loading, PageHeading} from '@/components/ui';
import {governanceApi} from '@/lib/endpoints';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';

export default function GovernanceHistory() {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.notices.read');
  const load = useLoad(async () => allowed ? governanceApi.history() : {events: [], pagination: {limit: 30, offset: 0}}, [allowed]);
  if (!allowed) return <PageHeading eyebrow="RESIDENT PORTAL" title="Governance history" description="Current resident access is required to view society governance events."/>;
  return <>
    <PageHeading eyebrow="RESIDENT PORTAL" title="Governance history" description="Published notices, discussions, and suggestions for Green Valley Residency. Private identity records are not included."/>
    {load.loading ? <Loading label="Loading governance history…"/> : load.error ? <ErrorState error={load.error} onRetry={load.refresh}/> : load.value?.events.length ? <div className="stack">{load.value.events.map(event => <Card key={event.id}><div className="between"><Badge value={event.event_type}/><span className="small muted">{shortDate(event.occurred_at)}</span></div><p className="mt-3">{event.summary}</p>{event.resource_path && <div className="mt-3"><Link className="text-link small" href={event.resource_path}>Open record</Link></div>}</Card>)}</div> : <EmptyState title="No governance events yet" description="Published notices, discussions, suggestions, informal polls, and proposals will appear here. Private disputes and individual poll responses are not listed."/>}
  </>;
}
