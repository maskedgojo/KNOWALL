'use client';
import {useState} from 'react';
import Link from 'next/link';
import {Alert, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, TextareaField} from '@/components/ui';
import {shortDate} from '@/lib/format';
import {errorText, useLoad} from '@/lib/use-load';
import {localityApi} from '@/lib/locality-api';
import {ISSUE_LABEL, type Correction} from '@/lib/locality-types';
import {CorrectionForm} from './correction-form';
import {HistoryList, LocalityBadge, LocalityGate} from './shared';

const STATUS_HELP:Record<string,string>={PENDING:'Waiting for a coordinator.',CLARIFICATION_REQUESTED:'The coordinator asked you a question. Reply below.',APPROVED:'Approved and applied to the listing.',REJECTED:'Not applied.'};

export default function MyCorrections(){return <LocalityGate permission="locality.listings.suggest" title="My corrections"><MyCorrectionsView/></LocalityGate>}

function MyCorrectionsView(){
  const load=useLoad(async()=>{const [mine,profile]=await Promise.all([localityApi.myCorrections(),localityApi.profile()]);return {...mine,categories:profile.locality.categories};});
  const [missing,setMissing]=useState(false),[notice,setNotice]=useState('');
  return <>
    <PageHeading eyebrow="LOCALITY" title="My corrections" description="Reports you sent about the services directory, and what the coordinator decided." action={<Button variant="secondary" onClick={()=>setMissing(open=>!open)}>Report a missing service</Button>}/>
    {notice&&<div className="mb-4"><Alert tone="success">{notice}</Alert></div>}
    {missing&&load.value&&<Card className="mb-4"><h2 className="card-title">Missing service</h2><div className="mt-3"><CorrectionForm missing categories={load.value.categories} onCancel={()=>setMissing(false)} onSubmit={async body=>{await localityApi.reportMissing(body);setMissing(false);setNotice('Sent. A coordinator will review it.');load.refresh();}}/></div></Card>}
    {load.loading?<Loading label="Loading your corrections…"/>:load.error?<ErrorState error={load.error} onRetry={load.refresh}/>:load.value!.corrections.length?
      <div className="stack">{load.value!.corrections.map(item=><CorrectionCard key={item.id} correction={item} onChanged={load.refresh}/>)}</div>
      :<EmptyState title="No corrections yet" description="Open a place in the directory and choose Report outdated information." action={<Link className="btn btn-primary" href="/locality/places">Browse services</Link>}/>}
  </>;
}

function CorrectionCard({correction,onChanged}:{correction:Correction;onChanged:()=>void}){
  const [message,setMessage]=useState(''),[value,setValue]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  async function reply(){setBusy(true);setError('');try{await localityApi.respond(correction.id,value.trim()?{message:message.trim(),proposed_value:value.trim()}:{message:message.trim()});onChanged();}catch(cause){setError(errorText(cause));}finally{setBusy(false);}}
  return <Card>
    <div className="between"><h2 className="card-title">{correction.place?<Link className="text-link" href={`/locality/places/${correction.place.id}`}>{correction.place.name}</Link>:(correction.proposed_value??'Missing service')}</h2><LocalityBadge value={correction.status}/></div>
    <p className="small muted mt-1">{ISSUE_LABEL[correction.issue_type]} · sent {shortDate(correction.submitted_at)} · {STATUS_HELP[correction.status]}</p>
    {correction.field&&<dl className="grid-2 small mt-3"><div><dt className="muted">Listed when you reported</dt><dd>{correction.current_value??'—'}</dd></div><div><dt className="muted">You proposed</dt><dd>{correction.proposed_value??'—'}</dd></div></dl>}
    <p className="small mt-2"><span className="muted">Your reason:</span> {correction.reason}</p>
    {correction.decision_reason&&<div className="mt-3"><Alert tone={correction.status==='APPROVED'?'success':correction.status==='REJECTED'?'danger':'warning'}><strong>Coordinator:</strong> {correction.decision_reason}</Alert></div>}
    {correction.status==='CLARIFICATION_REQUESTED'&&<div className="stack mt-3">
      <TextareaField id={`reply-${correction.id}`} label="Your reply" value={message} maxLength={1000} onChange={event=>setMessage(event.target.value)}/>
      {correction.field&&correction.field!=='coordinates'&&correction.field!=='category'&&<Field id={`reply-value-${correction.id}`} label="Updated proposal (optional)" value={value} maxLength={500} onChange={event=>setValue(event.target.value)}/>}
      {error&&<Alert tone="warning">{error}</Alert>}
      <div><Button busy={busy} disabled={message.trim().length<5} onClick={()=>void reply()}>Send reply</Button></div>
    </div>}
    {correction.history&&correction.history.length>0&&<details className="mt-3"><summary className="small text-link">Timeline</summary><div className="mt-2"><HistoryList entries={correction.history}/></div></details>}
  </Card>;
}
