'use client';
import {useState,type ReactNode} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Button, PageHeading, TextareaField} from '@/components/ui';
import {pretty, shortDate} from '@/lib/format';
import {errorText} from '@/lib/use-load';
import {localityApi} from '@/lib/locality-api';
import {safeHref, STATE_LABEL, type HistoryEntry, type Locality, type Place, type VerificationState} from '@/lib/locality-types';

/** Locality-specific tones; the shared Badge keeps its Module 1-3 meanings. */
const TONE:Record<string,'success'|'warning'|'danger'|'neutral'>={VERIFIED:'success',PUBLISHED:'success',APPROVED:'success',ACTIVE:'success',ACTIONED:'success',
  STALE:'warning',NEEDS_RECHECK:'warning',PENDING:'warning',CLARIFICATION_REQUESTED:'warning',DRAFT:'warning',SCHEDULED:'warning',OPEN:'warning',MEDIUM:'warning',
  HIGH:'danger',REJECTED:'danger',ARCHIVED:'neutral',EXPIRED:'neutral',UNVERIFIED:'neutral',DISMISSED:'neutral',LOW:'neutral',INFO:'neutral'};
export function LocalityBadge({value,label}:{value:string;label?:string}){return <span className={`badge badge-${TONE[value]??'neutral'}`}>{label??pretty(value)}</span>}
export function VerificationBadge({state}:{state:VerificationState}){return <LocalityBadge value={state} label={STATE_LABEL[state]}/>}

/** Only http(s) links become clickable; anything else is shown as plain text. */
export function SafeLink({href,children}:{href:string|null|undefined;children?:ReactNode}){
  const safe=safeHref(href);
  if(!safe)return href?<span className="muted">{href}</span>:null;
  return <a className="text-link" href={safe} target="_blank" rel="noopener noreferrer nofollow">{children??safe}</a>;
}

export function FictionalNotice({locality}:{locality?:Locality|null}){
  if(locality&&!locality.is_fictional)return null;
  return <div className="mb-4"><Alert tone="warning"><strong>Demonstration data.</strong> Every place, phone number, event and alert in this locality is fictional. In a real emergency, dial 112.</Alert></div>;
}

/** Pages check permissions themselves; Flask enforces them again on every request. */
export function LocalityGate({permission,title,children}:{permission:string;title:string;children:ReactNode}){
  const {access}=useAuth();
  if(!access?.permissions.includes(permission))return <PageHeading eyebrow="LOCALITY" title={title} description={permission==='locality.manage'?'Only a Locality Coordinator can open this desk.':'Current resident access is required to view the locality.'}/>;
  return <>{children}</>;
}

export function PlaceFacts({place}:{place:Place}){
  return <dl className="grid-2 mt-3 small">
    <div><dt className="muted">Address</dt><dd>{place.address||'Not recorded'}</dd></div>
    <div><dt className="muted">Phone</dt><dd>{place.phone?<a className="text-link" href={`tel:${place.phone.replace(/[^0-9+]/g,'')}`}>{place.phone}</a>:'Not recorded'}</dd></div>
    <div><dt className="muted">Website</dt><dd>{place.website_url?<SafeLink href={place.website_url}/>:'Not recorded'}</dd></div>
    <div><dt className="muted">Source</dt><dd>{place.source_label}{place.source_url&&<> · <SafeLink href={place.source_url}>source link</SafeLink></>}</dd></div>
    <div><dt className="muted">Last verified</dt><dd>{place.last_verified_at?`${shortDate(place.last_verified_at)}${place.last_verification_method?` · ${pretty(place.last_verification_method)}`:''}`:'Never'}</dd></div>
    <div><dt className="muted">Data origin</dt><dd>{place.data_origin==='FICTIONAL_DEMO'?'Fictional demo listing':'Real-world listing'}</dd></div>
  </dl>;
}

export function StaleNotice({place,staleDays}:{place:Place;staleDays?:number}){
  if(place.verification_state==='STALE')return <Alert tone="warning">This listing has not been re-verified in over {staleDays??180} days. Call ahead before relying on it.</Alert>;
  if(place.verification_state==='NEEDS_RECHECK')return <Alert tone="warning">A coordinator flagged this listing for recheck. Details may be out of date.</Alert>;
  if(place.verification_state==='UNVERIFIED')return <Alert tone="info">This listing has not been verified by a coordinator yet.</Alert>;
  return null;
}

export function HistoryList({entries}:{entries:HistoryEntry[]}){
  if(!entries.length)return <p className="small muted">No history yet.</p>;
  return <ol className="stack small">{entries.map(entry=><li key={entry.id}><strong>{pretty(entry.action)}</strong> · {shortDate(entry.created_at)}{entry.actor_display_name?` · ${entry.actor_display_name}`:''}{entry.reason&&<div className="muted">{entry.reason}</div>}</li>)}</ol>;
}

/** Inline "report this" control for published events and alerts. */
export function ReportButton({target,id}:{target:'EVENT'|'ALERT';id:string}){
  const [open,setOpen]=useState(false),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[done,setDone]=useState(false);
  const {access}=useAuth();
  if(!access?.permissions.includes('locality.listings.suggest'))return null;
  if(done)return <span className="small muted">Reported. A coordinator will review it.</span>;
  if(!open)return <button className="text-link small" onClick={()=>setOpen(true)}>Report a problem</button>;
  async function send(){setBusy(true);setMessage('');try{await localityApi.report(target,id,reason);setDone(true);}catch(cause){setMessage(errorText(cause));}finally{setBusy(false);}}
  return <div className="stack mt-2">
    <TextareaField id={`report-${id}`} label="What is wrong with this?" value={reason} maxLength={500} onChange={event=>setReason(event.target.value)}/>
    {message&&<Alert tone="warning">{message}</Alert>}
    <div className="flex gap-2"><Button busy={busy} disabled={reason.trim().length<5} onClick={()=>void send()}>Send report</Button><Button variant="ghost" onClick={()=>setOpen(false)}>Cancel</Button></div>
  </div>;
}

const COLORS:Record<string,string>={pharmacy:'#0f766e',hospital_clinic:'#2563eb',police:'#1e3a8a',emergency:'#dc2626',public_service:'#7c3aed',other_service:'#b45309'};
export const categoryColor=(key:string)=>COLORS[key]??'#475569';

/**
 * Schematic coverage map drawn from stored coordinates. The locality is fictional, so a real
 * street map would place invented businesses on real streets; this draws distance from the centre only.
 */
export function CoverageMap({locality,places,selected,onSelect}:{locality:Locality;places:Place[];selected?:string|null;onSelect?:(id:string)=>void}){
  const size=360,pad=18,radius=size/2-pad;
  const {center,radius_m}=locality.coverage;
  const metresPerDegLng=111320*Math.cos(center.latitude*Math.PI/180);
  const point=(lat:number,lng:number)=>({x:size/2+((lng-center.longitude)*metresPerDegLng/radius_m)*radius,y:size/2-((lat-center.latitude)*110540/radius_m)*radius});
  const mapped=places.filter(place=>place.latitude!==null&&place.longitude!==null);
  return <figure className="m-0">
    <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Schematic map of ${locality.name}: ${mapped.length} places within ${radius_m} metres`} className="w-full max-w-[420px] mx-auto block" style={{background:'#f8fafc',borderRadius:12}}>
      <circle cx={size/2} cy={size/2} r={radius} fill="#ecfdf5" stroke="#10b981" strokeDasharray="6 4"/>
      <circle cx={size/2} cy={size/2} r={radius/2} fill="none" stroke="#a7f3d0" strokeDasharray="2 4"/>
      <text x={size/2+4} y={size/2-radius/2-4} fontSize="10" fill="#64748b">{Math.round(radius_m/2)} m</text>
      <text x={size/2+4} y={pad+12} fontSize="10" fill="#64748b">{radius_m} m</text>
      <text x={size/2} y={14} fontSize="11" fill="#64748b" textAnchor="middle">N</text>
      <rect x={size/2-6} y={size/2-6} width="12" height="12" rx="2" fill="#065f46"><title>Green Valley Residency (centre)</title></rect>
      {mapped.map(place=>{const {x,y}=point(place.latitude!,place.longitude!);const active=place.id===selected;
        return <g key={place.id} role="button" tabIndex={0} aria-label={place.name} aria-pressed={active} style={{cursor:'pointer'}} onClick={()=>onSelect?.(place.id)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onSelect?.(place.id);}}}>
          <circle cx={x} cy={y} r={active?9:6} fill={categoryColor(place.category.key)} stroke={active?'#111827':'#fff'} strokeWidth={active?3:2} opacity={place.is_stale?0.6:1}/>
          <title>{place.name} · {place.category.label}</title>
        </g>;})}
    </svg>
    <figcaption className="small muted mt-2">Schematic map: positions show distance and direction from the society, not real streets. {places.length-mapped.length>0&&`${places.length-mapped.length} listing(s) have no map location.`}</figcaption>
  </figure>;
}
