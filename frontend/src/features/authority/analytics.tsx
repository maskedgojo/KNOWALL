'use client';
import Link from 'next/link';
import {Alert, Card, ErrorState, Loading, PageHeading, Stat} from '@/components/ui';
import {authorityAdminApi} from '@/lib/authority-api';
import {CASE_STATUSES} from '@/lib/authority-types';
import {pretty} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import {SimulationBanner, dateTime} from './parts';

const hours = (value: number | null) => value === null ? '—' : value < 48 ? `${value} h` : `${(value / 24).toFixed(1)} d`;

/** Oversight dashboard. Every number comes from Flask, which also reconciles states against the history. */
export default function CivicAnalytics() {
  const load = useLoad(() => authorityAdminApi.analytics(), []);
  if (load.loading) return <Loading label="Computing civic analytics…"/>;
  if (load.error || !load.value) return <ErrorState error={load.error || 'Unavailable.'} onRetry={load.refresh}/>;
  const data = load.value;
  const peak = Math.max(1, ...CASE_STATUSES.map(item => data.by_status[item]));

  return <>
    <PageHeading eyebrow="ADMINISTRATION · OVERSIGHT" title="Civic analytics"
      description={`Generated ${dateTime(data.generated_at)}`} action={<Link className="btn btn-secondary" href="/admin/authority">Authority cases</Link>}/>
    <SimulationBanner/>
    {data.reconciliation.consistent && data.reconciliation.status_sum_matches_total
      ? <Alert tone="success">Reconciled: {data.reconciliation.cases_checked} case states match their append-only history and timestamps.</Alert>
      : <Alert tone="danger">Reconciliation found {data.reconciliation.mismatches.length} case(s) whose state does not match the history.
        <ul>{data.reconciliation.mismatches.map(item => <li key={item.case_id}>{item.reference}: {item.problems.join(' ')}</li>)}</ul></Alert>}

    <div className="grid-4 mt-4">
      <Stat label="Cases" value={data.totals.cases} icon="clipboard"/>
      <Stat label="Open" value={data.totals.open} icon="clock"/>
      <Stat label="Overdue now" value={data.totals.overdue} icon="alert"/>
      <Stat label="Awaiting intake" value={data.totals.pending_intake} icon="upload"/>
    </div>

    <div className="grid-2 mt-4">
      <Card>
        <h2 className="card-title">Cases by stage</h2>
        <ul className="stack mt-3">{CASE_STATUSES.map(item => <li key={item}>
          <div className="between small"><span>{pretty(item)}</span><strong>{data.by_status[item]}</strong></div>
          <div style={{height: 8, background: 'var(--surface-2, #eef1f4)', borderRadius: 4}}>
            <div style={{width: `${(data.by_status[item] / peak) * 100}%`, height: 8, background: 'var(--primary, #1d4ed8)', borderRadius: 4}}/>
          </div>
        </li>)}</ul>
      </Card>

      <Card>
        <h2 className="card-title">Durations (from intake)</h2>
        <table className="mt-3 small" style={{width: '100%'}}><thead><tr><th align="left">Stage</th><th>Cases</th><th>Average</th><th>Median</th><th>Longest</th></tr></thead>
          <tbody>{([['To acknowledgement', data.durations.intake_to_acknowledge], ['To first resolution', data.durations.intake_to_first_resolution], ['To close', data.durations.intake_to_close]] as const).map(([label, row]) =>
            <tr key={label}><td>{label}</td><td align="center">{row.count}</td><td align="center">{hours(row.average_hours)}</td><td align="center">{hours(row.median_hours)}</td><td align="center">{hours(row.max_hours)}</td></tr>)}</tbody></table>
      </Card>

      <Card>
        <h2 className="card-title">Escalations and outcomes</h2>
        <ul className="small mt-3 stack">
          <li>Escalations: {data.escalations.total} ({data.escalations.auto_overdue} overdue, {data.escalations.manual} manual) · {data.escalations.open} open, {data.escalations.responded} answered</li>
          <li>Transfers: {data.totals.transfers}</li>
          <li>Reopened: {data.totals.reopened_cases} case(s), {data.totals.reopens} reopen(s) in total</li>
          <li>Resident verdicts: {data.outcomes.verifications.confirmed} confirmed, {data.outcomes.verifications.disputed} disputed</li>
          {Object.entries(data.outcomes.closed_by_basis).map(([basis, count]) => <li key={basis}>Closed · {pretty(basis)}: {count}</li>)}
          {data.last_snapshot && <li className="muted">Last periodic check: {dateTime(data.last_snapshot.at)} ({pretty(data.last_snapshot.trigger)})</li>}
        </ul>
      </Card>

      <Card>
        <h2 className="card-title">By department</h2>
        <table className="mt-3 small" style={{width: '100%'}}><thead><tr><th align="left">Department</th><th>Total</th><th>Open</th><th>Resolved</th><th>Closed</th><th>Overdue</th></tr></thead>
          <tbody>{data.by_department.map(row => <tr key={row.department_id}><td>{row.name}</td><td align="center">{row.total}</td><td align="center">{row.open}</td><td align="center">{row.resolved}</td><td align="center">{row.closed}</td><td align="center">{row.overdue}</td></tr>)}</tbody></table>
        {!data.by_department.length && <p className="small muted mt-2">No cases yet.</p>}
      </Card>
    </div>

    <Card className="mt-4">
      <h2 className="card-title">Audit view (latest 50 case events)</h2>
      <table className="mt-3 small" style={{width: '100%'}}><thead><tr><th align="left">When</th><th align="left">Case</th><th align="left">Action</th><th align="left">Status</th><th align="left">Actor</th><th align="left">Reason</th></tr></thead>
        <tbody>{data.audit.map(row => <tr key={`${row.case_id}-${row.sequence}`}>
          <td>{dateTime(row.at)}</td><td><Link className="text-link" href={`/authority/cases/${row.case_id}`}>{row.reference}</Link> #{row.sequence}</td>
          <td>{pretty(row.action)}</td><td>{row.from_status ? `${pretty(row.from_status)} → ` : ''}{pretty(row.to_status)}</td>
          <td>{pretty(row.actor_kind)}{row.actor_display_name ? ` · ${row.actor_display_name}` : ''}</td><td>{row.reason}</td>
        </tr>)}</tbody></table>
    </Card>
  </>;
}
