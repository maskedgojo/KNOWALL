'use client';
import {useState} from 'react';
import {Card, EmptyState, ErrorState, Loading, PageHeading, SelectField} from '@/components/ui';
import {pretty, shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import {localityAdminApi} from '@/lib/locality-api';
import {LocalityBadge, LocalityGate} from '../shared';
import {DeskTabs, ReasonAction} from './common';

export default function ManageReports(){return <LocalityGate permission="locality.manage" title="Content reports"><ReportsView/></LocalityGate>}

function ReportsView(){
  const [status,setStatus]=useState('OPEN');
  const load=useLoad(()=>localityAdminApi.reports(status),[status]);
  return <>
    <PageHeading eyebrow="LOCALITY COORDINATOR" title="Content reports" description="Residents flag published events and alerts. Archiving the content settles every open report on it."/>
    <DeskTabs/>
    <Card className="mb-4"><div className="max-w-xs"><SelectField id="report-status" label="Status" value={status} onChange={event=>setStatus(event.target.value)}><option value="OPEN">Open</option><option value="ACTIONED">Actioned</option><option value="DISMISSED">Dismissed</option><option value="">All</option></SelectField></div></Card>
    {load.loading?<Loading label="Loading reports…"/>:load.error?<ErrorState error={load.error} onRetry={load.refresh}/>:load.value!.reports.length?<div className="stack">{load.value!.reports.map(report=><Card key={report.id}>
      <div className="between"><h2 className="card-title">{report.target_title??'Removed content'}</h2><LocalityBadge value={report.status}/></div>
      <p className="small muted mt-1">{pretty(report.target_type)}{report.target_status?` · currently ${pretty(report.target_status)}`:''} · reported by {report.reporter_display_name} · {shortDate(report.created_at)}</p>
      <p className="mt-2">{report.reason}</p>
      {report.review_note&&<p className="small mt-2"><span className="muted">Review:</span> {report.review_note}{report.reviewer_display_name?` (${report.reviewer_display_name})`:''}</p>}
      {report.status==='OPEN'&&<div className="flex flex-wrap gap-2 mt-3">
        <ReasonAction label="Archive the content" variant="danger" onConfirm={async reason=>{await localityAdminApi.decideReport(report.id,'ARCHIVE_CONTENT',reason);load.refresh();}}/>
        <ReasonAction label="Dismiss" onConfirm={async reason=>{await localityAdminApi.decideReport(report.id,'DISMISS',reason);load.refresh();}}/>
      </div>}
    </Card>)}</div>:<EmptyState title="No reports" description="Nothing with this status."/>}
  </>;
}
