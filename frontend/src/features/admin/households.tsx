'use client';
import {useState} from 'react';
import {adminApi} from '@/lib/endpoints';
import {Alert,Badge,Button,Card,EmptyState,ErrorState,Loading,PageHeading} from '@/components/ui';
import {occupancy,pretty,shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import type {AdminHouseholdMember} from '@/lib/types';
const LIMIT=20;
function Member({member}: {member:AdminHouseholdMember}){
 return <div className="family-tile">
  <div className="family-avatar" aria-hidden="true">{member.display_name?.slice(0,1).toUpperCase()||'?'}</div>
  <div className="min-w-0 flex-1">
   <div className="between"><strong>{member.display_name}</strong><Badge value={member.membership_status}/></div>
   <div className="small muted">{pretty(member.category)} · Access: {pretty(member.access_state)}</div>
   {member.category==='FAMILY_MEMBER'&&<div className="small mt-2">{member.relationship_to_sponsor?`${pretty(member.relationship_to_sponsor)} of `:'Relationship not declared · Sponsor: '}{member.sponsor_display_name??'Sponsor not available'}</div>}
   <div className="small muted mt-2">Occupancy: {occupancy(member.is_current_occupant)} · Self-declared: {occupancy(member.declared_current_occupant)}</div>
   <div className="small muted">Valid: {shortDate(member.valid_from)} — {shortDate(member.valid_until)}</div>
  </div>
 </div>;
}
export default function AdminHouseholds(){
 const [offset,setOffset]=useState(0);
 const load=useLoad(()=>adminApi.households(offset,LIMIT),[offset]);
 const households=load.value?.households??[];
 const total=load.value?.pagination?.total;
 return <>
  <PageHeading eyebrow="ADMINISTRATION / DIRECTORY" title="Household directory" description="Actual households and linked sponsors from Flask. Separate households sharing a flat stay separate." action={<Button variant="secondary" onClick={load.refresh}>Refresh records</Button>}/>
  <div className="mb-5"><Alert tone="info">Family relationships are declared by household members; membership is not a legal certificate of relationship, proof of occupancy, or voting eligibility. Sensitive contact information and private evidence are excluded.</Alert></div>
  {load.loading?<Loading label="Loading household directory…"/>:load.error?<ErrorState error={load.error} onRetry={load.refresh}/>:households.length? <div className="stack-sm">
   {households.map(h=><Card key={h.household_id}>
    <div className="card-head"><div><h2 className="card-title">{h.household_label}</h2><p className="small muted mt-1">{h.flat?.tower_name} · Flat {h.flat?.flat_number}</p></div><Badge value={`${h.members?.length??0} members`}/></div>
    <div className="grid-2">{(h.members??[]).map(m=><Member key={m.membership_id} member={m}/>)}</div>
   </Card>)}
  </div>:<EmptyState title="No households in this page" description="No eligible records were returned from Flask."/>}
  <div className="form-actions"><Button variant="secondary" disabled={load.loading||offset===0} onClick={()=>setOffset(x=>Math.max(0,x-LIMIT))}>Previous</Button><span className="small muted">{typeof total==='number'?`${Math.min(offset+1,total)}–${Math.min(offset+households.length,total)} of ${total}`:`Offset ${offset}`}</span><Button variant="secondary" disabled={load.loading||(typeof total==='number'?offset+LIMIT>=total:households.length<LIMIT)} onClick={()=>setOffset(x=>x+LIMIT)}>Next</Button></div>
 </>;
}
