'use client';
import {useState} from 'react';
import Link from 'next/link';
import {useAuth} from '@/components/auth-provider';
import {Alert, Button, Card, ErrorState, Loading, PageHeading} from '@/components/ui';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import {localityApi} from '@/lib/locality-api';
import {ISSUE_LABEL} from '@/lib/locality-types';
import {CorrectionForm} from './correction-form';
import {CoverageMap, FictionalNotice, HistoryList, LocalityBadge, LocalityGate, PlaceFacts, StaleNotice, VerificationBadge} from './shared';

export default function PlaceDetail({id}:{id:string}){return <LocalityGate permission="locality.read" title="Place details"><DetailView id={id}/></LocalityGate>}

function DetailView({id}:{id:string}){
  const {access}=useAuth();const canSuggest=!!access?.permissions.includes('locality.listings.suggest');
  const load=useLoad(async()=>{const [detail,profile]=await Promise.all([localityApi.place(id),localityApi.profile()]);return {...detail,locality:profile.locality};},[id]);
  const [reporting,setReporting]=useState(false),[sent,setSent]=useState(false);
  if(load.loading)return <Loading label="Loading place…"/>;
  if(load.error||!load.value)return <ErrorState error={load.error||'Place unavailable.'} onRetry={load.refresh}/>;
  const {place,locality,history,my_corrections,open_corrections}=load.value;
  return <>
    <PageHeading eyebrow={place.category.label.toUpperCase()} title={place.name} description={place.description??undefined} action={<Link className="btn btn-ghost" href="/locality/places">Back to services</Link>}/>
    <FictionalNotice locality={locality}/>
    <div className="grid-2 items-start">
      <div className="stack">
        <Card>
          <div className="between"><h2 className="card-title">Listing details</h2><VerificationBadge state={place.verification_state}/></div>
          <div className="mt-3"><StaleNotice place={place} staleDays={locality.stale_after_days}/></div>
          <PlaceFacts place={place}/>
          {place.category.is_emergency&&<p className="small mt-3"><strong>In a real emergency, dial 112.</strong></p>}
          <p className="small muted mt-3">Updated {shortDate(place.updated_at)} · version {place.version}{open_corrections>0?` · ${open_corrections} correction(s) under review`:''}</p>
        </Card>
        {canSuggest&&<Card>
          <h2 className="card-title">Something wrong?</h2>
          {sent&&<div className="mt-2"><Alert tone="success">Thanks. Your correction is waiting for coordinator review. Track it in <Link className="text-link" href="/locality/corrections">My corrections</Link>.</Alert></div>}
          {my_corrections.length>0&&<ul className="small mt-2">{my_corrections.map(item=><li key={item.id}>{ISSUE_LABEL[item.issue_type]} · <LocalityBadge value={item.status}/> · {shortDate(item.submitted_at)}</li>)}</ul>}
          {reporting?<div className="mt-3"><CorrectionForm categories={locality.categories} onCancel={()=>setReporting(false)} onSubmit={async body=>{await localityApi.reportCorrection(place.id,body);setReporting(false);setSent(true);load.refresh();}}/></div>
            :<Button className="mt-3" variant="secondary" onClick={()=>{setReporting(true);setSent(false);}}>Report outdated information</Button>}
        </Card>}
        <Card><h2 className="card-title">Change history</h2><div className="mt-3"><HistoryList entries={history}/></div></Card>
      </div>
      <Card><CoverageMap locality={locality} places={[place]} selected={place.id}/></Card>
    </div>
  </>;
}
