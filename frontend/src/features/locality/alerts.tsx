'use client';
import {Card, EmptyState, ErrorState, Loading, PageHeading} from '@/components/ui';
import {pretty, shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import {localityApi} from '@/lib/locality-api';
import type {LocalAlert} from '@/lib/locality-types';
import {LocalityBadge, LocalityGate, ReportButton, SafeLink} from './shared';

export default function LocalityAlerts(){return <LocalityGate permission="locality.read" title="Local alerts"><AlertsView/></LocalityGate>}

function AlertsView(){
  const load=useLoad(()=>localityApi.alerts());
  return <>
    <PageHeading eyebrow="LOCALITY" title="Local alerts" description="Published by the locality coordinator with a named source. Alerts expire automatically and move to the archive."/>
    {load.loading?<Loading label="Loading alerts…"/>:load.error?<ErrorState error={load.error} onRetry={load.refresh}/>:<>
      <h2 className="card-title mb-2">Active now</h2>
      {load.value!.active.length?<div className="stack mb-6">{load.value!.active.map(alert=><AlertCard key={alert.id} alert={alert} reportable/>)}</div>:<div className="mb-6"><EmptyState title="No active alerts" description="Nothing needs your attention right now."/></div>}
      {load.value!.scheduled.length>0&&<><h2 className="card-title mb-2">Coming up</h2><div className="stack mb-6">{load.value!.scheduled.map(alert=><AlertCard key={alert.id} alert={alert}/>)}</div></>}
      {load.value!.past.length>0&&<details><summary className="text-link">Archive ({load.value!.past.length})</summary><div className="stack mt-3">{load.value!.past.map(alert=><AlertCard key={alert.id} alert={alert}/>)}</div></details>}
    </>}
  </>;
}

function AlertCard({alert,reportable=false}:{alert:LocalAlert;reportable?:boolean}){
  return <Card className={alert.state==='ACTIVE'?'notice-card':''}>
    <div className="between"><h3 className="card-title">{alert.title}</h3><span className="flex gap-2"><LocalityBadge value={alert.severity}/><LocalityBadge value={alert.state}/></span></div>
    <p className="mt-2">{alert.description}</p>
    <p className="small muted mt-2">Source: {alert.source_label} ({pretty(alert.source_type)}){alert.source_url&&<> · <SafeLink href={alert.source_url}>view notice</SafeLink></>} · {shortDate(alert.starts_at)} to {shortDate(alert.expires_at)}</p>
    {reportable&&<ReportButton target="ALERT" id={alert.id}/>}
  </Card>;
}
