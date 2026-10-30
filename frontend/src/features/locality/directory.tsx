'use client';
import {useState} from 'react';
import Link from 'next/link';
import {useRouter, useSearchParams} from 'next/navigation';
import {Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, SelectField} from '@/components/ui';
import {useLoad} from '@/lib/use-load';
import {localityApi} from '@/lib/locality-api';
import {categoryColor, CoverageMap, FictionalNotice, LocalityGate, VerificationBadge} from './shared';

export default function Directory(){return <LocalityGate permission="locality.read" title="Essential services"><DirectoryView/></LocalityGate>}

function DirectoryView(){
  const params=useSearchParams();const router=useRouter();
  const category=params.get('category')??'';const q=params.get('q')??'';
  const [text,setText]=useState(q);const [selected,setSelected]=useState<string|null>(null);
  const profile=useLoad(()=>localityApi.profile());
  const places=useLoad(()=>localityApi.places({q,category}),[q,category]);
  function apply(next:{q?:string;category?:string}){const search=new URLSearchParams();const value={q,category,...next};if(value.q)search.set('q',value.q);if(value.category)search.set('category',value.category);setSelected(null);router.replace(`/locality/places${search.toString()?`?${search}`:''}`);}
  function select(id:string){setSelected(id);document.getElementById(`place-${id}`)?.scrollIntoView({behavior:'smooth',block:'nearest'});}
  const locality=profile.value?.locality;
  return <>
    <PageHeading eyebrow="LOCALITY" title="Essential services" description="Pharmacies, clinics, police, emergency and public services near the society. Each listing shows its source and when it was last verified." action={<Link className="btn btn-secondary" href="/locality/corrections">My corrections</Link>}/>
    <FictionalNotice locality={locality}/>
    <Card className="mb-4">
      <form className="grid-2" onSubmit={event=>{event.preventDefault();apply({q:text.trim()});}}>
        <Field id="place-search" label="Search" placeholder="Name, address or service" value={text} maxLength={100} onChange={event=>setText(event.target.value)}/>
        <SelectField id="place-category" label="Category" value={category} onChange={event=>apply({category:event.target.value})}>
          <option value="">All categories</option>
          {locality?.categories.map(item=><option key={item.key} value={item.key}>{item.label}</option>)}
        </SelectField>
        <div className="flex gap-2"><Button type="submit">Search</Button>{(q||category)&&<Button type="button" variant="ghost" onClick={()=>{setText('');router.replace('/locality/places');}}>Clear</Button>}</div>
      </form>
    </Card>
    {places.loading||profile.loading?<Loading label="Loading services…"/>:places.error||profile.error?<ErrorState error={places.error||profile.error} onRetry={()=>{places.refresh();profile.refresh();}}/>:
      <div className="grid-2 items-start">
        <section aria-label="Results" className="stack">
          <p className="small muted">{places.value!.total} result{places.value!.total===1?'':'s'}</p>
          {places.value!.places.length?places.value!.places.map(place=><Card key={place.id} id={`place-${place.id}`} className={selected===place.id?'ring-2 ring-emerald-600':''} onMouseEnter={()=>setSelected(place.id)}>
            <div className="between"><Link className="text-link" href={`/locality/places/${place.id}`}><strong>{place.name}</strong></Link><VerificationBadge state={place.verification_state}/></div>
            <p className="small mt-1"><span aria-hidden="true" style={{color:categoryColor(place.category.key)}}>●</span> {place.category.label}{place.address?` · ${place.address}`:''}</p>
            {place.phone&&<p className="small mt-1">Phone: <a className="text-link" href={`tel:${place.phone.replace(/[^0-9+]/g,'')}`}>{place.phone}</a></p>}
          </Card>):<EmptyState title="No matching services" description="Try another search or category. If a service is missing, report it from My corrections."/>}
        </section>
        <Card><CoverageMap locality={locality!} places={places.value!.places} selected={selected} onSelect={select}/></Card>
      </div>}
  </>;
}
