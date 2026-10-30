/* eslint-disable @next/next/no-img-element -- session-scoped blob URLs cannot use Next image optimization */
'use client';
import {useEffect,useState} from 'react';
import {privateMemberEvidence} from '@/lib/api';
import {errorText} from '@/lib/use-load';
import {Alert,Button} from '@/components/ui';
import {Icon} from '@/components/icons';
/** An authenticated and revocable object URL, never a public document link. */
export function MemberEvidencePreview({requestId}:{requestId:string}){
 const [file,setFile]=useState<{url:string;type:string}|null>(null);
 const [loading,setLoading]=useState(false),[error,setError]=useState('');
 useEffect(()=>()=>{if(file)URL.revokeObjectURL(file.url);},[file]);
 async function open(){setLoading(true);setError('');try{setFile(await privateMemberEvidence(requestId));}catch(e){setError(errorText(e));}finally{setLoading(false);}}
 return <div className="stack-sm">
  <div className="row-flex"><Button variant="secondary" busy={loading} type="button" onClick={()=>void open()}><Icon name="eye" size={16}/>Open private evidence</Button>{file&&<a className="btn btn-ghost" href={file.url} download={`knowall-member-evidence-${requestId.slice(0,8)}`}>Download</a>}</div>
  {error&&<Alert tone="danger">{error}</Alert>}
  {file&&<div className="document-frame">{file.type.startsWith('image/')?<img src={file.url} alt="Privately supplied member evidence"/>:file.type==='application/pdf'?<iframe title="Private member evidence PDF" src={file.url} referrerPolicy="no-referrer"/>:<p className="small muted p-6">This file cannot be previewed in the browser. Use Download to inspect it.</p>}</div>}
 </div>;
}
