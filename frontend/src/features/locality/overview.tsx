'use client';
import Link from 'next/link';
import {Card, EmptyState, ErrorState, Loading, PageHeading, Stat} from '@/components/ui';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import {localityApi} from '@/lib/locality-api';
import {FictionalNotice, LocalityBadge, LocalityGate, ReportButton} from './shared';

export default function LocalityOverview(){return <LocalityGate permission="locality.read" title="Locality"><Overview/></LocalityGate>}

function Overview(){
  const load=useLoad(async()=>{const [profile,feed]=await Promise.all([localityApi.profile(),localityApi.feed()]);return {...profile,...feed};});
  if(load.loading)return <Loading label="Loading your locality…"/>;
  if(load.error||!load.value)return <ErrorState error={load.error||'Locality unavailable.'} onRetry={load.refresh}/>;
  const {locality,pinned,items}=load.value;
  const emergency=locality.categories.filter(item=>item.is_emergency);
  return <>
    <PageHeading eyebrow="LOCALITY" title={locality.name} description={locality.description} action={<Link className="btn btn-primary" href="/locality/places">Find a service</Link>}/>
    <FictionalNotice locality={locality}/>
    <div className="grid-2 mb-4">
      <Stat label="Coverage radius" value={`${(locality.coverage.radius_m/1000).toFixed(1)} km`} icon="building"/>
      <Stat label="Listed services" value={locality.categories.reduce((sum,item)=>sum+(item.place_count??0),0)} icon="search"/>
    </div>
    {pinned.length>0&&<section className="stack mb-4" aria-label="Active alerts">{pinned.map(alert=><Card key={alert.id} className="notice-card">
      <div className="between"><h2 className="card-title">{alert.title}</h2><LocalityBadge value={alert.severity!}/></div>
      <p className="mt-2">{alert.summary}</p>
      <p className="small muted mt-1">Source: {alert.source_label} · until {shortDate(alert.expires_at)}</p>
      <ReportButton target="ALERT" id={alert.id}/>
    </Card>)}</section>}
    <Card className="mb-4">
      <h2 className="card-title">Browse by category</h2>
      <div className="mt-3 flex flex-wrap gap-2">{locality.categories.map(item=><Link key={item.key} className="btn btn-secondary" href={`/locality/places?category=${encodeURIComponent(item.key)}`}>{item.label} ({item.place_count??0})</Link>)}</div>
      {emergency.length>0&&<p className="small muted mt-3">Emergency categories: {emergency.map(item=>item.label).join(', ')}. In a real emergency, dial 112.</p>}
    </Card>
    <h2 className="card-title mb-2">Locality feed</h2>
    {items.length?<div className="stack">{items.map(item=><Card key={`${item.kind}-${item.id}`}>
      <div className="between"><Link className="text-link" href={item.link}><strong>{item.title}</strong></Link><LocalityBadge value={item.kind==='EVENT'?(item.timing??'UPCOMING'):'INFO'} label={item.kind==='EVENT'?'Event':'Directory update'}/></div>
      <p className="small muted mt-1">{item.summary}{item.kind==='EVENT'&&item.starts_at?` · ${shortDate(item.starts_at)}`:''}{item.kind==='DIRECTORY_UPDATE'&&item.occurred_at?` · ${shortDate(item.occurred_at)}`:''}</p>
      {item.reportable&&item.kind==='EVENT'&&<ReportButton target="EVENT" id={item.id}/>}
    </Card>)}</div>:<EmptyState title="Nothing new" description="Published events and directory updates will appear here."/>}
  </>;
}
