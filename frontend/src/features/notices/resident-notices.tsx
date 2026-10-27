'use client';
import Link from 'next/link';
import {useEffect, useState} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Badge, Card, EmptyState, ErrorState, Loading, PageHeading} from '@/components/ui';
import {noticeApi} from '@/lib/endpoints';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import type {Notice} from '@/lib/types';

export function noticeWhen(notice: Notice) {
  const expiry = notice.expires_at ? `Expires ${shortDate(notice.expires_at)}` : 'No expiry date';
  return `${shortDate(notice.published_at)} · ${expiry}`;
}

/** Hide a notice as soon as its expiry instant passes, without waiting for another navigation. */
export function residentNoticeCurrent(notice: Notice, now = Date.now()) {
  if (notice.status !== 'PUBLISHED' || notice.visible_to_residents === false) return false;
  if (!notice.expires_at) return true;
  const expiry = new Date(notice.expires_at).getTime();
  return Number.isFinite(expiry) && expiry > now;
}

export default function ResidentNotices() {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.notices.read');
  const load = useLoad(async () => allowed ? noticeApi.visible() : {notices: [], pagination: {limit: 30, offset: 0}}, [allowed]);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const upcoming = (load.value?.notices ?? [])
      .map(notice => notice.expires_at ? new Date(notice.expires_at).getTime() : Number.POSITIVE_INFINITY)
      .filter(expiry => expiry > Date.now());
    const nextExpiry = Math.min(...upcoming);
    const timer = Number.isFinite(nextExpiry)
      ? window.setTimeout(() => setNow(Date.now()), nextExpiry - Date.now() + 50)
      : undefined;
    const refreshIfVisible = () => { if (document.visibilityState === 'visible') load.refresh(); };
    const onPageShow = (event: PageTransitionEvent) => { if (event.persisted) load.refresh(); };
    window.addEventListener('focus', refreshIfVisible);
    window.addEventListener('pageshow', onPageShow);
    document.addEventListener('visibilitychange', refreshIfVisible);
    return () => {
      if (timer !== undefined) window.clearTimeout(timer);
      window.removeEventListener('focus', refreshIfVisible);
      window.removeEventListener('pageshow', onPageShow);
      document.removeEventListener('visibilitychange', refreshIfVisible);
    };
  }, [load]);
  const notices = (load.value?.notices ?? []).filter(notice => residentNoticeCurrent(notice, now));
  if (!allowed) return <PageHeading eyebrow="RESIDENT PORTAL" title="Official notices" description="Current resident access is required to read society notices."/>;
  return <>
    <PageHeading eyebrow="RESIDENT PORTAL" title="Official notices" description="Published announcements for Green Valley Residency. Expired and archived notices are not listed."/>
    {load.loading ? <Loading label="Loading notices…"/> : load.error ? <ErrorState error={load.error} onRetry={load.refresh}/> : notices.length ? <div className="stack">{notices.map(notice => <Card key={notice.id}><div className="between"><h2 className="card-title">{notice.title}</h2><Badge value={notice.status}/></div><p className="mt-3">{notice.body}</p><div className="mt-3 between"><span className="small muted">{noticeWhen(notice)}</span><Link className="text-link small" href={`/notices/${notice.id}`}>Open notice</Link></div></Card>)}</div> : <EmptyState title="No current notices" description="Published notices that are still in force will appear here."/>}
  </>;
}
