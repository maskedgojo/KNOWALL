'use client';
import Link from 'next/link';
import {useState, type FormEvent} from 'react';
import {Alert, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, SelectField} from '@/components/ui';
import {authorityAdminApi, authorityApi} from '@/lib/authority-api';
import {pretty, shortDate} from '@/lib/format';
import {errorText, useLoad} from '@/lib/use-load';
import {CaseBadge, SimulationBanner, dateTime} from './parts';

/** Coordinator workspace: take Module 5 handoffs in, manage simulated departments and officials, run the sweep. */
export default function AdminAuthority() {
  const queue = useLoad(() => authorityAdminApi.intakeQueue(), []);
  const departments = useLoad(() => authorityApi.departments(), []);
  const cases = useLoad(() => authorityApi.list(), []);
  const [choice, setChoice] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [email, setEmail] = useState('');
  const [department, setDepartment] = useState('');
  const [title, setTitle] = useState('Demo official');

  function refresh() {queue.refresh(); departments.refresh(); cases.refresh();}
  async function run(action: () => Promise<string>) {
    setBusy(true); setError(''); setNotice('');
    try {setNotice(await action()); refresh();} catch (cause) {setError(errorText(cause));} finally {setBusy(false);}
  }
  function assign(event: FormEvent) {
    event.preventDefault();
    void run(async () => {await authorityAdminApi.assignOfficer(email, Number(department), title); setEmail(''); return 'Official assigned to the department.';});
  }
  const depts = departments.value?.departments ?? [];

  return <>
    <PageHeading eyebrow="ADMINISTRATION · MODULE 6" title="Authority cases (simulated)"
      description="Take validated civic issues in, route them to a demo department and oversee the case lifecycle."
      action={<Link className="btn btn-secondary" href="/admin/analytics">Civic analytics</Link>}/>
    <SimulationBanner/>
    {error && <Alert tone="warning">{error}</Alert>}
    {notice && <Alert tone="success">{notice}</Alert>}

    <div className="grid-2 mt-4">
      <Card>
        <h2 className="card-title">Intake queue</h2>
        <p className="small muted">Issues Module 5 handed off, waiting for an authority case.</p>
        <div className="mt-3">{queue.loading ? <Loading/> : queue.error || !queue.value ? <ErrorState error={queue.error} onRetry={queue.refresh}/>
          : queue.value.handoffs.length === 0 ? <EmptyState title="Nothing to take in" description="Route a validated issue from Civic issues first."/>
          : <div className="stack">{queue.value.handoffs.map(item => <div key={item.canonical_issue_id} className="notice-card stack">
            <div className="between"><Link href={`/civic/${item.canonical_issue_id}`}><strong>{item.title}</strong></Link><span className="small muted">{shortDate(item.routed_at)}</span></div>
            <span className="small muted">{pretty(item.category)} · {pretty(item.severity)} · {item.community_support} supporters</span>
            <SelectField id={`dept-${item.canonical_issue_id}`} label="Department" value={choice[item.canonical_issue_id] ?? ''}
              onChange={event => setChoice({...choice, [item.canonical_issue_id]: event.target.value})}>
              <option value="">{item.suggested_department ? `Suggested: ${item.suggested_department.name}` : 'No department covers this category'}</option>
              {depts.filter(row => row.is_active).map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
            </SelectField>
            <Button busy={busy} onClick={() => void run(async () => {
              const picked = choice[item.canonical_issue_id];
              const result = await authorityAdminApi.intake(item.canonical_issue_id, picked ? Number(picked) : undefined);
              return `Case ${result.case.authority_case_id} opened with ${result.case.department.name}.`;
            })}>Open authority case</Button>
          </div>)}</div>}</div>
      </Card>

      <Card>
        <div className="between"><h2 className="card-title">Cases</h2>
          <Button variant="secondary" busy={busy} onClick={() => void run(async () => {
            const {report} = await authorityAdminApi.sweep();
            return `Sweep done: ${report.escalated} escalated, ${report.closed} closed, ${report.reopened} reopened, ${report.awaiting_coordinator} awaiting you.`;
          })}>Run overdue check</Button></div>
        <div className="mt-3">{cases.loading ? <Loading/> : cases.error || !cases.value ? <ErrorState error={cases.error} onRetry={cases.refresh}/>
          : cases.value.cases.length === 0 ? <p className="small muted">No cases yet.</p>
          : <div className="stack">{cases.value.cases.map(item => <div key={item.case_id} className="notice-card">
            <div className="between"><Link href={`/authority/cases/${item.case_id}`}><strong>{item.authority_case_id} · {item.title}</strong></Link><CaseBadge status={item.status} overdue={item.is_overdue}/></div>
            <span className="small muted">{item.department.name} · due {dateTime(item.due_at)}</span>
          </div>)}</div>}</div>
      </Card>

      <Card>
        <h2 className="card-title">Simulated departments</h2>
        <div className="mt-3">{departments.loading ? <Loading/> : departments.error ? <ErrorState error={departments.error} onRetry={departments.refresh}/>
          : <div className="stack">{depts.map(row => <div key={row.id} className="notice-card">
            <div className="between"><strong>{row.name}</strong><span className="badge badge-warning">Demo</span></div>
            <p className="small muted">{row.jurisdiction?.map(rule => pretty(rule.category)).join(', ') || 'No categories'}{row.escalation_rule ? ` · SLA ${row.escalation_rule.threshold_hours} h → ${row.escalation_rule.target_label}` : ''}</p>
            <ul className="small mt-1">{row.officers?.map(person => <li key={person.id} className="between">
              <span>{person.display_name} · {person.title}</span>
              <button type="button" className="text-link small" onClick={() => void run(async () => {await authorityAdminApi.revokeOfficer(person.id); return 'Official access revoked.';})}>Revoke</button>
            </li>)}</ul>
          </div>)}</div>}</div>
      </Card>

      <Card>
        <h2 className="card-title">Assign a simulated official</h2>
        <form className="stack mt-3" onSubmit={assign}>
          <Field id="officer-email" label="Account email" type="email" value={email} onChange={event => setEmail(event.target.value)} required/>
          <SelectField id="officer-dept" label="Department" value={department} onChange={event => setDepartment(event.target.value)} required>
            <option value="">Choose…</option>{depts.filter(row => row.is_active).map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
          </SelectField>
          <Field id="officer-title" label="Title" value={title} onChange={event => setTitle(event.target.value)} minLength={3} maxLength={120} required/>
          <Button type="submit" busy={busy}>Assign</Button>
          <p className="small muted">The account must be active and email-verified. It can act only on its department&apos;s cases.</p>
        </form>
      </Card>
    </div>
  </>;
}
