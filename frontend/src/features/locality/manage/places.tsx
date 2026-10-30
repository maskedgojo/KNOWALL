'use client';
import {useState} from 'react';
import Link from 'next/link';
import {useRouter, useSearchParams} from 'next/navigation';
import {Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, SelectField} from '@/components/ui';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import {localityAdminApi, localityApi} from '@/lib/locality-api';
import {STATE_LABEL, type VerificationState} from '@/lib/locality-types';
import {LocalityGate, VerificationBadge} from '../shared';
import {DeskTabs} from './common';
import {PlaceForm} from './place-form';

const STATES:VerificationState[]=['VERIFIED','STALE','UNVERIFIED','NEEDS_RECHECK','ARCHIVED'];

export default function ManagePlaces(){return <LocalityGate permission="locality.manage" title="Manage places"><PlacesView/></LocalityGate>}

function PlacesView(){
  const params=useSearchParams();const router=useRouter();
  const state=params.get('state')??'';const q=params.get('q')??'';
  const [text,setText]=useState(q),[creating,setCreating]=useState(false);
  const categories=useLoad(()=>localityApi.categories());
  const places=useLoad(()=>localityAdminApi.places({state,q}),[state,q]);
  function apply(next:{state?:string;q?:string}){const value={state,q,...next};const search=new URLSearchParams();if(value.state)search.set('state',value.state);if(value.q)search.set('q',value.q);router.replace(`/locality/manage/places${search.toString()?`?${search}`:''}`);}
  return <>
    <PageHeading eyebrow="LOCALITY COORDINATOR" title="Places" description="Create, edit, verify and archive directory listings." action={<Button onClick={()=>setCreating(open=>!open)}>{creating?'Close form':'Add a place'}</Button>}/>
    <DeskTabs/>
    {creating&&categories.value&&<Card className="mb-4"><h2 className="card-title">New listing</h2><p className="small muted mt-1">New listings start as Not yet verified. Verify them once you have checked the details.</p>
      <div className="mt-3"><PlaceForm categories={categories.value.categories} submitLabel="Create listing" onCancel={()=>setCreating(false)} onSubmit={async body=>{const {place}=await localityAdminApi.createPlace(body);router.push(`/locality/manage/places/${place.id}`);}}/></div></Card>}
    <Card className="mb-4"><form className="grid-2" onSubmit={event=>{event.preventDefault();apply({q:text.trim()});}}>
      <Field id="manage-search" label="Search" value={text} maxLength={100} onChange={event=>setText(event.target.value)}/>
      <SelectField id="manage-state" label="Verification state" value={state} onChange={event=>apply({state:event.target.value})}><option value="">All</option><option value="ACTIVE">All active</option>{STATES.map(item=><option key={item} value={item}>{STATE_LABEL[item]}</option>)}</SelectField>
      <div><Button type="submit">Search</Button></div>
    </form></Card>
    {places.loading?<Loading label="Loading places…"/>:places.error?<ErrorState error={places.error} onRetry={places.refresh}/>:places.value!.places.length?
      <div className="stack">{places.value!.places.map(place=><Card key={place.id}>
        <div className="between"><Link className="text-link" href={`/locality/manage/places/${place.id}`}><strong>{place.name}</strong></Link><VerificationBadge state={place.verification_state}/></div>
        <p className="small muted mt-1">{place.category.label} · last verified {shortDate(place.last_verified_at)} · version {place.version}{place.open_corrections?` · ${place.open_corrections} open correction(s)`:''}</p>
      </Card>)}</div>:<EmptyState title="No places" description="No listings match this filter."/>}
  </>;
}
