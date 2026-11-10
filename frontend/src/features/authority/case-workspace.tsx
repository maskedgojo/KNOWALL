'use client';
import Link from 'next/link';
import {useState, type FormEvent} from 'react';
import {Alert, Button, Card, ErrorState, Field, Loading, PageHeading, SelectField, TextareaField} from '@/components/ui';
import {authorityAdminApi, authorityApi, disputePhotoPath, proofPath, reporterPhotoPath} from '@/lib/authority-api';
import {OPEN_STATUSES, TRANSFERABLE, WORKABLE, type EvidenceType} from '@/lib/authority-types';
import {pretty} from '@/lib/format';
import {errorText, useLoad} from '@/lib/use-load';
import {CaseBadge, PrivatePhoto, SimulationBanner, dateTime, evidenceMeta} from './parts';

type Panel = '' | 'transfer' | 'progress' | 'evidence' | 'resolve' | 'clarify' | 'escalate' | 'reopen' | 'close';

/** One case for the assigned simulated official or a coordinator. Flask re-checks scope on every action. */
export default function CaseWorkspace({id}: {id: string}) {
  const load = useLoad(() => authorityApi.get(id), [id]);
  const me = useLoad(() => authorityApi.me(), []);
  const departments = useLoad(() => authorityApi.departments(), []);
  const [panel, setPanel] = useState<Panel>('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [text, setText] = useState('');
  const [summary, setSummary] = useState('');
  const [due, setDue] = useState('');
  const [target, setTarget] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<EvidenceType>('RESOLUTION');

  async function run(action: () => Promise<unknown>, done: string) {
    setBusy(true); setError(''); setNotice('');
    try {await action(); setNotice(done); setPanel(''); setText(''); setSummary(''); setDue(''); setFile(null); load.refresh();}
    catch (cause) {setError(errorText(cause));} finally {setBusy(false);}
  }

  if (load.loading || me.loading) return <Loading label="Loading case…"/>;
  if (load.error || !load.value) return <ErrorState error={load.error || 'Case not found.'} onRetry={load.refresh}/>;
  const item = load.value.case;
  const officer = me.value?.officer ?? null;
  const assigned = !!officer && officer.department.id === item.department.id;
  const coordinator = !!me.value?.is_coordinator;
  const names = new Map((departments.value?.departments ?? []).map(row => [row.id, row.name]));
  const transferTargets = (departments.value?.departments ?? []).filter(row => row.id !== item.department.id && row.is_active);
  const proofCount = item.evidence.filter(row => row.round === item.round && row.evidence_type === 'RESOLUTION').length;
  const windowEnded = !!item.verification_closes_at && new Date(item.verification_closes_at) < new Date();

  function submit(event: FormEvent) {
    event.preventDefault();
    if (panel === 'transfer') void run(() => authorityApi.transfer(id, Number(target), text), 'Case transferred and logged.');
    if (panel === 'progress') void run(() => authorityApi.progress(id, {message: text, ...(summary ? {public_summary: summary} : {}), ...(due ? {revised_due_at: new Date(due).toISOString()} : {})}), 'Progress update published.');
    if (panel === 'evidence' && file) void run(() => authorityApi.uploadEvidence(id, file, kind, text), 'Photo added to the case.');
    if (panel === 'resolve') void run(() => authorityApi.resolve(id, text), 'Case marked resolved. Residents can now verify the fix.');
    if (panel === 'clarify') void run(() => authorityApi.requestClarification(id, text), 'Question sent to the reporter.');
    if (panel === 'escalate') void run(() => authorityAdminApi.escalate(id, text), 'Escalation recorded (simulated).');
    if (panel === 'reopen') void run(() => authorityAdminApi.reopen(id, text), 'Case reopened.');
    if (panel === 'close') void run(() => authorityAdminApi.close(id, text), 'Case closed by coordinator.');
  }

  const button = (name: Panel, label: string, show: boolean, variant: 'primary' | 'secondary' | 'danger' = 'secondary') =>
    show ? <Button key={name} variant={panel === name ? 'primary' : variant} onClick={() => {setPanel(panel === name ? '' : name); setError('');}}>{label}</Button> : null;

  return <>
    <PageHeading eyebrow={`AUTHORITY CASE ${item.authority_case_id} · DEMO`} title={item.title}
      description={`${pretty(item.category)} · ${pretty(item.severity)} · ${item.community_support} supporters · ${item.department.name}`}
      action={<Link className="btn btn-secondary" href="/authority">All cases</Link>}/>
    <SimulationBanner/>
    {error && <Alert tone="warning">{error}</Alert>}
    {notice && <Alert tone="success">{notice}</Alert>}

    <div className="grid-2 mt-4">
      <Card>
        <div className="between"><h2 className="card-title">Status</h2><CaseBadge status={item.status} overdue={item.is_overdue}/></div>
        <ul className="mt-3 small stack">
          <li>Department: <strong>{item.department.name}</strong> (simulated){item.owner_display_name ? ` · accepted by ${item.owner_display_name}` : ''}</li>
          <li>Due: {dateTime(item.due_at)}{item.is_overdue ? ' (overdue)' : ''}</li>
          <li>Round {item.round}{item.reopen_count ? ` · reopened ${item.reopen_count}×` : ''}</li>
          {item.status === 'RESOLVED' && <li>Verification: {item.tally.confirmed} confirmed, {item.tally.disputed} disputed · ends {dateTime(item.verification_closes_at)}</li>}
          {item.closure_basis && <li>Closed {dateTime(item.closed_at)} · {pretty(item.closure_basis)}</li>}
          <li>Civic issue: <Link className="text-link" href={`/civic/${item.civic_issue_id}`}>{item.civic_issue_id.slice(0, 8)}…</Link></li>
        </ul>
        <div className="flex gap-2 flex-wrap mt-4">
          {assigned && item.status === 'ROUTED' && <Button busy={busy} onClick={() => void run(() => authorityApi.acknowledge(id), 'Case accepted.')}>Accept case</Button>}
          {button('transfer', 'Transfer', (assigned || coordinator) && TRANSFERABLE.includes(item.status))}
          {button('progress', 'Post progress', assigned && WORKABLE.includes(item.status), 'primary')}
          {button('evidence', 'Add photo', assigned && WORKABLE.includes(item.status))}
          {button('clarify', 'Ask reporter', assigned && WORKABLE.includes(item.status))}
          {button('resolve', 'Mark resolved', assigned && item.status === 'IN_PROGRESS', 'primary')}
          {button('escalate', 'Escalate', coordinator && OPEN_STATUSES.includes(item.status), 'danger')}
          {button('reopen', 'Reopen', coordinator && item.status === 'RESOLVED', 'danger')}
          {button('close', 'Close (no votes)', coordinator && item.status === 'RESOLVED' && windowEnded && !item.tally.confirmed && !item.tally.disputed)}
        </div>
        {panel && <form className="stack mt-4" onSubmit={submit}>
          {panel === 'transfer' && <SelectField id="transfer-to" label="Move to department" value={target} onChange={event => setTarget(event.target.value)} required>
            <option value="">Choose…</option>{transferTargets.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</SelectField>}
          {panel === 'evidence' && <>
            <SelectField id="evidence-kind" label="Photo type" value={kind} onChange={event => setKind(event.target.value as EvidenceType)}>
              <option value="RESOLUTION">Resolution proof</option><option value="PROGRESS">Progress</option></SelectField>
            <label className="field" htmlFor="evidence-file"><span className="field-title">Photo</span>
              <input id="evidence-file" className="input" type="file" accept="image/png,image/jpeg" onChange={event => setFile(event.target.files?.[0] ?? null)} required/>
              <span className="hint">JPG or PNG up to 5 MB. Photos cannot be removed once added.</span></label>
          </>}
          {panel === 'escalate' && <Alert tone="info">This records a simulated escalation inside KNOWALL. It is not sent to any real government body.</Alert>}
          {panel === 'resolve' && item.department.requires_resolution_proof && proofCount === 0 && <Alert tone="warning">Add a resolution proof photo first. Resolution without proof is blocked.</Alert>}
          <TextareaField id="panel-text" value={text} onChange={event => setText(event.target.value)}
            label={{transfer: 'Reason for transfer', progress: 'Update (staff)', evidence: 'Caption (optional)', resolve: 'What was fixed?', clarify: 'Question for the reporter', escalate: 'Escalation reason', reopen: 'Reason for reopening', close: 'Reason for closing', '': ''}[panel]}
            minLength={panel === 'evidence' ? 0 : 5} maxLength={1000} required={panel !== 'evidence'}/>
          {panel === 'progress' && <>
            <Field id="public-summary" label="Resident-facing summary (optional)" value={summary} onChange={event => setSummary(event.target.value)} maxLength={300}/>
            <Field id="revised-due" label="Revised target date (optional)" type="datetime-local" value={due} onChange={event => setDue(event.target.value)}/>
          </>}
          <div className="flex gap-2"><Button type="submit" busy={busy}>Submit</Button><Button type="button" variant="secondary" onClick={() => setPanel('')}>Cancel</Button></div>
        </form>}
      </Card>

      <Card>
        <h2 className="card-title">Reported issue (from Module 5)</h2>
        <p className="mt-3">{item.issue.summary}</p>
        {item.issue.location.address_hint && <p className="small muted mt-2">Near: {item.issue.location.address_hint}</p>}
        <p className="small muted">{item.issue.location.latitude?.toFixed(5)}, {item.issue.location.longitude?.toFixed(5)} · validated {dateTime(item.issue.validated_at)}</p>
        {item.issue.merged_duplicate_issue_ids.length > 0 && <p className="small mt-1">{item.issue.merged_duplicate_issue_ids.length} duplicate report(s) merged into this issue.</p>}
        <div className="stack mt-3">{item.issue.evidence.map(row => <PrivatePhoto key={row.evidence_id} path={reporterPhotoPath(id, row.evidence_id)} caption={row.caption} meta="Reporter photo"/>)}</div>
      </Card>

      <Card>
        <h2 className="card-title">Department photos ({item.evidence.length})</h2>
        <div className="stack mt-3">{item.evidence.length ? item.evidence.map(row => <PrivatePhoto key={row.id} path={proofPath(row.id)} caption={row.caption} meta={evidenceMeta(row)}/>) : <p className="small muted">No photos yet.</p>}</div>
      </Card>

      <Card>
        <h2 className="card-title">Resident verification</h2>
        {item.verifications.length === 0 ? <p className="small muted mt-3">No verdicts yet.</p> : <ul className="stack mt-3">{item.verifications.map(row => <li key={row.id} className="notice-card">
          <div className="between"><strong className="small">{row.resident_display_name} · {row.verdict === 'CONFIRMED' ? 'Solved' : 'Not solved'}</strong><span className="small muted">Round {row.round} · {dateTime(row.at)}</span></div>
          {row.reason && <p className="small mt-1">{row.reason}</p>}
          {row.has_photo && <PrivatePhoto path={disputePhotoPath(row.id)} caption="Resident's photo" meta="Dispute evidence"/>}
        </li>)}</ul>}
        {item.clarifications.length > 0 && <><h3 className="card-title mt-4">Clarifications</h3><ul className="stack mt-2">{item.clarifications.map(row => <li key={row.id} className="notice-card small">
          <strong>Q:</strong> {row.question}<br/><strong>A:</strong> {row.response ?? <em>Waiting for the reporter</em>}
        </li>)}</ul></>}
      </Card>

      <Card>
        <h2 className="card-title">Escalations and transfers</h2>
        <ul className="stack mt-3 small">
          {item.escalations.map(row => <li key={row.id} className="notice-card">{pretty(row.kind)} → {row.target_label} · {pretty(row.outcome)} · {dateTime(row.triggered_at)}<br/>{row.reason}</li>)}
          {item.transfers.map((row, index) => <li key={index} className="notice-card">Transfer: {names.get(row.from_department_id) ?? row.from_department_id} → {names.get(row.to_department_id) ?? row.to_department_id} · {dateTime(row.at)}<br/>{row.reason}</li>)}
          {!item.escalations.length && !item.transfers.length && <li className="muted">None.</li>}
        </ul>
      </Card>

      <Card>
        <h2 className="card-title">History (append-only)</h2>
        <ol className="stack mt-3">{item.events.map(row => <li key={row.sequence} className="notice-card">
          <div className="between"><strong className="small">#{row.sequence} {pretty(row.action)}</strong><span className="small muted">{dateTime(row.at)}</span></div>
          <div className="small muted">{row.from_status ? `${pretty(row.from_status)} → ` : ''}{pretty(row.to_status)} · {pretty(row.actor_kind)}{row.actor_display_name ? ` · ${row.actor_display_name}` : ''}</div>
          {row.reason && <p className="small mt-1">{row.reason}</p>}
        </li>)}</ol>
      </Card>
    </div>
  </>;
}
