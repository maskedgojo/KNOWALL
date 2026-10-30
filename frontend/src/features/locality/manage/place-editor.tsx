'use client';
import {useState} from 'react';
import Link from 'next/link';
import {Alert, Button, Card, ErrorState, Field, Loading, PageHeading, SelectField, TextareaField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {pretty, shortDate} from '@/lib/format';
import {errorText, useLoad} from '@/lib/use-load';
import {localityAdminApi, localityApi} from '@/lib/locality-api';
import {ISSUE_LABEL, STAFF_METHODS} from '@/lib/locality-types';
import {HistoryList, LocalityBadge, LocalityGate, PlaceFacts, StaleNotice, VerificationBadge} from '../shared';
import {DeskTabs, ReasonAction} from './common';
import {PlaceForm} from './place-form';

export default function PlaceEditor({id}:{id:string}){return <LocalityGate permission="locality.manage" title="Edit place"><EditorView id={id}/></LocalityGate>}

function EditorView({id}:{id:string}){
  const load=useLoad(async()=>{const [detail,categories]=await Promise.all([localityAdminApi.place(id),localityApi.categories()]);return {...detail,...categories};},[id]);
  const [editing,setEditing]=useState(false),[notice,setNotice]=useState('');
  if(load.loading)return <Loading label="Loading place…"/>;
  if(load.error||!load.value)return <ErrorState error={load.error||'Place unavailable.'} onRetry={load.refresh}/>;
  const {place,verifications,corrections,history,categories}=load.value;
  const archived=place.publication_status==='ARCHIVED';
  const done=(message:string)=>{setNotice(message);setEditing(false);load.refresh();};
  return <>
    <PageHeading eyebrow="LOCALITY COORDINATOR" title={place.name} description={`${place.category.label} · version ${place.version}`} action={<Link className="btn btn-ghost" href="/locality/manage/places">All places</Link>}/>
    <DeskTabs/>
    {notice&&<div className="mb-4"><Alert tone="success">{notice}</Alert></div>}
    {archived&&<div className="mb-4"><Alert tone="warning">Archived{place.archived_reason?`: ${place.archived_reason}`:''}. Residents cannot see this listing.</Alert></div>}
    <div className="grid-2 items-start">
      <div className="stack">
        <Card>
          <div className="between"><h2 className="card-title">Listing</h2><VerificationBadge state={place.verification_state}/></div>
          <div className="mt-3"><StaleNotice place={place}/></div>
          {editing?<div className="mt-3"><PlaceForm categories={categories} place={place} submitLabel="Save changes" onCancel={()=>setEditing(false)} onSubmit={async (body,note)=>{
            if(!Object.keys(body).length){setEditing(false);return;}
            try{await localityAdminApi.updatePlace(place.id,{...body,expected_version:place.version,...(note?{note}:{})});done('Listing updated.');}
            catch(cause){if(cause instanceof ApiError&&cause.code==='PLACE_VERSION_CONFLICT'){load.refresh();}throw cause;}
          }}/></div>:<><PlaceFacts place={place}/>{place.last_verified_by_display_name&&<p className="small muted mt-2">Last verified by {place.last_verified_by_display_name}</p>}</>}
          {!editing&&<div className="flex flex-wrap gap-2 mt-4">
            <Button variant="secondary" onClick={()=>setEditing(true)}>Edit details</Button>
            {!archived&&<ReasonAction label="Flag for recheck" placeholder="Why does this need checking?" onConfirm={async reason=>{await localityAdminApi.markStale(place.id,reason);done('Flagged for recheck.');}}/>}
            {archived?<ReasonAction label="Restore" variant="primary" onConfirm={async reason=>{await localityAdminApi.restorePlace(place.id,reason);done('Listing restored.');}}/>
              :<ReasonAction label="Archive" variant="danger" placeholder="For example: permanently closed." onConfirm={async reason=>{await localityAdminApi.archivePlace(place.id,reason);done('Listing archived.');}}/>}
          </div>}
        </Card>
        {!archived&&<VerifyCard placeId={place.id} onDone={()=>done('Listing verified.')}/>}
        <Card><h2 className="card-title">History</h2><div className="mt-3"><HistoryList entries={history}/></div></Card>
      </div>
      <div className="stack">
        <Card><h2 className="card-title">Corrections</h2>{corrections.length?<ul className="stack small mt-3">{corrections.map(item=><li key={item.id}><Link className="text-link" href={`/locality/manage/corrections?open=${item.id}`}>{ISSUE_LABEL[item.issue_type]}</Link> · <LocalityBadge value={item.status}/> · {item.reporter_display_name} · {shortDate(item.submitted_at)}{item.proposed_value&&<div className="muted">Proposed: {item.proposed_value}</div>}</li>)}</ul>:<p className="small muted mt-2">No corrections.</p>}</Card>
        <Card><h2 className="card-title">Verification log</h2>{verifications.length?<ul className="stack small mt-3">{verifications.map(item=><li key={item.id}><strong>{pretty(item.method)}</strong>{item.scope!=='LISTING'?` (${item.scope} only)`:''} · {shortDate(item.verified_at)}{item.verifier_display_name?` · ${item.verifier_display_name}`:''}{item.note&&<div className="muted">{item.note}</div>}</li>)}</ul>:<p className="small muted mt-2">Never verified.</p>}</Card>
      </div>
    </div>
  </>;
}

function VerifyCard({placeId,onDone}:{placeId:string;onDone:()=>void}){
  const [method,setMethod]=useState<string>('PHONE_CALL'),[note,setNote]=useState(''),[source,setSource]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  async function verify(){setBusy(true);setError('');try{await localityAdminApi.verifyPlace(placeId,{method,note:note.trim(),...(source.trim()?{source_url:source.trim()}:{})});setNote('');setSource('');onDone();}catch(cause){setError(errorText(cause));}finally{setBusy(false);}}
  return <Card><h2 className="card-title">Verify listing</h2><p className="small muted mt-1">Record how you confirmed the whole listing is correct today.</p>
    <div className="stack mt-3">
      <SelectField id="verify-method" label="Method" value={method} onChange={event=>setMethod(event.target.value)}>{STAFF_METHODS.map(item=><option key={item} value={item}>{pretty(item)}</option>)}</SelectField>
      <TextareaField id="verify-note" label="What did you check? (required)" value={note} maxLength={500} onChange={event=>setNote(event.target.value)}/>
      <Field id="verify-source" label={method==='OFFICIAL_SOURCE'?'Official source link (required)':'Source link (optional)'} value={source} maxLength={500} onChange={event=>setSource(event.target.value)}/>
      {error&&<Alert tone="warning">{error}</Alert>}
      <div><Button busy={busy} disabled={note.trim().length<3} onClick={()=>void verify()}>Mark verified</Button></div>
    </div>
  </Card>;
}
