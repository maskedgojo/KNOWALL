'use client';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {useState, type FormEvent} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Button, Card, ErrorState, Field, Loading, PageHeading, SelectField, TextareaField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {civicApi} from '@/lib/civic-api';
import {CIVIC_CATEGORIES, CIVIC_SEVERITIES, SUPPORTABLE, type CivicCategory, type CivicPrivacy, type CivicSeverity, type SimilarIssue} from '@/lib/civic-types';
import {pretty} from '@/lib/format';
import {errorText, useLoad} from '@/lib/use-load';
import {CIVIC_NOTE, CivicMap, IssueCard, mapNotice} from './parts';

const STEPS = ['Location', 'Details', 'Check matches', 'Photos & submit'];

export default function ReportWizard() {
  const {access} = useAuth();
  const router = useRouter();
  const locality = useLoad(() => civicApi.locality(), []);
  const [step, setStep] = useState(0);
  const [point, setPoint] = useState<{lat: number; lon: number} | null>(null);
  const [addressHint, setAddressHint] = useState('');
  const [category, setCategory] = useState<CivicCategory>('ROAD_DAMAGE');
  const [severity, setSeverity] = useState<CivicSeverity>('MEDIUM');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [privacy, setPrivacy] = useState<CivicPrivacy>('ANONYMOUS');
  const [matches, setMatches] = useState<SimilarIssue[] | null>(null);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [shareResidents, setShareResidents] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [fields, setFields] = useState<Record<string, string>>({});

  if (!access?.permissions.includes('civic.issues.create')) return <PageHeading eyebrow="CIVIC ISSUES" title="Report an issue" description="Current resident access is required."/>;
  if (locality.loading) return <Loading label="Loading map…"/>;
  if (locality.error || !locality.value) return <ErrorState error={locality.error || 'Civic reporting is unavailable.'} onRetry={locality.refresh}/>;
  const area = locality.value.locality;
  const outside = point ? mapNotice(area, point.lat, point.lon) : '';
  const maxFiles = area.max_evidence_per_issue;

  function fail(cause: unknown) {
    setError(errorText(cause));
    setFields(cause instanceof ApiError ? cause.fields : {});
  }

  async function findMatches() {
    if (!point) return;
    setBusy(true); setError(''); setFields({});
    try {
      const result = await civicApi.similar({category, lat: point.lat, lon: point.lon, title});
      setMatches(result.similar); setStep(2);
    } catch (cause) {fail(cause);} finally {setBusy(false);}
  }

  /** Create the draft once; later visits update it so nothing is duplicated. */
  async function saveDraft(): Promise<string | null> {
    if (!point) return null;
    const body = {title, description, category, severity, latitude: point.lat, longitude: point.lon, address_hint: addressHint, privacy};
    if (draftId) {await civicApi.edit(draftId, body); return draftId;}
    const created = await civicApi.create({...body, save_as_draft: true});
    setDraftId(created.issue.id);
    return created.issue.id;
  }

  async function uploadAll(id: string) {
    for (const file of files.slice(0, maxFiles)) await civicApi.uploadEvidence(id, file, '', shareResidents ? 'RESIDENTS' : 'PRIVATE');
    setFiles([]);
  }

  async function finish(event: FormEvent, submit: boolean) {
    event.preventDefault();
    setBusy(true); setError(''); setFields({});
    try {
      const id = await saveDraft();
      if (!id) return;
      await uploadAll(id);
      if (submit) await civicApi.submit(id);
      router.push(`/civic/${id}`);
    } catch (cause) {fail(cause);} finally {setBusy(false);}
  }

  return <>
    <PageHeading eyebrow="CIVIC ISSUES" title="Report an issue" description="Pin the problem, describe it, check for existing reports, then submit."
      action={<Link className="btn btn-secondary" href="/civic">Back to issues</Link>}/>
    <Alert tone="info">{CIVIC_NOTE}</Alert>
    <ol className="flex gap-2 flex-wrap mt-4 small" aria-label="Progress">{STEPS.map((label, index) => <li key={label} className={index === step ? 'badge badge-success' : 'badge badge-neutral'}>{index + 1}. {label}</li>)}</ol>
    {error && <div className="mt-3"><Alert tone="warning">{error}{Object.entries(fields).map(([name, message]) => <div key={name} className="small">{pretty(name)}: {message}</div>)}</Alert></div>}

    {step === 0 && <Card className="mt-4">
      <h2 className="card-title">Where is the problem?</h2>
      <p className="small muted mt-1">Click the map to drop a pin, or type the coordinates. The dashed circle is the covered area.</p>
      <div className="mt-3"><CivicMap locality={area} picked={point} onPick={(lat, lon) => setPoint({lat, lon})}/></div>
      <div className="grid-2 mt-3">
        <Field id="civic-lat" label="Latitude" type="number" step="any" value={point?.lat ?? ''} onChange={event => setPoint({lat: Number(event.target.value), lon: point?.lon ?? area.center_lon})}/>
        <Field id="civic-lon" label="Longitude" type="number" step="any" value={point?.lon ?? ''} onChange={event => setPoint({lat: point?.lat ?? area.center_lat, lon: Number(event.target.value)})}/>
      </div>
      {outside && <div className="mt-3"><Alert tone="warning">{outside}</Alert></div>}
      <div className="mt-3"><Field id="civic-hint" label="Landmark (optional)" value={addressHint} maxLength={160} onChange={event => setAddressHint(event.target.value)} hint="For example: opposite the main gate."/></div>
      <div className="mt-4"><Button disabled={!point || !!outside} onClick={() => {setError(''); setStep(1);}}>Continue</Button></div>
    </Card>}

    {step === 1 && <Card className="mt-4">
      <h2 className="card-title">What is wrong?</h2>
      <form className="stack mt-3" onSubmit={event => {event.preventDefault(); void findMatches();}}>
        <SelectField id="civic-cat" label="Category" value={category} onChange={event => setCategory(event.target.value as CivicCategory)}>{CIVIC_CATEGORIES.map(item => <option key={item} value={item}>{pretty(item)}</option>)}</SelectField>
        <SelectField id="civic-sev" label="How serious is it?" value={severity} onChange={event => setSeverity(event.target.value as CivicSeverity)}>{CIVIC_SEVERITIES.map(item => <option key={item} value={item}>{pretty(item)}</option>)}</SelectField>
        <Field id="civic-title" label="Title" value={title} onChange={event => setTitle(event.target.value)} minLength={8} maxLength={160} required error={fields.title}/>
        <TextareaField id="civic-desc" label="Describe the problem" value={description} onChange={event => setDescription(event.target.value)} minLength={20} maxLength={2000} required/>
        {fields.description && <span className="field-error">{fields.description}</span>}
        <SelectField id="civic-privacy" label="Who can see your name?" value={privacy} onChange={event => setPrivacy(event.target.value as CivicPrivacy)}>
          <option value="ANONYMOUS">Hidden — other residents see “A resident”</option><option value="PUBLIC_NAME">Show my display name to residents</option>
        </SelectField>
        <p className="small muted">Do not include phone numbers or email addresses. Your contact details are never shown.</p>
        <div className="flex gap-2"><Button type="button" variant="secondary" onClick={() => setStep(0)}>Back</Button><Button type="submit" busy={busy}>Check for existing reports</Button></div>
      </form>
    </Card>}

    {step === 2 && <Card className="mt-4">
      <h2 className="card-title">Is it already reported?</h2>
      {matches && matches.length ? <>
        <p className="small muted mt-1">These open reports are close by and in the same category. Open one to support it instead of adding a duplicate. A coordinator decides final matches.</p>
        <div className="mt-3">{matches.map(item => <div key={item.id}><IssueCard issue={item}/><p className="small muted" style={{marginTop: -8, marginBottom: 12}}>{item.match.distance_m} m away · {Math.round(item.match.title_similarity * 100)}% similar wording · {SUPPORTABLE.includes(item.state) ? 'You can support it now' : 'Support opens after coordinator validation'}</p></div>)}</div>
      </> : <p className="small muted mt-2">No similar open reports nearby.</p>}
      <div className="flex gap-2 mt-4"><Button variant="secondary" onClick={() => setStep(1)}>Back</Button><Button onClick={() => setStep(3)}>{matches?.length ? 'None of these — continue' : 'Continue'}</Button></div>
    </Card>}

    {step === 3 && <Card className="mt-4">
      <h2 className="card-title">Add photos and submit</h2>
      <form className="stack mt-3" onSubmit={event => void finish(event, true)}>
        <label className="field" htmlFor="civic-files"><span className="field-title">Photos (up to {maxFiles}, JPG or PNG, 5 MB each)</span>
          <input id="civic-files" className="input" type="file" accept="image/png,image/jpeg" multiple onChange={event => setFiles(Array.from(event.target.files ?? []).slice(0, maxFiles))}/>
          <span className="hint">{files.length ? `${files.length} selected` : 'Photos are private to you and coordinators unless you choose to share them.'}</span>
        </label>
        <label className="small"><input type="checkbox" checked={shareResidents} onChange={event => setShareResidents(event.target.checked)}/> Let other residents see these photos (do not share photos showing people or private property)</label>
        <p className="small muted">Your report is checked by a coordinator before residents can support it.</p>
        <div className="flex gap-2 flex-wrap">
          <Button type="button" variant="secondary" onClick={() => setStep(2)}>Back</Button>
          <Button type="button" variant="secondary" busy={busy} onClick={event => void finish(event as unknown as FormEvent, false)}>Save as draft</Button>
          <Button type="submit" busy={busy}>Submit report</Button>
        </div>
      </form>
    </Card>}
  </>;
}
