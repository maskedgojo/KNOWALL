'use client';
import Link from 'next/link';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Card, ErrorState, Loading, PageHeading} from '@/components/ui';
import {proposalApi} from '@/lib/endpoints';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';

export default function ProposalDetail({id}: {id: string}) {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.notices.read');
  const load = useLoad(async () => allowed ? proposalApi.one(id) : null, [allowed, id]);
  if (!allowed) return <PageHeading eyebrow="RESIDENT PORTAL" title="Proposal unavailable" description="Current resident access is required."/>;
  if (load.loading) return <Loading label="Loading proposal…"/>;
  if (load.error || !load.value) return <ErrorState error={load.error || 'This proposal is not available.'} onRetry={load.refresh}/>;
  const proposal = load.value.proposal;
  return <>
    <PageHeading eyebrow="RESIDENT PORTAL / PROPOSAL" title={proposal.title} description={`${proposal.author_display_name} · ${shortDate(proposal.created_at)}`} action={<Link className="btn btn-secondary" href="/proposals">All proposals</Link>}/>
    <Card><div className="between"><Badge value={proposal.status}/><span className="small muted">Voting is not open</span></div><p className="mt-4 whitespace-pre-wrap">{proposal.summary}</p>{proposal.status === 'SUBMITTED' ? <p className="mt-4 small muted">Awaiting a Society Admin decision. This record does not accept ballots.</p> : <div className="mt-4"><Alert tone={proposal.status === 'APPROVED' ? 'success' : 'warning'}><strong>{proposal.status === 'APPROVED' ? 'Approved' : 'Rejected'} by the Society Admin</strong> · {shortDate(proposal.decided_at)}{proposal.decision_note && <p className="mt-2 whitespace-pre-wrap">{proposal.decision_note}</p>}</Alert></div>}</Card>
  </>;
}
