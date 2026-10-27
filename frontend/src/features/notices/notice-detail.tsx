'use client';
import Link from 'next/link';
import {useAuth} from '@/components/auth-provider';
import {Badge, Card, ErrorState, Loading, PageHeading} from '@/components/ui';
import {noticeApi} from '@/lib/endpoints';
import {useLoad} from '@/lib/use-load';
import {noticeWhen} from './resident-notices';

export default function NoticeDetail({id}:{id:string}) {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.notices.read');
  const load = useLoad(async () => allowed ? noticeApi.visibleOne(id) : null, [allowed, id]);
  if (!allowed) return <PageHeading eyebrow="RESIDENT PORTAL" title="Notice unavailable" description="Current resident access is required to read this notice."/>;
  if (load.loading) return <Loading label="Loading notice…"/>;
  if (load.error || !load.value) return <ErrorState error={load.error || 'This notice is not available.'} onRetry={load.refresh}/>;
  const notice = load.value.notice;
  return <>
    <PageHeading eyebrow="RESIDENT PORTAL / OFFICIAL NOTICE" title={notice.title} description={noticeWhen(notice)} action={<Link className="btn btn-secondary" href="/notices">All notices</Link>}/>
    <Card><div className="between"><Badge value={notice.status}/>{notice.replaces_notice_id && <span className="small muted">Replaces an earlier notice</span>}</div><p className="mt-4 whitespace-pre-wrap">{notice.body}</p></Card>
  </>;
}
