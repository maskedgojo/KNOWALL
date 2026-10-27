'use client';
import Link from 'next/link';
import {useAuth} from '@/components/auth-provider';
import {Badge, Card, ErrorState, Loading, PageHeading} from '@/components/ui';
import {disputeApi} from '@/lib/endpoints';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';

export default function DisputeDetail({id}: {id: string}) {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.notices.read');
  const load = useLoad(async () => allowed ? disputeApi.one(id) : null, [allowed, id]);
  if (!allowed) return <PageHeading eyebrow="RESIDENT PORTAL" title="Dispute unavailable" description="Current resident access is required."/>;
  if (load.loading) return <Loading label="Loading dispute…"/>;
  if (load.error || !load.value) return <ErrorState error={load.error || 'This dispute is not available.'} onRetry={load.refresh}/>;
  const dispute = load.value.dispute;
  return <>
    <PageHeading eyebrow="RESIDENT PORTAL / PRIVATE DISPUTE" title={dispute.title} description={shortDate(dispute.created_at)} action={<Link className="btn btn-secondary" href="/disputes">My disputes</Link>}/>
    <Card><div className="between"><Badge value={dispute.status}/><span className="small muted">Visible only to you</span></div><p className="mt-4 whitespace-pre-wrap">{dispute.description}</p><p className="mt-4 small muted">Status changes, appeals, and attachments are not available.</p></Card>
  </>;
}
