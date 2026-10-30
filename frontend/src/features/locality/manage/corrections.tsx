'use client';
import {useState} from 'react';
import Link from 'next/link';
import {useSearchParams} from 'next/navigation';
import {Alert, Button, Card, EmptyState, ErrorState, Loading, PageHeading, SelectField, TextareaField} from '@/components/ui';
import {shortDate} from '@/lib/format';
import {errorText, useLoad} from '@/lib/use-load';
import {localityAdminApi} from '@/lib/locality-api';
import {ISSUE_LABEL, type Decision, type StaffCorrection} from '@/lib/locality-types';
import {HistoryList, LocalityBadge, LocalityGate, SafeLink} from '../shared';
import {DeskTabs} from './common';

export default function ManageCorrections(){return <LocalityGate permission="locality.manage" title="Corrections"><QueueView/></LocalityGate>}

function QueueView(){
  const params=useSearchParams();
  const [status,setStatus]=useState('PENDING'),[open,setOpen]=useState<string|null>(params.get('open'));
  const queue=useLoad(()=>localityAdminApi.corrections(status),[status]);
  return <>
    <PageHeading eyebrow="LOCALITY COORDINATOR" title="Corrections" description="Resident reports, oldest first. Compare what was listed when the resident reported with what is published now, then decide with a reason."/>
    <DeskTabs/>
    <Card className="mb-4"><div className="max-w-xs"><SelectField id="correction-status" label="Status" value={status} onChange={event=>setStatus(event.target.value)}>
      <option value="PENDING">Pending review</option><option value="CLARIFICATION_REQUESTED">Waiting for reporter</option><option value="APPROVED">Approved</option><option value="REJECTED">Rejected</option><option value="">All</option>
    </SelectField></div></Card>
    <div className="grid-2 items-start">
      <section className="stack" aria-label="Correction queue">
        {queue.loading?<Loading label="Loading corrections…"/>:queue.error?<ErrorState error={queue.error} onRetry={queue.refresh}/>:queue.value!.corrections.length?queue.value!.corrections.map(item=>
          <Card key={item.id} className={open===item.id?'ring-2 ring-emerald-600':''}>
            <div className="between"><button className="text-link text-left" onClick={()=>setOpen(item.id)}><strong>{item.place?.name??`New: ${item.proposed_value??'missing service'}`}</strong></button><LocalityBadge value={item.status}/></div>
            <p className="small muted mt-1">{ISSUE_LABEL[item.issue_type]} · {item.reporter_display_name} · {shortDate(item.submitted_at)}</p>
            {item.published_changed_since_submission&&<p className="small mt-1"><LocalityBadge value="STALE" label="Listing changed since report"/></p>}
            {!!item.competing_open_corrections&&<p className="small mt-1"><LocalityBadge value="PENDING" label={`${item.competing_open_corrections} other open report(s) on this field`}/></p>}
          </Card>):<EmptyState title="Queue is clear" description="No corrections with this status."/>}
      </section>
      <section aria-label="Correction review">{open?<Review key={open} id={open} onDecided={queue.refresh}/>:<Card><p className="muted">Select a correction to review it.</p></Card>}</section>
    </div>
  </>;
}

function Review({id,onDecided}:{id:string;onDecided:()=>void}){
  const load=useLoad(()=>localityAdminApi.correction(id),[id]);
  const [reason,setReason]=useState(''),[busy,setBusy]=useState<Decision|''>(''),[error,setError]=useState(''),[done,setDone]=useState('');
  if(load.loading)return <Loading label="Loading correction…"/>;
  if(load.error||!load.value)return <ErrorState error={load.error||'Correction unavailable.'} onRetry={load.refresh}/>;
  const c:StaffCorrection=load.value.correction;
  const reviewable=c.status==='PENDING'||c.status==='CLARIFICATION_REQUESTED';
  async function decide(decision:Decision){setBusy(decision);setError('');setDone('');
    try{await localityAdminApi.decideCorrection(c.id,decision,reason.trim());setReason('');setDone(decision==='APPROVE'?'Approved and applied to the listing.':decision==='REJECT'?'Rejected. The reporter can see your reason.':'Clarification requested from the reporter.');load.refresh();onDecided();}
    catch(cause){setError(errorText(cause));load.refresh();}finally{setBusy('');}}
  return <Card>
    <div className="between"><h2 className="card-title">{c.place?<Link className="text-link" href={`/locality/manage/places/${c.place.id}`}>{c.place.name}</Link>:'Missing service'}</h2><LocalityBadge value={c.status}/></div>
    <p className="small muted mt-1">{ISSUE_LABEL[c.issue_type]} · reported by {c.reporter_display_name} on {shortDate(c.submitted_at)}</p>
    {c.field&&<table className="w-full small mt-3"><thead><tr className="text-left"><th className="muted">When reported</th><th className="muted">Published now</th><th className="muted">Proposed</th></tr></thead>
      <tbody><tr><td>{c.current_value??'—'}</td><td className={c.published_changed_since_submission?'font-semibold':''}>{c.published_value??'—'}</td><td><strong>{c.proposed_value??'—'}</strong></td></tr></tbody></table>}
    {!c.field&&c.proposed_value&&<p className="mt-3"><span className="muted small">Proposed:</span> {c.proposed_value}</p>}
    {c.published_changed_since_submission&&<div className="mt-3"><Alert tone="warning">The listing changed after this report. Approval is blocked; reject it or ask the reporter to confirm.</Alert></div>}
    <p className="mt-3"><span className="muted small">Reporter&apos;s reason:</span> {c.reason}</p>
    {c.source_url&&<p className="small mt-1">Evidence: <SafeLink href={c.source_url}/></p>}
    {c.related_corrections&&c.related_corrections.length>0&&<div className="mt-3"><strong className="small">Other reports on this field</strong><ul className="small">{c.related_corrections.map(item=><li key={item.id}>{item.proposed_value??'—'} · {item.reporter_display_name} · <LocalityBadge value={item.status}/></li>)}</ul></div>}
    {done&&<div className="mt-3"><Alert tone="success">{done}</Alert></div>}
    {reviewable&&<div className="stack mt-4">
      <TextareaField id="decision-reason" label="Decision reason (required, shared with the reporter)" value={reason} maxLength={1000} placeholder="For example: confirmed by calling the shop." onChange={event=>setReason(event.target.value)}/>
      {error&&<Alert tone="warning">{error}</Alert>}
      <div className="flex flex-wrap gap-2">
        {c.status==='PENDING'&&<Button busy={busy==='APPROVE'} disabled={reason.trim().length<5||!!busy||c.published_changed_since_submission} onClick={()=>void decide('APPROVE')}>Approve and apply</Button>}
        {c.status==='PENDING'&&<Button variant="secondary" busy={busy==='REQUEST_CLARIFICATION'} disabled={reason.trim().length<5||!!busy} onClick={()=>void decide('REQUEST_CLARIFICATION')}>Ask for clarification</Button>}
        <Button variant="danger" busy={busy==='REJECT'} disabled={reason.trim().length<5||!!busy} onClick={()=>void decide('REJECT')}>Reject</Button>
      </div>
    </div>}
    {c.decision_reason&&!reviewable&&<p className="small mt-3"><span className="muted">Decision:</span> {c.decision_reason}{c.reviewer_display_name?` (${c.reviewer_display_name})`:''}</p>}
    <details className="mt-4"><summary className="small text-link">History</summary><div className="mt-2"><HistoryList entries={c.history??[]}/></div></details>
  </Card>;
}
