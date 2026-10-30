'use client';

import {useCallback,useState} from 'react';
import Link from 'next/link';
import {adminApi,asRecord,str} from '@/lib/endpoints';
import {documentList,reviewList,applicantName,flatText} from './helpers';
import {AdminEvidence,type OcrReviewState} from './review-evidence';
import {FamilySponsorPanel} from './family-sponsor-panel';
import {sponsorFromApplicationDetail,sponsorReviewStatus} from '@/lib/family-review';
import {Alert,Badge,Button,Card,ErrorState,Loading,PageHeading,SelectField,TextareaField} from '@/components/ui';
import {useLoad,errorText} from '@/lib/use-load';
import {pretty,shortDate} from '@/lib/format';
import {Icon} from '@/components/icons';

type Decision='APPROVED'|'REJECTED'|'NEEDS_CORRECTION';

export default function AdminReview({id}:{id:string}) {
  const load=useLoad(()=>adminApi.detail(id),[id]);
  const [opened,setOpened]=useState<string[]>([]);
  const [ocrState,setOcrState]=useState<Record<string,OcrReviewState>>({});
  const [ack,setAck]=useState(false);
  const [reviewed,setReviewed]=useState(false);
  const [familyReviewed,setFamilyReviewed]=useState(false);
  const [decision,setDecision]=useState<Decision>('NEEDS_CORRECTION');
  const [reason,setReason]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');

  const app=asRecord(asRecord(load.value).application);
  const familyApplication=str(app.category)==='FAMILY_MEMBER';
  const sponsor=familyApplication?sponsorFromApplicationDetail(load.value):null;
  const sponsorReady=sponsorReviewStatus(sponsor)==='ELIGIBLE';
  const docs=documentList(load.value).filter(d=>Boolean(str(d.id)));
  const reviews=reviewList(load.value);
  const isEvidenceRequired=app.evidence_required===true;
  const docsReady=docs.every(doc=>ocrState[str(doc.id)]?.loaded===true);
  const allOpened=docs.length>0&&docs.every(doc=>opened.includes(str(doc.id)));
  const mismatchCount=docs.reduce((sum,doc)=>sum+(ocrState[str(doc.id)]?.mismatches??0),0);
  const warningCount=docs.reduce((sum,doc)=>sum+(ocrState[str(doc.id)]?.warnings??0),0);

  const onOpened=useCallback((docId:string)=>{
    setOpened(current=>current.includes(docId)?current:[...current,docId]);
  },[]);
  const onOcrState=useCallback((docId:string,state:OcrReviewState)=>{
    // A refreshed result must be acknowledged again, never inherit a stale review checkbox.
    setAck(false);
    setOcrState(current=>{
      const existing=current[docId];
      if(existing?.loaded===state.loaded&&existing?.mismatches===state.mismatches&&existing?.warnings===state.warnings)return current;
      return {...current,[docId]:state};
    });
  },[]);

  async function act(event:React.FormEvent) {
    event.preventDefault();setError('');setMessage('');
    if(decision!=='APPROVED'&&!reason.trim()){
      setError('A clear reviewer reason is required.');return;
    }
    if(decision==='APPROVED'){
      if(familyApplication&&!sponsorReady){setError('The linked family sponsor must be resolved and eligible in the Flask review response before approval.');return;}
      if(familyApplication&&!familyReviewed){setError('Review and acknowledge the sponsor identity, same-household link and relationship before approval.');return;}
      if(isEvidenceRequired&&!allOpened){setError('Open every uploaded original evidence file before approval.');return;}
      if(docs.length&&!docsReady){setError('OCR history for every document must load before you can approve. Use Refresh in the OCR panel.');return;}
      if(isEvidenceRequired&&!reviewed){setError('Confirm that you manually reviewed all original evidence.');return;}
      if(docs.length&&!ack){setError('Read and acknowledge the OCR comparisons and warnings before approval.');return;}
      if((mismatchCount||warningCount)&&!reason.trim()){
        setError('Explain how you resolved the OCR mismatches or warnings before approving.');return;
      }
    }
    if(!window.confirm(`Confirm ${pretty(decision)}? Flask will record an audited human decision.`))return;
    setBusy(true);
    try{
      await adminApi.decision(id,{
        decision,
        reason:reason.trim()||undefined,
        document_reviewed:reviewed,
        acknowledge_ocr_warnings:ack,
      });
      setMessage(`Flask recorded the ${pretty(decision)} decision.`);
      setReason('');
      load.refresh();
    }catch(e){setError(errorText(e));}
    finally{setBusy(false);}
  }

  return <>
    <PageHeading eyebrow="ADMINISTRATION / HUMAN REVIEW" title="Application verification" description={`Reference ${id.slice(0,8).toUpperCase()} · Manual evidence review required`} action={<Link href="/admin/applications" className="btn btn-secondary"><Icon name="back" size={15}/>Back to queue</Link>}/>
    {load.loading?<Loading/>:load.error?<ErrorState error={load.error} onRetry={load.refresh}/>:<>
      <div className="mb-5"><Alert tone="warning">Surya OCR is advisory. Compare the submitted claims with the original evidence and resolve any mismatches before making a human decision.</Alert></div>
      <Card className="mb-5">
        <div className="card-head"><h2 className="card-title">Applicant and residence</h2><Badge value={str(app.status)}/></div>
        <div className="admin-review-summary">
          <div><span>Applicant</span><strong>{applicantName(app)}</strong></div>
          <div><span>Flat</span><strong>{flatText(app.flat)}</strong></div>
          <div><span>Category</span><strong>{pretty(str(app.category))}</strong></div>
          <div><span>Submitted</span><strong>{shortDate(str(app.submitted_at))}</strong></div>
          <div><span>Self-declared occupancy</span><strong>{app.declared_current_occupant===true?'Yes':app.declared_current_occupant===false?'No':'Unknown / Not verified'}</strong></div>
          {familyApplication&&<div><span>Relationship to sponsor</span><strong>{pretty(str(app.relationship_to_sponsor))}</strong></div>}
        </div>
        {str(app.applicant_notes)&&<div className="mt-4"><h3>Applicant notes</h3><p className="small muted mt-2 whitespace-pre-line">{str(app.applicant_notes)}</p></div>}
      </Card>

      {familyApplication&&<FamilySponsorPanel sponsor={sponsor} relationship={str(app.relationship_to_sponsor)}/>}

      <div className="mb-3 between"><div><h2 className="card-title">Evidence review workspace</h2><p className="small muted mt-2">The original and actual saved OCR comparisons are shown side-by-side for each document.</p></div><span className="badge badge-neutral">{docs.length} file{docs.length===1?'':'s'}</span></div>
      {docs.length?docs.map(doc=><AdminEvidence key={str(doc.id)} document={doc} sponsor={sponsor} isFamily={familyApplication} onOpened={onOpened} onOcrState={onOcrState}/>):
        <Card><Alert tone="warning">No evidence is included in the Flask response. Do not approve an application requiring residence evidence.</Alert></Card>}

      <div className="grid-2 section-space">
        <Card>
          <h2 className="card-title mb-4">Human reviewer decision</h2>
          {mismatchCount>0&&<div className="mb-3"><Alert tone="warning">{mismatchCount} mismatch{mismatchCount===1?'':'es'} across uploaded documents. An approval requires a written resolution.</Alert></div>}
          {!docsReady&&docs.length>0&&<div className="mb-3"><Alert tone="info">Loading OCR history. Wait for the comparison panels before recording an approval.</Alert></div>}
          {error&&<div className="mb-3"><Alert tone="danger">{error}</Alert></div>}
          {message&&<div className="mb-3"><Alert tone="success">{message}</Alert></div>}
          <form onSubmit={act} className="form-stack">
            <SelectField id="decision" label="Decision" value={decision} onChange={e=>setDecision(e.target.value as Decision)}><option value="NEEDS_CORRECTION">Request corrections</option><option value="REJECTED">Reject application</option><option value="APPROVED">Approve application</option></SelectField>
            <TextareaField id="reason" label={decision==='APPROVED'?(mismatchCount||warningCount?'Resolution notes (required)':'Review notes (optional)'):'Reviewer reason (required)'} required={decision!=='APPROVED'||!!(mismatchCount||warningCount)} value={reason} onChange={e=>setReason(e.target.value)} placeholder="Explain the original evidence examined and your decision rationale"/>
            <label className="row-flex small"><input type="checkbox" checked={reviewed} disabled={!allOpened} onChange={e=>setReviewed(e.target.checked)}/> I personally inspected all original evidence and completed manual verification.</label>
            {familyApplication&&<label className="row-flex small"><input type="checkbox" checked={familyReviewed} disabled={!sponsorReady} onChange={e=>setFamilyReviewed(e.target.checked)}/> I checked the verified sponsor identity, household/flat binding and family relationship separately from the OCR name comparison.</label>}
            <label className="row-flex small"><input type="checkbox" checked={ack} disabled={!docsReady||docs.length===0} onChange={e=>setAck(e.target.checked)}/> I reviewed the saved OCR comparisons and acknowledge any warnings shown by Flask.</label>
            <Alert tone="info">Originals opened: {opened.filter(id=>docs.some(doc=>str(doc.id)===id)).length}/{docs.length} · OCR histories loaded: {docs.filter(doc=>ocrState[str(doc.id)]?.loaded).length}/{docs.length}. The Flask backend independently enforces authorization and review requirements.</Alert>
            <div className="form-actions"><Button type="submit" busy={busy} variant={decision==='REJECTED'?'danger':'primary'}>Record human decision</Button></div>
          </form>
        </Card>
        <Card><h2 className="card-title mb-4">Review history</h2>{reviews.length?reviews.map((r,i)=><div className="notice-card mb-3" key={str(r.id)||i}><div className="between"><strong>{pretty(str(r.decision)||str(r.status))}</strong><span className="small muted">{shortDate(str(r.created_at))}</span></div><p className="muted small mt-2">{str(r.reason)||'No reviewer comment'}</p></div>):<div className="empty"><h3>No review entries in this response</h3><p>Review history is populated only from Flask.</p></div>}</Card>
      </div>
    </>}
  </>;
}
