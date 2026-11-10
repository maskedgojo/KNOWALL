import {api, ApiError} from './api';
import type {AuthorityMe, CaseDetail, CaseList, CaseNotification, CaseStatus, CaseTracker, CivicAnalytics, Department, EvidenceType, IntakeItem, ResolutionEvidence, Verdict} from './authority-types';

const id=(value:string)=>encodeURIComponent(value);
type CaseResponse={case:CaseDetail; simulation_notice:string};

/** Module 6 API. Flask enforces department scope and coordinator rights; the UI only hides what it cannot use. */
export const authorityApi={
  me:()=>api<AuthorityMe>('/api/authority/me'),
  departments:()=>api<{departments:Department[]}>('/api/authority/departments'),
  list:(filters:{status?:CaseStatus; overdue?:boolean; department_id?:number}={})=>{
    const search=new URLSearchParams({limit:'100'});
    if(filters.status)search.set('status',filters.status);
    if(filters.overdue)search.set('overdue','true');
    if(filters.department_id)search.set('department_id',String(filters.department_id));
    return api<CaseList>(`/api/authority/cases?${search}`);
  },
  get:(caseId:string)=>api<CaseResponse>(`/api/authority/cases/${id(caseId)}`),
  acknowledge:(caseId:string,note?:string)=>api<CaseResponse>(`/api/authority/cases/${id(caseId)}/acknowledge`,{method:'POST',body:note?{note}:{}}),
  transfer:(caseId:string,to_department_id:number,reason:string)=>api<CaseResponse>(`/api/authority/cases/${id(caseId)}/transfer`,{method:'POST',body:{to_department_id,reason}}),
  progress:(caseId:string,body:{message:string; public_summary?:string; revised_due_at?:string})=>api<CaseResponse>(`/api/authority/cases/${id(caseId)}/progress`,{method:'POST',body}),
  uploadEvidence:(caseId:string,file:File,evidence_type:EvidenceType,caption='')=>{
    const form=new FormData();form.append('file',file);form.append('evidence_type',evidence_type);if(caption)form.append('caption',caption);
    return api<{evidence:ResolutionEvidence}>(`/api/authority/cases/${id(caseId)}/evidence`,{method:'POST',body:form});
  },
  resolve:(caseId:string,summary:string)=>api<CaseResponse>(`/api/authority/cases/${id(caseId)}/resolve`,{method:'POST',body:{summary}}),
  requestClarification:(caseId:string,question:string)=>api<CaseResponse>(`/api/authority/cases/${id(caseId)}/request-clarification`,{method:'POST',body:{question}}),
  // Resident actions
  caseStatus:(issueId:string)=>api<{case:CaseTracker|null; canonical_issue_id:string; simulation_notice:string}>(`/api/civic/issues/${id(issueId)}/case-status`),
  verify:(caseId:string,verdict:Verdict,reason:string,photo?:File|null)=>{
    if(photo){const form=new FormData();form.append('verdict',verdict);form.append('reason',reason);form.append('photo',photo);
      return api<{case:CaseTracker; outcome:string|null}>(`/api/authority/cases/${id(caseId)}/verify`,{method:'POST',body:form});}
    return api<{case:CaseTracker; outcome:string|null}>(`/api/authority/cases/${id(caseId)}/verify`,{method:'POST',body:{verdict,reason}});
  },
  respondClarification:(caseId:string,response:string)=>api<{case:CaseTracker}>(`/api/authority/cases/${id(caseId)}/respond-clarification`,{method:'POST',body:{response}}),
  notifications:()=>api<{notifications:CaseNotification[]; unread:number}>('/api/authority/notifications'),
  markRead:(notificationId:string)=>api<{id:string; read_at:string}>(`/api/authority/notifications/${id(notificationId)}/read`,{method:'POST',body:{}}),
};

/** Coordinator-only Module 6 API. */
export const authorityAdminApi={
  intakeQueue:()=>api<{handoffs:IntakeItem[]}>('/api/authority/intake-queue'),
  intake:(canonical_issue_id:string,department_id?:number,note?:string)=>api<{case:CaseDetail; created:boolean}>('/api/authority/cases/intake',{method:'POST',body:{canonical_issue_id,...(department_id?{department_id}:{}),...(note?{note}:{})}}),
  escalate:(caseId:string,reason:string)=>api<CaseResponse>(`/api/authority/cases/${id(caseId)}/escalate`,{method:'POST',body:{reason,acknowledge_simulated:true}}),
  reopen:(caseId:string,reason:string)=>api<CaseResponse>(`/api/authority/cases/${id(caseId)}/reopen`,{method:'POST',body:{reason}}),
  close:(caseId:string,reason:string)=>api<CaseResponse>(`/api/authority/cases/${id(caseId)}/close`,{method:'POST',body:{reason}}),
  assignOfficer:(email:string,department_id:number,title:string)=>api<{officer:{id:string}}>('/api/authority/admin/officers',{method:'POST',body:{email,department_id,title}}),
  revokeOfficer:(officerId:string)=>api<{revoked:boolean}>(`/api/authority/admin/officers/${id(officerId)}`,{method:'DELETE',body:{}}),
  sweep:()=>api<{report:{escalated:number; closed:number; reopened:number; awaiting_coordinator:number}}>('/api/authority/admin/sweep',{method:'POST',body:{}}),
  analytics:()=>api<CivicAnalytics>('/api/admin/analytics/civic'),
};

/** Private photo through Flask (official proof, reporter photo or dispute photo). The caller revokes the URL. */
export async function authorityFile(path:string):Promise<{url:string; type:string}>{
  if(!path.startsWith('/api/authority/'))throw new Error('Only authority file routes are allowed');
  let response:Response;
  try{response=await fetch(path,{credentials:'same-origin',cache:'no-store'});}
  catch{throw new ApiError(0,'NETWORK','Could not download this photo.');}
  if(!response.ok)throw new ApiError(response.status,'EVIDENCE_UNAVAILABLE','Photo unavailable or access denied.');
  const blob=await response.blob();
  const bytes=new Uint8Array(await blob.slice(0,8).arrayBuffer());
  const png=bytes[0]===0x89&&bytes[1]===0x50&&bytes[2]===0x4e&&bytes[3]===0x47;
  const jpeg=bytes[0]===0xff&&bytes[1]===0xd8&&bytes[2]===0xff;
  if(!png&&!jpeg)throw new ApiError(415,'UNSUPPORTED_MEDIA','This file is not a supported image.');
  const type=png?'image/png':'image/jpeg';
  return {url:URL.createObjectURL(new Blob([blob],{type})),type};
}
export const proofPath=(evidenceId:string)=>`/api/authority/evidence/${id(evidenceId)}/file`;
export const reporterPhotoPath=(caseId:string,evidenceId:string)=>`/api/authority/cases/${id(caseId)}/issue-evidence/${id(evidenceId)}/file`;
export const disputePhotoPath=(verificationId:string)=>`/api/authority/verifications/${id(verificationId)}/photo`;
