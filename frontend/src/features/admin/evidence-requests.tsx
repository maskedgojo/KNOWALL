'use client';
import {useState} from 'react';
import {adminApi} from '@/lib/endpoints';
import {Alert,Badge,Button,Card,EmptyState,ErrorState,Loading,PageHeading,SelectField,TextareaField} from '@/components/ui';
import {shortDate} from '@/lib/format';
import {useLoad,errorText} from '@/lib/use-load';
import {MemberEvidencePreview} from '@/features/evidence/private-evidence-preview';
import type {MemberEvidenceRequest} from '@/lib/types';
const LIMIT=20;
type Decision='ACCEPTED'|'REJECTED'|'CANCELLED';
function Review({item,onDone}:{item:MemberEvidenceRequest;onDone:()=>void}){
 const [action,setAction]=useState<Decision>(item.status==='SUBMITTED'?'ACCEPTED':'CANCELLED');
 const [note,setNote]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[success,setSuccess]=useState('');
 const actionable=item.status==='REQUESTED'||item.status==='SUBMITTED';
 async function resolve(e:React.FormEvent){e.preventDefault();if(!actionable||busy)return;
  if(item.status==='REQUESTED'&&action!=='CANCELLED'){setError('An unsubmitted request can only be cancelled.');return;}
  if(item.status==='SUBMITTED'&&action==='CANCELLED'){setError('Submitted evidence must be accepted or rejected.');return;}
  if(note.trim().length<3){setError('Give a clear audit note explaining the decision.');return;}
  if(!window.confirm('Confirm this recorded evidence decision? This action will be audited.'))return;
  setBusy(true);setError('');setSuccess('');
  try{await adminApi.resolveEvidence(item.id,{decision:action,review_note:note.trim()});setSuccess('Flask confirmed the decision.');onDone();}catch(e){setError(errorText(e));}finally{setBusy(false);}
 }
 return <Card className="mb-4">
  <div className="card-head"><div><h2 className="card-title">Member evidence request</h2><p className="small muted mt-1">Membership {item.membership_id.slice(0,8)}… · Issued {shortDate(item.created_at??'')}</p></div><Badge value={item.status}/></div>
  <div className="info-list"><div className="info-row"><span>Reason</span><strong>{item.reason}</strong></div><div className="info-row"><span>Requested evidence</span><strong>{item.evidence_needed}</strong></div></div>
  {item.status==='SUBMITTED'&&<div className="mt-4"><h3 className="card-title mb-3">Submitted private evidence</h3><MemberEvidencePreview requestId={item.id}/></div>}
  {item.status==='REQUESTED'&&<div className="mt-3"><Alert tone="info">Awaiting the member&apos;s upload. Membership access is not changed by this request.</Alert></div>}
  {actionable&&<form className="form-stack mt-4" onSubmit={e=>void resolve(e)}>
   <SelectField id={`decision-${item.id}`} label="Review decision" value={action} onChange={e=>setAction(e.target.value as Decision)}>{item.status==='REQUESTED'?<option value="CANCELLED">Cancel request</option>:<><option value="ACCEPTED">Accept evidence</option><option value="REJECTED">Reject evidence</option></>}</SelectField>
   <TextareaField id={`note-${item.id}`} label="Audit note (required)" value={note} onChange={e=>setNote(e.target.value)} maxLength={1200} required placeholder="Record your reason for this decision; avoid copying sensitive document text."/>
   {error&&<Alert tone="danger">{error}</Alert>}{success&&<Alert tone="success">{success}</Alert>}
   <div className="form-actions"><Button type="submit" busy={busy}>Record evidence decision</Button></div>
  </form>}
  {!actionable&&<div className="mt-3"><p className="small muted">This request is closed. Resolution does not automatically change a resident&apos;s membership status.</p>{item.retention_deadline&&<p className="small muted">Scheduled evidence retention deadline: {shortDate(item.retention_deadline)}</p>}</div>}
 </Card>;
}
export default function AdminEvidenceRequests(){
 const [offset,setOffset]=useState(0);const load=useLoad(()=>adminApi.evidenceRequests(offset,LIMIT),[offset]);const rows=load.value?.requests??[];const total=load.value?.pagination?.total;
 return <><PageHeading eyebrow="ADMINISTRATION / EXCEPTIONAL EVIDENCE" title="Evidence request reviews" description="Review additional evidence only when an administrator has recorded a specific reason." action={<Button variant="secondary" onClick={load.refresh}>Refresh requests</Button>}/>
  <div className="mb-5"><Alert tone="info">Family memberships activate through eligible sponsorship. Evidence requests are exceptional, private, audited and never cause automatic suspension. No OCR is run for these files.</Alert></div>
  {load.loading?<Loading label="Loading requests…"/>:load.error?<ErrorState error={load.error} onRetry={load.refresh}/>:rows.length?rows.map(r=><Review key={r.id} item={r} onDone={load.refresh}/>):<EmptyState title="No requests on this page" description="Requests will appear here when an administrator creates them."/>}
  <div className="form-actions"><Button variant="secondary" onClick={()=>setOffset(x=>Math.max(0,x-LIMIT))} disabled={offset===0||load.loading}>Previous</Button><span className="small muted">{typeof total==='number'?`${Math.min(offset+rows.length,total)} of ${total}`:`Offset ${offset}`}</span><Button variant="secondary" onClick={()=>setOffset(x=>x+LIMIT)} disabled={load.loading||(typeof total==='number'?offset+LIMIT>=total:rows.length<LIMIT)}>Next</Button></div>
 </>;
}
