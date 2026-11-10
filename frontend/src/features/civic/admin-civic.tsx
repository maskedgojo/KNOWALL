'use client';
import Link from 'next/link';
import {useState, type FormEvent} from 'react';
import {Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, SelectField, TextareaField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {civicAdminApi, civicApi} from '@/lib/civic-api';
import {CIVIC_SEVERITIES, type CivicIssue, type CivicReport, type CivicSeverity, type CivicState, type ReportDisposition, type SimilarIssue} from '@/lib/civic-types';
import {pretty, shortDate} from '@/lib/format';
import {errorText, useLoad} from '@/lib/use-load';
import {EvidencePhoto} from './parts';

type Action = 'review' | 'validate' | 'needs-info' | 'reject' | 'merge' | 'route' | 'acknowledge';

/** Actions a coordinator may take per state. Flask enforces the real lifecycle. */
const ACTIONS: Partial<Record<CivicState, Action[]>> = {
  SUBMITTED: ['review', 'validate', 'needs-info', 'reject', 'merge'],
  UNDER_REVIEW: ['validate', 'needs-info', 'reject', 'merge'],
  NEEDS_INFO: ['reject'],
  VALIDATED: ['route', 'needs-info', 'reject', 'merge'],
  READY_FOR_ROUTING: ['acknowledge'],
};
const LABEL: Record<Action, string> = {
  review: 'Start review', validate: 'Validate', 'needs-info': 'Ask for more information', reject: 'Reject', merge: 'Merge into another report',
  route: 'Hand off for routing', acknowledge: 'Record authority case (demo)',
};
const QUEUE: CivicState[] = ['SUBMITTED', 'UNDER_REVIEW', 'NEEDS_INFO', 'VALIDATED', 'READY_FOR_ROUTING'];

function IssueRow({issue, required, onSaved}: {issue: CivicIssue; required: number; onSaved: () => void}) {
  const actions = ACTIONS[issue.state] ?? [];
  const [action, setAction] = useState<Action | ''>(actions[0] ?? '');
  const [reason, setReason] = useState('');
  const [severity, setSeverity] = useState<CivicSeverity | ''>('');
  const [canonical, setCanonical] = useState('');
  const [candidates, setCandidates] = useState<SimilarIssue[]>([]);
  const [far, setFar] = useState(false);
  const [confirmFar, setConfirmFar] = useState(false);
  const [caseId, setCaseId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);

  async function pick(next: Action) {
    setAction(next); setError(''); setFar(false);
    if (next === 'merge') {
      try {setCandidates((await civicApi.similar({category: issue.category, lat: issue.latitude, lon: issue.longitude, title: issue.title, excludeId: issue.id})).similar);}
      catch (cause) {setError(errorText(cause));}
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!action) return;
    setBusy(true); setError('');
    try {
      if (action === 'review') await civicAdminApi.review(issue.id);
      if (action === 'validate') await civicAdminApi.validate(issue.id, {note: reason || undefined, severity: severity || undefined});
      if (action === 'needs-info') await civicAdminApi.needsInfo(issue.id, reason);
      if (action === 'reject') await civicAdminApi.reject(issue.id, reason);
      if (action === 'merge') await civicAdminApi.merge(issue.id, {canonical_issue_id: canonical, reason, acknowledge_distance: confirmFar || undefined});
      if (action === 'route') await civicAdminApi.route(issue.id);
      if (action === 'acknowledge') await civicAdminApi.acknowledge(issue.id, caseId);
      setReason(''); setFar(false); setConfirmFar(false); onSaved();
    } catch (cause) {
      setError(errorText(cause));
      if (cause instanceof ApiError && cause.code === 'LOCATIONS_TOO_FAR') setFar(true);
      if (cause instanceof ApiError && cause.code === 'NOT_READY_FOR_ROUTING') setError(`${cause.message} ${Object.values(cause.fields).join(' ')}`);
    } finally {setBusy(false);}
  }

  const needsReason = action === 'needs-info' || action === 'reject' || action === 'merge';
  return <div className="notice-card mb-3">
    <div className="between"><Link href={`/civic/${issue.id}`}><strong>{issue.title}</strong></Link><Badge value={issue.state}/></div>
    <div className="mt-1 small muted">{pretty(issue.category)} · {pretty(issue.severity)} · {issue.support_count}/{required} supporters · {issue.evidence_count} photo{issue.evidence_count === 1 ? '' : 's'} · {issue.reporter_display_name} · {shortDate(issue.created_at)}</div>
    <p className="mt-1 small">{issue.description}</p>
    <button className="text-link small mt-1" onClick={() => setOpen(!open)}>{open ? 'Hide photos' : `Photos (${issue.evidence_count})`}</button>
    {open && <div className="mt-2 stack">{issue.evidence.length ? issue.evidence.map(item => <EvidencePhoto key={item.id} item={item}
      extra={<button type="button" className="text-link small" onClick={() => void civicAdminApi.setEvidenceVisibility(item.id, item.visibility === 'PRIVATE' ? 'RESIDENTS' : 'PRIVATE').then(onSaved).catch(cause => setError(errorText(cause)))}>{item.visibility === 'PRIVATE' ? 'Share with residents' : 'Make private'}</button>}/>) : <p className="small muted">No photos.</p>}</div>}
    {actions.length > 0 && <form className="stack mt-3" onSubmit={submit}>
      {error && <Alert tone="warning">{error}</Alert>}
      <SelectField id={`act-${issue.id}`} label="Action" value={action} onChange={event => void pick(event.target.value as Action)}>{actions.map(item => <option key={item} value={item}>{LABEL[item]}</option>)}</SelectField>
      {action === 'validate' && <>
        <SelectField id={`sev-${issue.id}`} label="Adjust severity (optional)" value={severity} onChange={event => setSeverity(event.target.value as CivicSeverity | '')}><option value="">Keep {pretty(issue.severity)}</option>{CIVIC_SEVERITIES.map(item => <option key={item} value={item}>{pretty(item)}</option>)}</SelectField>
        <Field id={`note-${issue.id}`} label="Note to the reporter (optional)" value={reason} onChange={event => setReason(event.target.value)} maxLength={500}/>
      </>}
      {needsReason && <TextareaField id={`why-${issue.id}`} label={action === 'merge' ? 'Why is it the same issue?' : 'Reason (the reporter will see this)'} value={reason} onChange={event => setReason(event.target.value)} minLength={5} maxLength={500} required/>}
      {action === 'merge' && <>
        <SelectField id={`can-${issue.id}`} label="Main report" value={canonical} onChange={event => setCanonical(event.target.value)} required>
          <option value="">{candidates.length ? 'Choose a nearby report' : 'No nearby candidates — paste an id below'}</option>
          {candidates.map(item => <option key={item.id} value={item.id}>{item.title} · {item.match.distance_m} m</option>)}</SelectField>
        <Field id={`canid-${issue.id}`} label="Or paste a report id" value={canonical} onChange={event => setCanonical(event.target.value)}/>
        {far && <label className="small"><input type="checkbox" checked={confirmFar} onChange={event => setConfirmFar(event.target.checked)}/> These are far apart but describe the same problem (for example, one long stretch of road)</label>}
      </>}
      {action === 'route' && <p className="small muted">Needs {required} supporters and at least one photo. The server checks this and returns what is missing.</p>}
      {action === 'acknowledge' && <Field id={`case-${issue.id}`} label="Authority case id (demonstration)" value={caseId} onChange={event => setCaseId(event.target.value)} minLength={3} maxLength={64} required hint="Normally recorded automatically by the authority workspace."/>}
      <div><Button type="submit" busy={busy} disabled={!action}>Apply</Button></div>
    </form>}
    {issue.state === 'READY_FOR_ROUTING' && issue.handoff && <p className="mt-2 small">Handoff <Badge value={issue.handoff.routing_status}/> {issue.handoff.authority_case_id ?? ''}</p>}
  </div>;
}

function ReportRow({report, onSaved}: {report: CivicReport; onSaved: () => void}) {
  const [disposition, setDisposition] = useState<ReportDisposition>('DISMISSED');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function resolve(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {await civicAdminApi.resolveReport(report.id, disposition, note); onSaved();} catch (cause) {setError(errorText(cause));} finally {setBusy(false);}
  }
  return <form className="notice-card mb-3 stack" onSubmit={resolve}>
    <div className="between"><strong className="small">{pretty(report.concern_type)}</strong><Link className="text-link small" href={`/civic/${report.issue_id}`}>Open issue</Link></div>
    <p className="small">{report.concern}</p>
    {error && <Alert tone="warning">{error}</Alert>}
    <SelectField id={`disp-${report.id}`} label="Decision" value={disposition} onChange={event => setDisposition(event.target.value as ReportDisposition)}>
      <option value="DISMISSED">Dismiss — no problem found</option><option value="REDACTED">Redact the description and hide photos</option>
      <option value="CORRECTION_REQUESTED">Ask the reporter to correct it</option><option value="REMOVED">Remove the report</option>
    </SelectField>
    <Field id={`rnote-${report.id}`} label="Note (kept in the audit trail)" value={note} onChange={event => setNote(event.target.value)} minLength={5} maxLength={500} required/>
    <div><Button type="submit" busy={busy}>Resolve</Button></div>
  </form>;
}

export default function AdminCivic() {
  const [state, setState] = useState<CivicState>('SUBMITTED');
  const locality = useLoad(() => civicApi.locality(), []);
  const queue = useLoad(() => civicAdminApi.queue(state), [state]);
  const reports = useLoad(() => civicAdminApi.reports('OPEN'), []);
  const required = locality.value?.locality.required_supporters ?? 3;
  const refresh = () => {queue.refresh(); reports.refresh();};
  return <>
    <PageHeading eyebrow="CIVIC ISSUES" title="Review civic issues" description="Validate reports, link duplicates, handle concerns and prepare cases for routing. Authority accounts in this version are simulated demonstration data."/>
    <div className="grid-2">
      <Card>
        <div className="between"><h2 className="card-title">Queue</h2>
          <SelectField id="queue-state" label="State" value={state} onChange={event => setState(event.target.value as CivicState)}>{QUEUE.map(item => <option key={item} value={item}>{pretty(item)}</option>)}</SelectField></div>
        <div className="mt-3">{queue.loading ? <Loading label="Loading queue…"/> : queue.error ? <ErrorState error={queue.error} onRetry={queue.refresh}/>
          : queue.value?.issues.length ? queue.value.issues.map(issue => <IssueRow key={issue.id} issue={issue} required={required} onSaved={refresh}/>)
            : <EmptyState title="Nothing in this state" description="New reports appear under Submitted."/>}</div>
      </Card>
      <Card>
        <h2 className="card-title">Open concerns</h2>
        <div className="mt-3">{reports.loading ? <Loading label="Loading concerns…"/> : reports.error ? <ErrorState error={reports.error} onRetry={reports.refresh}/>
          : reports.value?.reports.length ? reports.value.reports.map(report => <ReportRow key={report.id} report={report} onSaved={refresh}/>)
            : <EmptyState title="No open concerns" description="Residents' abuse or privacy reports appear here."/>}</div>
      </Card>
    </div>
  </>;
}
