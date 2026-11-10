'use client';
import Link from 'next/link';
import {useState} from 'react';
import {Card, EmptyState, ErrorState, Loading, PageHeading, SelectField} from '@/components/ui';
import {authorityApi} from '@/lib/authority-api';
import {CASE_STATUSES, type CaseStatus} from '@/lib/authority-types';
import {pretty} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import {CaseBadge, SimulationBanner, dateTime} from './parts';

/** Simulated official's queue. Flask returns only the official's own department cases. */
export default function OfficerWorkspace() {
  const me = useLoad(() => authorityApi.me(), []);
  const [status, setStatus] = useState<CaseStatus | ''>('');
  const [overdue, setOverdue] = useState(false);
  const list = useLoad(() => authorityApi.list({status: status || undefined, overdue}), [status, overdue]);

  if (me.loading) return <Loading label="Checking your department…"/>;
  if (me.error || !me.value) return <ErrorState error={me.error || 'Unavailable.'} onRetry={me.refresh}/>;
  if (!me.value.officer && !me.value.is_coordinator) return <EmptyState title="No department assignment"
    description="This workspace is for simulated department officials. A coordinator assigns accounts to a demo department."/>;
  const officer = me.value.officer;

  return <>
    <PageHeading eyebrow="AUTHORITY WORKSPACE · DEMO" title={officer ? officer.department.name : 'All departments'}
      description={officer ? `${officer.title} · simulated official` : 'Coordinator view of every simulated department'}/>
    <SimulationBanner/>
    <Card className="mt-4">
      <div className="flex gap-3 flex-wrap items-end">
        <SelectField id="case-status" label="Status" value={status} onChange={event => setStatus(event.target.value as CaseStatus | '')}>
          <option value="">All statuses</option>{CASE_STATUSES.map(item => <option key={item} value={item}>{pretty(item)}</option>)}
        </SelectField>
        <label className="flex gap-2 items-center small"><input type="checkbox" checked={overdue} onChange={event => setOverdue(event.target.checked)}/> Overdue only</label>
      </div>
      <div className="mt-4">{list.loading ? <Loading label="Loading cases…"/> : list.error || !list.value ? <ErrorState error={list.error} onRetry={list.refresh}/>
        : list.value.cases.length === 0 ? <EmptyState title="No cases" description="Cases appear here when a coordinator routes a validated civic issue to this department."/>
        : <div className="stack">{list.value.cases.map(item => <div key={item.case_id} className="notice-card">
          <div className="between"><Link href={`/authority/cases/${item.case_id}`}><strong>{item.authority_case_id} · {item.title}</strong></Link><CaseBadge status={item.status} overdue={item.is_overdue}/></div>
          <div className="small muted mt-1">{pretty(item.category)} · {pretty(item.severity)} · {item.community_support} supporters · {item.department.name} · due {dateTime(item.due_at)}</div>
        </div>)}</div>}</div>
    </Card>
  </>;
}
