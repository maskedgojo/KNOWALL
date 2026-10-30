'use client';
import {useState} from 'react';
import Link from 'next/link';
import {Alert, Button, Card, ErrorState, Field, Loading, PageHeading, Stat} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {errorText, useLoad} from '@/lib/use-load';
import {localityAdminApi, localityApi} from '@/lib/locality-api';
import type {Locality} from '@/lib/locality-types';
import {FictionalNotice, LocalityGate} from '../shared';
import {DeskTabs} from './common';

export default function LocalityDesk(){return <LocalityGate permission="locality.manage" title="Locality desk"><DeskView/></LocalityGate>}

function DeskView(){
  const load=useLoad(async()=>{const [summary,profile]=await Promise.all([localityAdminApi.summary(),localityApi.profile()]);return {...summary,...profile};});
  if(load.loading)return <Loading label="Loading the locality desk…"/>;
  if(load.error||!load.value)return <ErrorState error={load.error||'Desk unavailable.'} onRetry={load.refresh}/>;
  const {summary:s,locality}=load.value;
  const work:[string,number,string][]=[['Corrections waiting for review',s.corrections_pending,'/locality/manage/corrections'],['Listings needing re-verification',s.places_needing_recheck,'/locality/manage/places?state=STALE'],['Unverified listings',s.places_unverified,'/locality/manage/places?state=UNVERIFIED'],['Events waiting for approval',s.events_pending,'/locality/manage/events'],['Draft alerts',s.alerts_draft,'/locality/manage/alerts'],['Open content reports',s.reports_open,'/locality/manage/reports']];
  return <>
    <PageHeading eyebrow="LOCALITY COORDINATOR" title="Locality desk" description={`Stewardship for ${locality.name}. Every change is versioned and recorded in the history and audit trail.`}/>
    <DeskTabs/>
    <FictionalNotice locality={locality}/>
    <div className="grid-2 mb-4">
      <Stat label="Active listings" value={s.places_active} icon="building"/>
      <Stat label="Active alerts" value={s.alerts_active} icon="alert"/>
    </div>
    <Card className="mb-4"><h2 className="card-title">Work queue</h2>
      <ul className="stack mt-3">{work.map(([label,count,href])=><li key={label} className="between"><Link className="text-link" href={href}>{label}</Link><strong>{count}</strong></li>)}</ul>
      {s.corrections_awaiting_reporter>0&&<p className="small muted mt-3">{s.corrections_awaiting_reporter} correction(s) are waiting for the reporter to reply.</p>}
    </Card>
    <ProfileEditor locality={locality} onSaved={load.refresh}/>
  </>;
}

function ProfileEditor({locality,onSaved}:{locality:Locality;onSaved:()=>void}){
  const [radius,setRadius]=useState(String(locality.coverage.radius_m)),[stale,setStale]=useState(String(locality.stale_after_days));
  const [busy,setBusy]=useState(false),[message,setMessage]=useState(''),[fields,setFields]=useState<Record<string,string>>({});
  async function save(){setBusy(true);setMessage('');setFields({});try{await localityAdminApi.updateProfile({coverage_radius_m:Number(radius),stale_after_days:Number(stale)});setMessage('Saved.');onSaved();}catch(cause){setMessage(errorText(cause));if(cause instanceof ApiError)setFields(cause.fields);}finally{setBusy(false);}}
  return <Card><h2 className="card-title">Coverage settings</h2>
    <p className="small muted mt-1">Shrinking the radius is refused while active listings would fall outside it.</p>
    <div className="grid-2 mt-3">
      <Field id="coverage-radius" label="Coverage radius (metres)" type="number" min={200} max={20000} value={radius} error={fields.coverage_radius_m} onChange={event=>setRadius(event.target.value)}/>
      <Field id="stale-days" label="Re-verify listings after (days)" type="number" min={7} max={3650} value={stale} error={fields.stale_after_days} onChange={event=>setStale(event.target.value)}/>
    </div>
    {message&&<div className="mt-2"><Alert tone={message==='Saved.'?'success':'warning'}>{message}</Alert></div>}
    <Button className="mt-3" busy={busy} onClick={()=>void save()}>Save settings</Button>
  </Card>;
}
