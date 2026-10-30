'use client';
import Link from 'next/link';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Card, ErrorState, Loading, PageHeading} from '@/components/ui';
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
    <Card><div className="between"><Badge value={dispute.status}/><span className="small muted">Visible only to you and the Society Admin</span></div><p className="mt-4 whitespace-pre-wrap">{dispute.description}</p>{dispute.admin_response ? <div className="mt-4"><Alert tone={dispute.status === 'RESOLVED' ? 'success' : 'info'}><strong>Society Admin response</strong>{dispute.status_changed_at ? ` · ${shortDate(dispute.status_changed_at)}` : ''}<p className="mt-2 whitespace-pre-wrap">{dispute.admin_response}</p></Alert></div> : <p className="mt-4 small muted">{dispute.status === 'IN_REVIEW' ? 'The Society Admin is reviewing this dispute.' : 'The Society Admin has not responded yet.'}</p>}<p className="mt-4 small muted">Appeals and attachments are not available.</p></Card>
  </>;
}
