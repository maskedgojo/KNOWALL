'use client';
import Link from 'next/link';
import {useState, type FormEvent} from 'react';
import {Alert, Badge, Button, Card, ErrorState, Field, Loading, PageHeading, SelectField, TextareaField} from '@/components/ui';
import {civicApi} from '@/lib/civic-api';
import {CONCERN_TYPES, EVIDENCE_EDITABLE, REPORTER_EDITABLE, REPORTER_WITHDRAWABLE, SUPPORTABLE, type ConcernType, type TimelineEvent} from '@/lib/civic-types';
import {pretty, shortDate} from '@/lib/format';
import {errorText, useLoad} from '@/lib/use-load';
import {CivicMap, EvidencePhoto, PriorityCard} from './parts';
import CaseTracker from '@/features/authority/case-tracker';

function eventText(event: TimelineEvent) {
  if (event.type === 'ROUTED') return 'Handed off for routing to the authority workspace (demonstration)';
  if (event.type === 'AUTHORITY_ACKNOWLEDGED') return `Authority case ${event.authority_case_id} opened (demonstration)`;
  return event.to_state ? pretty(event.to_state) : '';
}

export default function CivicIssueDetail({id}: {id: string}) {
  const issueLoad = useLoad(() => civicApi.get(id), [id]);
  const timeline = useLoad(() => civicApi.timeline(id), [id]);
  const locality = useLoad(() => civicApi.locality(), []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [hint, setHint] = useState('');
  const [note, setNote] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [concernType, setConcernType] = useState<ConcernType>('ABUSIVE');
  const [concern, setConcern] = useState('');
  const [reporting, setReporting] = useState(false);

  function refresh() {issueLoad.refresh(); timeline.refresh();}
  async function run(action: () => Promise<unknown>, done?: string) {
    setBusy(true); setError(''); setNotice('');
    try {await action(); if (done) setNotice(done); refresh();} catch (cause) {setError(errorText(cause));} finally {setBusy(false);}
  }

  if (issueLoad.loading) return <Loading label="Loading issue…"/>;
  if (issueLoad.error || !issueLoad.value) return <ErrorState error={issueLoad.error || 'Issue not found.'} onRetry={issueLoad.refresh}/>;
  const issue = issueLoad.value.issue;
  const mine = issue.viewer_is_reporter;
  const maxFiles = locality.value?.locality.max_evidence_per_issue ?? 5;
  const canSupport = !mine && SUPPORTABLE.includes(issue.state);
  const canEvidence = mine && EVIDENCE_EDITABLE.includes(issue.state);

  function startEdit() {setTitle(issue.title); setDescription(issue.description); setHint(issue.address_hint); setEditing(true);}
  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    await run(async () => {await civicApi.edit(id, {title, description, address_hint: hint}); setEditing(false);}, 'Changes saved.');
  }
  async function sendConcern(event: FormEvent) {
    event.preventDefault();
    await run(async () => {await civicApi.report(id, concernType, concern); setConcern(''); setReporting(false);}, 'Thank you. A coordinator will review your concern.');
  }
  async function addPhotos(event: FormEvent) {
    event.preventDefault();
    await run(async () => {for (const file of files) await civicApi.uploadEvidence(id, file); setFiles([]);}, 'Photos added.');
  }

  return <>
    <PageHeading eyebrow={`CIVIC ISSUE · ${pretty(issue.category).toUpperCase()}`} title={issue.title}
      description={`${pretty(issue.severity)} severity · reported by ${issue.reporter_display_name} · ${shortDate(issue.created_at)}`}
      action={<Link className="btn btn-secondary" href="/civic">All issues</Link>}/>
    {error && <Alert tone="warning">{error}</Alert>}
    {notice && <Alert tone="success">{notice}</Alert>}
    {issue.state === 'MERGED' && issue.canonical_issue_id && <Alert tone="info">A coordinator linked this report to an existing one. Your report and its history are kept. <Link className="text-link" href={`/civic/${issue.canonical_issue_id}`}>Open the main report</Link></Alert>}
    {issue.state === 'NEEDS_INFO' && mine && <Alert tone="warning">A coordinator asked for more information. See the progress list, edit your report, then submit it again.</Alert>}

    <div className="grid-2 mt-4">
      <Card>
        <div className="between"><h2 className="card-title">Report</h2><Badge value={issue.state}/></div>
        {editing ? <form className="stack mt-3" onSubmit={saveEdit}>
          <Field id="edit-title" label="Title" value={title} onChange={event => setTitle(event.target.value)} minLength={8} maxLength={160} required/>
          <TextareaField id="edit-desc" label="Description" value={description} onChange={event => setDescription(event.target.value)} minLength={20} maxLength={2000} required/>
          <Field id="edit-hint" label="Landmark" value={hint} onChange={event => setHint(event.target.value)} maxLength={160}/>
          <div className="flex gap-2"><Button type="submit" busy={busy}>Save</Button><Button type="button" variant="secondary" onClick={() => setEditing(false)}>Cancel</Button></div>
        </form> : <>
          <p className="mt-3">{issue.description}</p>
          {issue.address_hint && <p className="mt-2 small muted">Near: {issue.address_hint}</p>}
        </>}

        {canSupport && <div className="mt-4 flex gap-2 flex-wrap items-center">
          {issue.viewer_has_supported
            ? <><Badge value="SUPPORTED"/><Button variant="secondary" busy={busy} onClick={() => void run(() => civicApi.unsupport(id))}>Withdraw my support</Button></>
            : <Button busy={busy} onClick={() => void run(() => civicApi.support(id), 'Thanks for supporting this issue.')}>Support this issue</Button>}
          <span className="small muted">{issue.support_count} supporter{issue.support_count === 1 ? '' : 's'}</span>
        </div>}
        {!canSupport && !mine && issue.state !== 'MERGED' && <p className="mt-4 small muted">{issue.state === 'SUBMITTED' || issue.state === 'UNDER_REVIEW' ? 'Support opens once a coordinator validates this report.' : `${issue.support_count} supporter${issue.support_count === 1 ? '' : 's'}`}</p>}
        {mine && <p className="mt-4 small muted">{issue.support_count} neighbour{issue.support_count === 1 ? '' : 's'} supporting your report.</p>}

        {mine && !editing && <div className="mt-4 stack">
          <div className="flex gap-2 flex-wrap">
            {REPORTER_EDITABLE.includes(issue.state) && <Button variant="secondary" onClick={startEdit}>Edit</Button>}
            {REPORTER_EDITABLE.includes(issue.state) && <Button busy={busy} onClick={() => void run(() => civicApi.submit(id, note || undefined), 'Submitted for review.')}>{issue.state === 'DRAFT' ? 'Submit for review' : 'Resubmit'}</Button>}
            {REPORTER_WITHDRAWABLE.includes(issue.state) && <Button variant="danger" busy={busy} onClick={() => void run(() => civicApi.withdraw(id), 'Report withdrawn.')}>Withdraw</Button>}
          </div>
          {issue.state === 'NEEDS_INFO' && <Field id="resubmit-note" label="Note to the coordinator (optional)" value={note} onChange={event => setNote(event.target.value)} maxLength={500}/>}
        </div>}
      </Card>

      <Card>
        <h2 className="card-title">Location</h2>
        <div className="mt-3">{locality.value && <CivicMap locality={locality.value.locality} selectedId={issue.id} pins={[{id: issue.id, latitude: issue.latitude, longitude: issue.longitude, severity: issue.severity, label: issue.title}]}/>}</div>
        <p className="mt-2 small muted">{issue.latitude.toFixed(5)}, {issue.longitude.toFixed(5)}</p>
      </Card>

      <Card>
        <h2 className="card-title">Photos ({issue.evidence_count})</h2>
        <div className="mt-3 stack">{issue.evidence.length ? issue.evidence.map(item => <EvidencePhoto key={item.id} item={item}
          onRemove={canEvidence && mine ? () => void run(() => civicApi.removeEvidence(id, item.id), 'Photo removed.') : undefined}/>) : <p className="small muted">No photos visible to you.</p>}</div>
        {canEvidence && issue.evidence.length < maxFiles && <form className="stack mt-3" onSubmit={addPhotos}>
          <label className="field" htmlFor="civic-more"><span className="field-title">Add photos</span>
            <input id="civic-more" className="input" type="file" accept="image/png,image/jpeg" multiple onChange={event => setFiles(Array.from(event.target.files ?? []).slice(0, maxFiles - issue.evidence.length))}/>
            <span className="hint">JPG or PNG up to 5 MB. Private to you and coordinators.</span></label>
          <Button type="submit" variant="secondary" busy={busy} disabled={!files.length}>Upload</Button>
        </form>}
      </Card>

      <Card>
        <h2 className="card-title">Progress</h2>
        <div className="mt-3">{timeline.loading ? <Loading label="Loading progress…"/> : timeline.error || !timeline.value ? <ErrorState error={timeline.error} onRetry={timeline.refresh}/> : <>
          <ol className="stack">{timeline.value.events.map((event, index) => <li key={index} className="notice-card">
            <div className="between"><strong className="small">{eventText(event)}</strong><span className="small muted">{shortDate(event.at)}</span></div>
            {event.reason && <p className="mt-1 small">{event.reason}</p>}
          </li>)}</ol>
          {issue.handoff && <p className="mt-3 small">Handoff: <Badge value={issue.handoff.routing_status}/>{issue.handoff.authority_case_id && <> case <strong>{issue.handoff.authority_case_id}</strong></>}</p>}
          <p className="mt-2 small muted">After handoff, the authority workspace owns the case status shown here.</p>
        </>}</div>
      </Card>

      {issue.authoritative_status && <CaseTracker issueId={id} onChange={refresh}/>}

      <PriorityCard priority={issue.priority}/>

      {issue.readiness && (mine || issue.state === 'VALIDATED') && <Card>
        <h2 className="card-title">Ready for routing?</h2>
        {issue.readiness.unmet.length ? <ul className="mt-2 small">{issue.readiness.unmet.map(item => <li key={item}>{item}</li>)}</ul> : <p className="mt-2 small">All criteria met. A coordinator can hand this case on.</p>}
      </Card>}

      {!mine && issue.state !== 'MERGED' && <Card>
        <h2 className="card-title">Something wrong with this report?</h2>
        {reporting ? <form className="stack mt-3" onSubmit={sendConcern}>
          <SelectField id="concern-type" label="Concern" value={concernType} onChange={event => setConcernType(event.target.value as ConcernType)}>{CONCERN_TYPES.map(item => <option key={item} value={item}>{pretty(item)}</option>)}</SelectField>
          <TextareaField id="concern" label="What should a coordinator look at?" value={concern} onChange={event => setConcern(event.target.value)} minLength={10} maxLength={1000} required/>
          <div className="flex gap-2"><Button type="submit" busy={busy}>Send concern</Button><Button type="button" variant="secondary" onClick={() => setReporting(false)}>Cancel</Button></div>
        </form> : <div className="mt-2"><Button variant="secondary" onClick={() => setReporting(true)}>Raise a concern</Button></div>}
      </Card>}
    </div>
  </>;
}
