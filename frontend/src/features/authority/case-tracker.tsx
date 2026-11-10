'use client';
import {useState, type FormEvent} from 'react';
import {Alert, Button, Card, ErrorState, Loading, TextareaField} from '@/components/ui';
import {authorityApi, proofPath} from '@/lib/authority-api';
import type {Verdict} from '@/lib/authority-types';
import {errorText, useLoad} from '@/lib/use-load';
import {CaseBadge, PrivatePhoto, SimulationBanner, dateTime, evidenceMeta} from './parts';

/**
 * Resident-facing linked case tracker on the civic issue page. It shows the same civic issue,
 * the same case id and the same status the simulated official sees; Module 6 owns that status.
 */
export default function CaseTracker({issueId, onChange}: {issueId: string; onChange?: () => void}) {
  const load = useLoad(() => authorityApi.caseStatus(issueId), [issueId]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [reason, setReason] = useState('');
  const [photo, setPhoto] = useState<File | null>(null);
  const [answer, setAnswer] = useState('');

  async function run(action: () => Promise<string | void>, done: string) {
    setBusy(true); setError(''); setNotice('');
    try {const message = await action(); setNotice(message || done); load.refresh(); onChange?.();} catch (cause) {setError(errorText(cause));} finally {setBusy(false);}
  }

  if (load.loading) return <Card><Loading label="Loading authority case…"/></Card>;
  if (load.error || !load.value) return <Card><ErrorState error={load.error || 'Case status unavailable.'} onRetry={load.refresh}/></Card>;
  const item = load.value.case;
  if (!item) return null;
  const v = item.verification;

  async function sendVerdict(event: FormEvent) {
    event.preventDefault();
    if (!item || !verdict) return;
    await run(async () => {
      const result = await authorityApi.verify(item.case_id, verdict, reason, verdict === 'DISPUTED' ? photo : null);
      setVerdict(null); setReason(''); setPhoto(null);
      if (result.outcome === 'CLOSED') return 'Thank you. Enough residents confirmed the fix, so the case is closed.';
      if (result.outcome === 'REOPENED') return 'Thank you. Residents disputed the fix, so the same case was reopened.';
    }, 'Thank you. Your verdict was recorded.');
  }
  async function sendAnswer(event: FormEvent) {
    event.preventDefault();
    if (!item) return;
    await run(async () => {await authorityApi.respondClarification(item.case_id, answer); setAnswer('');}, 'Your reply was sent to the department.');
  }

  return <Card>
    <div className="between"><h2 className="card-title">Authority case {item.authority_case_id}</h2><CaseBadge status={item.status} overdue={item.is_overdue}/></div>
    <div className="mt-2"><SimulationBanner/></div>
    {error && <Alert tone="warning">{error}</Alert>}
    {notice && <Alert tone="success">{notice}</Alert>}
    <p className="mt-2"><strong>{item.status_label}</strong></p>
    <p className="small muted">Department: {item.department?.name ?? '—'} (simulated) · Target date {dateTime(item.due_at)}{item.round > 1 ? ` · Round ${item.round} after ${item.reopen_count} reopen${item.reopen_count === 1 ? '' : 's'}` : ''}</p>

    {item.open_clarification && <form className="notice-card mt-3 stack" onSubmit={sendAnswer}>
      <strong className="small">The department asks you:</strong>
      <p className="small">{item.open_clarification.question}</p>
      <TextareaField id="clarification-answer" label="Your reply" value={answer} onChange={event => setAnswer(event.target.value)} minLength={5} maxLength={1000} required/>
      <Button type="submit" busy={busy}>Send reply</Button>
    </form>}

    {item.status === 'RESOLVED' && <div className="notice-card mt-3">
      <strong className="small">Is it really fixed?</strong>
      <p className="small muted mt-1">{v.confirmed} confirmed · {v.disputed} disputed. The case closes at {v.close_threshold} confirmations and reopens at {v.reopen_threshold} disputes. Voting ends {dateTime(item.verification_closes_at)}.</p>
      {v.viewer_verdict && <p className="small mt-1">You answered: <strong>{v.viewer_verdict === 'CONFIRMED' ? 'Solved' : 'Not solved'}</strong></p>}
      {!v.viewer_is_affected && <p className="small muted mt-1">Only the reporter and residents who supported this issue can verify the fix.</p>}
      {v.viewer_can_verify && !verdict && <div className="flex gap-2 mt-2">
        <Button onClick={() => setVerdict('CONFIRMED')}>Yes, it is solved</Button>
        <Button variant="danger" onClick={() => setVerdict('DISPUTED')}>No, not solved</Button>
      </div>}
      {verdict && <form className="stack mt-2" onSubmit={sendVerdict}>
        <TextareaField id="verdict-reason" label={verdict === 'DISPUTED' ? 'What is still wrong? (required)' : 'Comment (optional)'} value={reason}
          onChange={event => setReason(event.target.value)} minLength={verdict === 'DISPUTED' ? 10 : 0} maxLength={1000} required={verdict === 'DISPUTED'}/>
        {verdict === 'DISPUTED' && <label className="field" htmlFor="verdict-photo"><span className="field-title">Photo of the problem (optional)</span>
          <input id="verdict-photo" className="input" type="file" accept="image/png,image/jpeg" onChange={event => setPhoto(event.target.files?.[0] ?? null)}/>
          <span className="hint">JPG or PNG up to 5 MB. Seen only by you, the department and coordinators.</span></label>}
        <div className="flex gap-2"><Button type="submit" busy={busy}>{verdict === 'CONFIRMED' ? 'Confirm fix' : 'Dispute fix'}</Button><Button type="button" variant="secondary" onClick={() => setVerdict(null)}>Cancel</Button></div>
      </form>}
    </div>}

    {item.evidence.length > 0 && <div className="mt-3 stack">
      <strong className="small">Department photos</strong>
      {item.evidence.map(row => <PrivatePhoto key={row.id} path={proofPath(row.id)} caption={row.caption} meta={evidenceMeta(row)}/>)}
    </div>}

    <ol className="stack mt-3">{item.timeline.map(event => <li key={event.sequence} className="notice-card">
      <div className="between"><strong className="small">{event.summary}</strong><span className="small muted">{dateTime(event.at)}</span></div>
      <span className="small muted">{event.status_label}</span>
    </li>)}</ol>
  </Card>;
}
