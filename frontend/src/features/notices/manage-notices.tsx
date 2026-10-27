'use client';
import {useState} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, TextareaField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {noticeApi} from '@/lib/endpoints';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import type {Notice} from '@/lib/types';

function localInput(value: string | null) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function expiryValue(value: string) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

export default function ManageNotices() {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.notices.manage');
  const load = useLoad(async () => allowed ? noticeApi.managed() : {notices: [], pagination: {limit: 30, offset: 0}}, [allowed]);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [expiry, setExpiry] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (!allowed) return <PageHeading eyebrow="ADMINISTRATION" title="Official notices" description="Notice management is limited to a verified Society Admin."/>;
  const current = load.value?.notices.find(notice => notice.id === selected) ?? null;

  function choose(notice: Notice) {
    setSelected(notice.id);
    setTitle(notice.title);
    setBody(notice.body);
    setExpiry(localInput(notice.expires_at));
    setError('');
    setMessage('');
  }

  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true); setError(''); setMessage('');
    try { await action(); setMessage(success); load.refresh(); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : 'The notice could not be saved.'); }
    finally { setBusy(false); }
  }

  return <>
    <PageHeading eyebrow="ADMINISTRATION" title="Official notices" description="Drafts can be edited. Published text and expiry stay fixed; issue a replacement to correct them. Archive is separate from expiry."/>
    {message && <div className="mb-4"><Alert tone="success">{message}</Alert></div>}
    {error && <div className="mb-4"><Alert tone="danger">{error}</Alert></div>}
    <div className="grid-2">
      <Card>
        <h2 className="card-title">{current ? 'Selected notice' : 'New draft'}</h2>
        <div className="mt-4 stack">
          <Field id="notice-title" label="Title" value={title} onChange={event => setTitle(event.target.value)} disabled={!!current && current.status !== 'DRAFT'}/>
          <TextareaField id="notice-body" label="Body" value={body} onChange={event => setBody(event.target.value)} disabled={!!current && current.status !== 'DRAFT'}/>
          <Field id="notice-expiry" label="Expiry" type="datetime-local" value={expiry} hint="Leave blank for no expiry. Published expiry cannot be changed." onChange={event => setExpiry(event.target.value)} disabled={!!current && current.status !== 'DRAFT'}/>
          <div className="flex gap-2 flex-wrap">
            {!current && <Button busy={busy} onClick={() => void run(async () => { const created = await noticeApi.create({title, body, expires_at: expiryValue(expiry)}); setSelected(created.notice.id); }, 'Draft created.')}>Create draft</Button>}
            {current?.status === 'DRAFT' && <Button busy={busy} onClick={() => void run(() => noticeApi.update(current.id, {title, body, expires_at: expiryValue(expiry)}), 'Draft saved.')}>Save draft</Button>}
            {current?.status === 'DRAFT' && <Button variant="secondary" busy={busy} onClick={() => void run(() => noticeApi.publish(current.id), 'Notice published.')}>Publish</Button>}
            {current && current.status !== 'ARCHIVED' && <Button variant="danger" busy={busy} onClick={() => void run(() => noticeApi.archive(current.id), 'Notice archived.')}>Archive</Button>}
            {current?.status === 'PUBLISHED' && <Button variant="secondary" busy={busy} onClick={() => void run(async () => { const copy = await noticeApi.replace(current.id); choose(copy.notice); }, 'Replacement draft created. The original notice is unchanged.')}>Create replacement</Button>}
            {current && <Button variant="ghost" onClick={() => { setSelected(null); setTitle(''); setBody(''); setExpiry(''); }}>New draft</Button>}
          </div>
        </div>
      </Card>
      <Card>
        <h2 className="card-title">Society notices</h2>
        {load.loading ? <Loading label="Loading notices…"/> : load.error ? <ErrorState error={load.error} onRetry={load.refresh}/> : load.value?.notices.length ? load.value.notices.map(notice => <button className="notice-card mb-3 w-full text-left" key={notice.id} onClick={() => choose(notice)}><div className="between"><strong>{notice.title}</strong><Badge value={notice.status}/></div><div className="mt-1 small muted">{notice.visible_to_residents ? 'Visible to residents' : 'Hidden from residents'} · {notice.expires_at ? `Expires ${shortDate(notice.expires_at)}` : 'No expiry'}</div></button>) : <EmptyState title="No notices yet" description="Create a draft before publishing it to residents."/>}
      </Card>
    </div>
  </>;
}
