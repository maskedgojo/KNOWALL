import {api, ApiError} from './api';
import type {CivicCategory, CivicHandoffRecord, CivicIssue, CivicList, CivicLocality, CivicPrivacy, CivicReport, CivicSeverity, CivicState, CivicTimeline, ConcernType, EvidenceVisibility, ReportDisposition, SimilarIssue} from './civic-types';

const pathId=(id:string)=>encodeURIComponent(id);

export interface IssueInput {title:string; description:string; category:CivicCategory; severity:CivicSeverity; latitude:number; longitude:number; address_hint:string; privacy:CivicPrivacy}
export interface ListFilters {mine?:boolean; category?:string; severity?:string; state?:string; q?:string; sort?:'recent'|'support'|'priority'; limit?:number; offset?:number}

function query(params:Record<string,string|number|boolean|undefined>){
  const search=new URLSearchParams();
  for(const [key,value] of Object.entries(params)) if(value!==undefined&&value!=='') search.set(key,String(value));
  const text=search.toString();return text?`?${text}`:'';
}

/** Resident-facing civic API. Flask decides every permission; the UI only hides what it cannot use. */
export const civicApi={
  locality:()=>api<{locality:CivicLocality}>('/api/civic/locality'),
  list:(filters:ListFilters={})=>api<CivicList>(`/api/civic/issues${query({...filters,mine:filters.mine?'true':undefined})}`),
  get:(id:string)=>api<{issue:CivicIssue}>(`/api/civic/issues/${pathId(id)}`),
  timeline:(id:string)=>api<CivicTimeline>(`/api/civic/issues/${pathId(id)}/timeline`),
  similar:(p:{category:CivicCategory; lat:number; lon:number; title?:string; excludeId?:string})=>api<{similar:SimilarIssue[]; radius_m:number; note:string}>(`/api/civic/issues/similar${query({category:p.category,lat:p.lat,lon:p.lon,title:p.title,exclude_id:p.excludeId})}`),
  create:(body:IssueInput&{save_as_draft?:boolean})=>api<{issue:CivicIssue; similar:SimilarIssue[]}>('/api/civic/issues',{method:'POST',body}),
  edit:(id:string,body:Partial<IssueInput>)=>api<{issue:CivicIssue}>(`/api/civic/issues/${pathId(id)}`,{method:'PATCH',body}),
  submit:(id:string,note?:string)=>api<{issue:CivicIssue}>(`/api/civic/issues/${pathId(id)}/submit`,{method:'POST',body:note?{note}:{}}),
  withdraw:(id:string)=>api<{issue:CivicIssue}>(`/api/civic/issues/${pathId(id)}`,{method:'DELETE',body:{}}),
  support:(id:string)=>api<{support_count:number; viewer_has_supported:boolean}>(`/api/civic/issues/${pathId(id)}/support`,{method:'POST',body:{}}),
  unsupport:(id:string)=>api<{support_count:number; viewer_has_supported:boolean}>(`/api/civic/issues/${pathId(id)}/support`,{method:'DELETE',body:{}}),
  report:(id:string,concern_type:ConcernType,concern:string)=>api<{report:{id:string; status:string}}>(`/api/civic/issues/${pathId(id)}/report`,{method:'POST',body:{concern_type,concern}}),
  uploadEvidence:(id:string,file:File,caption='',visibility:EvidenceVisibility='PRIVATE')=>{
    const form=new FormData();form.append('file',file);form.append('visibility',visibility);if(caption)form.append('caption',caption);
    return api<{evidence:{id:string}}>(`/api/civic/issues/${pathId(id)}/evidence`,{method:'POST',body:form});
  },
  removeEvidence:(id:string,evidenceId:string)=>api<{removed:boolean}>(`/api/civic/issues/${pathId(id)}/evidence/${pathId(evidenceId)}`,{method:'DELETE',body:{}}),
};

/** Coordinator-only civic API (Flask requires the shared admin grant). */
export const civicAdminApi={
  queue:(state?:CivicState)=>api<CivicList>(`/api/civic/admin/issues${query({state,limit:100})}`),
  review:(id:string)=>api<{issue:CivicIssue}>(`/api/civic/admin/issues/${pathId(id)}/review`,{method:'POST',body:{}}),
  validate:(id:string,body:{note?:string; severity?:CivicSeverity})=>api<{issue:CivicIssue}>(`/api/civic/admin/issues/${pathId(id)}/validate`,{method:'POST',body}),
  needsInfo:(id:string,reason:string)=>api<{issue:CivicIssue}>(`/api/civic/admin/issues/${pathId(id)}/needs-info`,{method:'POST',body:{reason}}),
  reject:(id:string,reason:string)=>api<{issue:CivicIssue}>(`/api/civic/admin/issues/${pathId(id)}/reject`,{method:'POST',body:{reason}}),
  merge:(id:string,body:{canonical_issue_id:string; reason:string; acknowledge_distance?:boolean})=>api<{duplicate:CivicIssue; canonical:CivicIssue}>(`/api/civic/admin/issues/${pathId(id)}/merge`,{method:'POST',body}),
  route:(id:string)=>api<{handoff:CivicHandoffRecord; issue:CivicIssue}>(`/api/civic/issues/${pathId(id)}/route`,{method:'POST',body:{}}),
  acknowledge:(id:string,authority_case_id:string)=>api<{handoff:CivicHandoffRecord}>(`/api/civic/issues/${pathId(id)}/handoff/acknowledge`,{method:'POST',body:{authority_case_id}}),
  setEvidenceVisibility:(evidenceId:string,visibility:EvidenceVisibility)=>api<{evidence:{id:string; visibility:string}}>(`/api/civic/admin/evidence/${pathId(evidenceId)}/visibility`,{method:'POST',body:{visibility}}),
  reports:(status:'OPEN'|'RESOLVED'='OPEN')=>api<{reports:CivicReport[]}>(`/api/civic/admin/reports?status=${status}`),
  resolveReport:(id:string,disposition:ReportDisposition,note:string)=>api<{report:CivicReport}>(`/api/civic/admin/reports/${pathId(id)}/resolve`,{method:'POST',body:{disposition,note}}),
};

/** Private evidence photo through Flask; the caller revokes the returned object URL. */
export async function civicEvidenceFile(id:string):Promise<{url:string; type:string}>{
  let response:Response;
  try{response=await fetch(`/api/civic/evidence/${pathId(id)}/file`,{credentials:'same-origin',cache:'no-store'});}
  catch{throw new ApiError(0,'NETWORK','Could not download this photo.');}
  if(!response.ok) throw new ApiError(response.status,'EVIDENCE_UNAVAILABLE','Photo unavailable or access denied.');
  const blob=await response.blob();
  const bytes=new Uint8Array(await blob.slice(0,8).arrayBuffer());
  const png=bytes[0]===0x89&&bytes[1]===0x50&&bytes[2]===0x4e&&bytes[3]===0x47;
  const jpeg=bytes[0]===0xff&&bytes[1]===0xd8&&bytes[2]===0xff;
  if(!png&&!jpeg) throw new ApiError(415,'UNSUPPORTED_MEDIA','This file is not a supported image.');
  const type=png?'image/png':'image/jpeg';
  return {url:URL.createObjectURL(new Blob([blob],{type})),type};
}
