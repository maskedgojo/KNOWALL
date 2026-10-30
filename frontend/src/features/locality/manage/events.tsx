'use client';
import {useState} from 'react';
import {Card, EmptyState, ErrorState, Loading, PageHeading, SelectField} from '@/components/ui';
import {pretty} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import {localityAdminApi} from '@/lib/locality-api';
import {timeRange} from '@/lib/operations-types';
import {HistoryList, LocalityBadge, LocalityGate} from '../shared';
import {DeskTabs, ReasonAction} from './common';

export default function ManageEvents(){return <LocalityGate permission="locality.manage" title="Event moderation"><EventsView/></LocalityGate>}

function EventsView(){
  const [status,setStatus]=useState('PENDING');
  const load=useLoad(()=>localityAdminApi.events(status),[status]);
  return <>
    <PageHeading eyebrow="LOCALITY COORDINATOR" title="Events" description="Approve resident-submitted and society-shared events before residents see them."/>
    <DeskTabs/>
    <Card className="mb-4"><div className="max-w-xs"><SelectField id="event-status" label="Status" value={status} onChange={event=>setStatus(event.target.value)}><option value="PENDING">Pending</option><option value="PUBLISHED">Published</option><option value="REJECTED">Rejected</option><option value="ARCHIVED">Archived</option><option value="">All</option></SelectField></div></Card>
    {load.loading?<Loading label="Loading events…"/>:load.error?<ErrorState error={load.error} onRetry={load.refresh}/>:load.value!.events.length?<div className="stack">{load.value!.events.map(event=><Card key={event.id}>
      <div className="between"><h2 className="card-title">{event.title}</h2><LocalityBadge value={event.status??'PENDING'}/></div>
      <p className="small muted mt-1">{timeRange(event.starts_at,event.ends_at)} · {event.venue} · {pretty(event.category)} · {event.organizer}{event.shared_by_society?' · Shared from society events':''} · submitted by {event.submitted_by_display_name}</p>
      <p className="mt-2">{event.description}</p>
      {event.decision_reason&&<p className="small mt-2"><span className="muted">Decision:</span> {event.decision_reason}{event.reviewer_display_name?` (${event.reviewer_display_name})`:''}</p>}
      <div className="flex flex-wrap gap-2 mt-3">
        {event.status==='PENDING'&&event.timing!=='COMPLETED'&&<ReasonAction label="Publish" variant="primary" onConfirm={async reason=>{await localityAdminApi.decideEvent(event.id,'PUBLISH',reason);load.refresh();}}/>}
        {event.status==='PENDING'&&<ReasonAction label="Reject" variant="danger" onConfirm={async reason=>{await localityAdminApi.decideEvent(event.id,'REJECT',reason);load.refresh();}}/>}
        {event.status==='PUBLISHED'&&<ReasonAction label="Archive" variant="danger" onConfirm={async reason=>{await localityAdminApi.decideEvent(event.id,'ARCHIVE',reason);load.refresh();}}/>}
      </div>
      {event.history&&<details className="mt-3"><summary className="small text-link">History</summary><div className="mt-2"><HistoryList entries={event.history}/></div></details>}
    </Card>)}</div>:<EmptyState title="No events" description="Nothing with this status."/>}
  </>;
}
