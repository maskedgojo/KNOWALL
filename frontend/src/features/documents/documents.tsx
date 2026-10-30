/* eslint-disable @next/next/no-img-element -- private session-fetched blob URLs cannot use Next image optimization */
'use client';
import {useEffect,useRef,useState} from 'react';
import {ApiError,privateFile} from '@/lib/api';
import {arrayAt,residentApi,str} from '@/lib/endpoints';
import {pretty,shortDate} from '@/lib/format';
import {errorText,useLoad} from '@/lib/use-load';
import {latestOcr,ocrSummary,type OcrView} from '@/lib/ocr-view';
import {Alert,Badge,Button,Card,EmptyState,ErrorState,Field,Loading,SelectField} from '@/components/ui';
import {Icon} from '@/components/icons';

const MAX_BYTES=5*1024*1024;
const RECOVERY_CHECKS=18; // Best-effort GET-only reconciliation for slow CPU inference.
const RECOVERY_INTERVAL_MS=5000;

function describeError(error:unknown):string {
  if (error instanceof ApiError) {
    const status=error.status?`HTTP ${error.status}`:'Connection interrupted';
    return `${status}${error.code&&!error.code.startsWith('HTTP_')?` (${error.code})`:''}: ${error.message}`;
  }
  return errorText(error);
}
function wait(ms:number,signal:AbortSignal):Promise<void>{
  return new Promise((resolve,reject)=>{
    if(signal.aborted){reject(new DOMException('Cancelled','AbortError'));return;}
    const onAbort=()=>{clearTimeout(timer);reject(new DOMException('Cancelled','AbortError'));};
    const timer=setTimeout(()=>{signal.removeEventListener('abort',onAbort);resolve();},ms);
    signal.addEventListener('abort',onAbort,{once:true});
  });
}
function isTerminal(status:string){return status==='COMPLETED'||status==='FAILED';}

/** Only backend-supplied comparison fields are shown. Raw OCR text and JSON are not dumped into the UI. */
export function OcrFindings({data,warnings,title='Document comparison'}:{data:unknown;warnings?:unknown;title?:string}){
  const view=latestOcr(data,warnings);
  if(!view)return <div className="ocr-placeholder" role="status">No saved OCR findings are available for this document.</div>;
  const totals=ocrSummary(view);
  return <section className="ocr-results" aria-label={title}>
    <div className="ocr-results-head">
      <div><h3>{title}</h3><p className="small muted">Information entered in KNOWALL compared with what Surya read from the document.</p></div>
      <Badge value={view.status}/>
    </div>
    {view.status==='COMPLETED'&&view.comparisons.length>0&&<div className="ocr-counts" aria-label="Comparison summary">
      <span className="ocr-count ocr-count-match"><Icon name="check" size={15}/>{totals.matched} matched</span>
      <span className="ocr-count ocr-count-mismatch"><Icon name="alert" size={15}/>{totals.mismatched} different</span>
      {totals.unconfirmed>0&&<span className="ocr-count">{totals.unconfirmed} need checking</span>}
    </div>}
    {view.status==='FAILED'&&<Alert tone="warning">Text extraction failed{view.errorMessage?`: ${view.errorMessage}`:'.'} The original evidence is still available for manual review.</Alert>}
    {view.status==='PROCESSING'&&<Alert tone="info">Flask is still processing this document. You can check saved results again shortly.</Alert>}
    {view.status==='COMPLETED'&&view.comparisons.length===0&&<Alert tone="info">OCR completed, but the backend did not return any field comparisons. The document still requires manual review.</Alert>}
    {view.comparisons.length>0&&<div className="ocr-comparison-list">
      <div className="ocr-column-head" aria-hidden="true"><span>Field</span><span>Application</span><span>Document</span><span>Result</span></div>
      {view.comparisons.map(row=><div className={`ocr-comparison-row ${row.status==='MISMATCH'?'ocr-row-mismatch':''}`} key={row.field}>
        <span className="ocr-field-name">{row.label}</span>
        <span className="ocr-cell"><span className="ocr-mobile-label">Application</span>{row.entered}</span>
        <span className="ocr-cell"><span className="ocr-mobile-label">Document</span>{row.extracted}</span>
        <span className="ocr-cell"><span className={`ocr-result-tag ${row.status==='MATCH'?'ocr-tag-match':row.status==='MISMATCH'?'ocr-tag-mismatch':'ocr-tag-unknown'}`}>{row.status==='MATCH'?<><Icon name="check" size={13}/>Matches</>:row.status==='MISMATCH'?<><Icon name="alert" size={13}/>Different</>:'Check manually'}</span></span>
      </div>)}
    </div>}
    {view.warnings.length>0&&<div className="ocr-warnings"><strong>Review warnings</strong><ul>{view.warnings.map((warning,index)=><li key={`${index}-${warning}`}>{warning}</li>)}</ul></div>}
    <p className="ocr-caution"><Icon name="shield" size={15}/> OCR compares text only. A match does not establish document authenticity or approve a membership.</p>
  </section>;
}

/** Private file bytes are fetched with the Flask session. The direct download URL is never opened for preview. */
export function PrivatePreview({id,filename,onOpened}:{id:string;filename?:string;onOpened?:()=>void}){
  const [preview,setPreview]=useState<{url:string;type:string}|null>(null);
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(false);
  const supported=preview?.type==='image/png'||preview?.type==='image/jpeg'||preview?.type==='application/pdf';
  useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview.url);},[preview]);
  async function open(){
    setLoading(true);setError('');
    try {
      const next=await privateFile(id);
      setPreview(next);
      if(['image/png','image/jpeg','application/pdf'].includes(next.type))onOpened?.();
    } catch(e){setError(describeError(e));}
    finally{setLoading(false);}
  }
  const baseName=filename?.split(/[\\/]/).pop()?.replace(/[^a-zA-Z0-9._-]/g,'_') || `knowall-evidence-${id.slice(0,8)}`;
  return <div className="stack-sm">
    <div className="row-flex">
      <Button variant="secondary" busy={loading} onClick={()=>void open()}><Icon name="eye" size={16}/>Preview original</Button>
      {preview&&<>
        {supported&&<a className="btn btn-ghost" href={preview.url} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer"><Icon name="eye" size={16}/>Open in new tab</a>}
        <a className="btn btn-ghost" href={preview.url} download={baseName}>Download</a>
      </>}
    </div>
    {error&&<Alert tone="danger">{error}</Alert>}
    {preview&&<div className="document-frame">
      {preview.type.startsWith('image/')?<img src={preview.url} alt="Privately uploaded residence evidence"/>:
        preview.type==='application/pdf'?<iframe title="Private residence evidence PDF" src={preview.url} referrerPolicy="no-referrer"/>:
        <div className="p-6 text-center small muted">The original was retrieved, but it is not a supported inline image or PDF. Use Download to inspect it.</div>}
    </div>}
  </div>;
}

export function DocumentsPanel({applicationId,editable=false}:{applicationId:string;editable?:boolean}){
  const docs=useLoad(()=>residentApi.documents(applicationId),[applicationId]);
  const [file,setFile]=useState<File|null>(null);
  const [type,setType]=useState('');
  const [busy,setBusy]=useState(false);
  const [processing,setProcessing]=useState('');
  const [error,setError]=useState('');
  const [success,setSuccess]=useState('');
  const [recoveryMessage,setRecoveryMessage]=useState('');
  const [history,setHistory]=useState<{id:string;value:unknown}|null>(null);
  const recoveryController=useRef<AbortController|null>(null);
  useEffect(()=>()=>{recoveryController.current?.abort();},[]);
  const entries=arrayAt(docs.value,'documents');

  async function upload(event:React.FormEvent){
    event.preventDefault();
    if(!file){setError('Choose a file.');return;}
    if(!['application/pdf','image/png','image/jpeg'].includes(file.type)){setError('Only PDF, JPG or PNG files are allowed.');return;}
    if(file.size>MAX_BYTES){setError('Maximum upload size is 5 MB.');return;}
    setBusy(true);setError('');setSuccess('');
    try {
      await residentApi.upload({application_id:applicationId,document_type:type.trim(),file});
      setFile(null);setType('');docs.refresh();setSuccess('Your private evidence was uploaded.');
    }catch(e){setError(describeError(e));}
    finally{setBusy(false);}
  }

  async function loadOCR(id:string){
    if(processing)return;
    setProcessing(id);setError('');setRecoveryMessage('');
    try {
      const value=await residentApi.ocrHistory(id);
      setHistory({id,value});
      const view=latestOcr(value);
      if(!view)setRecoveryMessage('No OCR result has been saved yet.');
    }catch(e){setError(`Could not load the saved OCR results: ${describeError(e)}`);}
    finally{setProcessing('');}
  }

  async function runOCR(id:string){
    if(processing)return;
    const controller=new AbortController();recoveryController.current=controller;
    setProcessing(id);setError('');setSuccess('');setRecoveryMessage('');
    // Baseline prevents an earlier completed OCR run being mistaken for a new run.
    let previousId=history?.id===id?latestOcr(history.value)?.id:null;
    if(!previousId){try{previousId=latestOcr(await residentApi.ocrHistory(id))?.id??null;}catch{/* OCR can still start when there is no prior history. */}}
    if(controller.signal.aborted)return;
    setHistory(null);
    let postError:unknown=null;
    try{await residentApi.ocr(id);}catch(e){postError=e;}
    if(controller.signal.aborted)return;
    // A proxy disconnect does not prove that Flask stopped processing. Query the saved
    // result instead of repeating this non-idempotent POST.
    const statusUnknown=postError instanceof ApiError && [0,409,500,502,503,504].includes(postError.status);
    const checks=statusUnknown?RECOVERY_CHECKS:1;
    let resolved:OcrView|null=null;
    let fetchProblem:unknown=null;
    try{
      if(statusUnknown)setRecoveryMessage('The request was interrupted or returned an uncertain status. Checking saved OCR results without starting another run…');
      for(let i=0;i<checks;i++){
        if(controller.signal.aborted)return;
        try{
          const value=await residentApi.ocrHistory(id);
          if(controller.signal.aborted)return;
          setHistory({id,value});
          resolved=latestOcr(value);
          fetchProblem=null;
          if(resolved&&isTerminal(resolved.status))break;
        }catch(e){fetchProblem=e;}
        if(i<checks-1)await wait(RECOVERY_INTERVAL_MS,controller.signal);
      }
      if(controller.signal.aborted)return;
      setRecoveryMessage('');
      if(resolved?.status==='COMPLETED'){
        const {mismatched}=ocrSummary(resolved);
        if(postError&&previousId&&resolved.id===previousId) {
          setRecoveryMessage('A previous completed OCR result is available below, but the latest request could not be confirmed. No duplicate OCR run was started.');
        } else {
          setSuccess(mismatched>0?`Saved OCR result completed: ${mismatched} field${mismatched===1?' is':'s are'} different. Administrator review is required.`:'Saved OCR result completed. Check the comparisons below; manual review is still required.');
        }
      }else if(resolved?.status==='FAILED'){
        setError(`The backend saved a failed OCR result${resolved.errorMessage?`: ${resolved.errorMessage}`:'.'} The original file remains available.`);
      }else if(postError){
        setError(`${describeError(postError)}. No completed result was confirmed. Select “View OCR results” later before deciding whether to run OCR again.`);
      }else if(fetchProblem){
        setError(`Flask responded to the OCR request, but saved results could not be retrieved: ${describeError(fetchProblem)}. Use “View OCR results” before rerunning.`);
      }else{
        setRecoveryMessage('OCR has not reported completion yet. Use “View OCR results” to check again; avoid submitting duplicate runs.');
      }
      docs.refresh();
    }catch(e){if(!(e instanceof Error&&e.name==='AbortError'))setError(`Unable to check saved OCR results: ${describeError(e)}`);}
    finally{if(!controller.signal.aborted){setProcessing('');recoveryController.current=null;}}
  }

  return <Card>
    <div className="card-head"><div><h2 className="card-title"><Icon name="file"/>Private evidence & OCR</h2><p className="small muted mt-2">Only authorized accounts can access uploaded documents.</p></div><Badge value={`${entries.length} files`}/></div>
    <div className="mb-5"><Alert tone="warning">OCR reads document text and highlights differences. A human administrator must still verify the evidence.</Alert></div>
    {error&&<div className="mb-3"><Alert tone="danger">{error}</Alert></div>}
    {success&&<div className="mb-3"><Alert tone="success">{success}</Alert></div>}
    {recoveryMessage&&<div className="mb-3"><Alert tone="info">{recoveryMessage}</Alert></div>}
    {!!processing&&!recoveryMessage&&<div className="mb-3"><Alert tone="info">Working with Flask. Surya OCR may take several minutes on CPU. Please do not start a duplicate run.</Alert></div>}
    {docs.loading?<Loading/>:docs.error?<ErrorState error={docs.error} onRetry={docs.refresh}/>:entries.length?
      entries.map(document=>{
        const id=str(document.id);
        const filename=str(document.original_filename)||str(document.filename)||str(document.document_type)||`Document ${id.slice(0,8)}`;
        return <div className="notice-card mb-3" key={id}>
          <div className="between"><div><strong>{filename}</strong><div className="small muted mt-1">{pretty(str(document.document_type))}{document.created_at?` · ${shortDate(str(document.created_at))}`:''}</div></div>{typeof document.status==='string'&&<Badge value={document.status}/>}</div>
          <div className="mt-3"><PrivatePreview id={id} filename={filename}/></div>
          <div className="row-flex mt-3">
            <Button variant="secondary" busy={processing===id} disabled={!!processing} onClick={()=>void loadOCR(id)}>View OCR comparisons</Button>
            {editable&&<Button busy={processing===id} disabled={!!processing} onClick={()=>void runOCR(id)}><Icon name="scan" size={16}/>Run Surya OCR</Button>}
          </div>
          {history?.id===id&&<div className="mt-4"><OcrFindings data={history.value}/></div>}
        </div>;
      }):<EmptyState title="No documents uploaded" description="Only you and authorized administrators can inspect uploaded original evidence."/>}
    {editable&&<form onSubmit={upload} className="form-stack mt-5 border-t border-slate-200 pt-5">
      <h3>Upload supporting evidence</h3>
      <SelectField id="doc-type" label="Document type" required value={type} onChange={e=>setType(e.target.value)}>
        <option value="">Choose supporting evidence</option><option value="RENTAL_AGREEMENT">Rental agreement</option><option value="OCCUPANCY_LETTER">Occupancy letter</option><option value="OTHER_RESIDENCE_EVIDENCE">Other residence evidence</option>
      </SelectField>
      <Field id="doc-file" label="Evidence file (PDF, JPG or PNG, up to 5 MB; PDF max 3 pages)" type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" onChange={e=>setFile(e.target.files?.[0]??null)} required/>
      <div className="form-actions"><Button type="submit" busy={busy}><Icon name="upload" size={16}/>Upload securely</Button></div>
    </form>}
  </Card>;
}
