'use client';
import {useState} from 'react';
import Link from 'next/link';
import {residentApi} from '@/lib/endpoints';
import {Alert,Badge,Button,Card,EmptyState,ErrorState,Loading,PageHeading} from '@/components/ui';
import {shortDate} from '@/lib/format';
import {useLoad,errorText} from '@/lib/use-load';
import {MemberEvidencePreview} from './private-evidence-preview';
import type {MemberEvidenceRequest} from '@/lib/types';
const MAX_BYTES=5*1024*1024;
const FILE_TYPES=['image/png','image/jpeg','application/pdf'];
function Request({item,onDone}:{item:MemberEvidenceRequest;onDone:()=>void}){
 const [file,setFile]=useState<File|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[success,setSuccess]=useState('');
 async function upload(e:React.FormEvent){e.preventDefault();if(!file||busy)return;
  if(!FILE_TYPES.includes(file.type)){setError('Choose a PDF, PNG or JPG document.');return;}
  if(file.size>MAX_BYTES){setError('Maximum permitted document size is 5 MiB.');return;}
  setBusy(true);setError('');setSuccess('');
  try{await residentApi.uploadMemberEvidence(item.id,file);setFile(null);setSuccess('Your private file was received by Flask. Await administrator review.');onDone();}catch(e){setError(errorText(e));}finally{setBusy(false);}
 }
 return <Card className="mb-4"><div className="card-head"><div><h2 className="card-title">Additional information request</h2><p className="small muted mt-1">Issued {shortDate(item.created_at??'')}</p></div><Badge value={item.status}/></div>
  <div className="info-list"><div className="info-row"><span>Reason</span><strong>{item.reason}</strong></div><div className="info-row"><span>Requested evidence</span><strong>{item.evidence_needed}</strong></div></div>
  {item.status==='REQUESTED'&&<form className="form-stack mt-4" onSubmit={e=>void upload(e)}><label className="field" htmlFor={`file-${item.id}`}><span className="field-title">Upload evidence privately (PDF, PNG or JPG; up to 5 MiB)</span><input className="input" id={`file-${item.id}`} type="file" accept="application/pdf,image/png,image/jpeg" onChange={e=>setFile(e.target.files?.[0]??null)}/></label>
   <Alert tone="info">Share only the minimum evidence necessary. A pending request does not automatically suspend your household membership. Documents are private and are not sent to OCR automatically.</Alert>
   {error&&<Alert tone="danger">{error}</Alert>}{success&&<Alert tone="success">{success}</Alert>}
   <div className="form-actions"><Button type="submit" busy={busy} disabled={!file}>Send supporting document</Button></div></form>}
  {item.status!=='REQUESTED'&&<div className="mt-4"><Alert tone={item.status==='REJECTED'?'warning':'info'}>{item.status==='SUBMITTED'?'Your document was submitted. Administrator review is pending.':item.status==='ACCEPTED'?'The administrator accepted the supplied evidence.':item.status==='REJECTED'?'The administrator did not accept the supplied evidence. Contact your society administrator if clarification is needed.':'The document request has been cancelled.'}</Alert></div>}
  {(item.status==='SUBMITTED'||item.status==='ACCEPTED'||item.status==='REJECTED')&&item.document&&<div className="mt-3"><MemberEvidencePreview requestId={item.id}/></div>}
 </Card>;
}
export default function ResidentEvidenceRequests(){const load=useLoad(()=>residentApi.evidenceRequests(),[]);const items=load.value?.requests??[];
 return <><PageHeading eyebrow="RESIDENT PORTAL / PRIVATE REQUESTS" title="Evidence requests" description="Additional information requested specifically for your membership. No routine family documentation is required." action={<Button variant="secondary" onClick={load.refresh}>Refresh</Button>}/>
 {load.loading?<Loading/>:load.error?<ErrorState error={load.error} onRetry={load.refresh}/>:items.length?items.map(i=><Request key={i.id} item={i} onDone={load.refresh}/>):<EmptyState title="No evidence requests" description="Your society administrator has not requested any extra documentation."/>}
 <p className="small muted mt-4">Only authorized administrators can request or review private evidence. <Link href="/household" className="text-link">Return to household</Link>.</p>
 </>;
}
