import {api} from './api';
import type {Access,Application,CreateApplication,FamilyHousehold,Flat,Household,Membership,Relationship,Tower,User,InvitationAcceptance,AdminHousehold,Pagination,MemberEvidenceRequest} from './types';
const pathId = (id:string)=>encodeURIComponent(id);
export const authApi = {
  register:(values:{display_name:string;email:string;password:string;phone?:string|null})=>api<{message:string;user:User}>('/api/auth/register',{method:'POST',body:values}),
  login:(values:{email:string;password:string})=>api<{user:User;csrf_token:string}>('/api/auth/login',{method:'POST',body:values}),
  me:()=>api<{user:User}>('/api/auth/me'),
  logout:()=>api<{message:string;csrf_token:string}>('/api/auth/logout',{method:'POST',body:{}}),
  resend:(email:string)=>api<{message:string}>('/api/auth/verification/resend',{method:'POST',body:{email}}),
  forgot:(email:string)=>api<{message:string}>('/api/auth/password/forgot',{method:'POST',body:{email}}),
  verify:(token:string)=>api<{message:string}>('/api/auth/verify-email',{method:'POST',body:{token}}),
  reset:(token:string,new_password:string)=>api<{message:string;csrf_token?:string}>('/api/auth/password/reset',{method:'POST',body:{token,new_password}}),
};
export const residentApi={
  access:()=>api<Access>('/api/me/access'),
  profile:()=>api<{user:User}>('/api/me/profile'),
  updateProfile:(p:Partial<Pick<User,'display_name'|'phone'|'date_of_birth'|'occupation'>>)=>api<{user:User}>('/api/me/profile',{method:'PATCH',body:p}),
  memberships:()=>api<{memberships:Membership[]}>('/api/me/memberships'),
  households:()=>api<{households:Household[]}>('/api/me/households'),
  familyTree:()=>api<{households:FamilyHousehold[]}>('/api/me/family-tree'),
  towers:()=>api<{towers:Tower[]}>('/api/residential/towers'),
  flats:(towerId:string)=>api<{flats:Flat[]}>(`/api/residential/towers/${pathId(towerId)}/flats`),
  flat:(flatId:string)=>api<{flat:Flat}>(`/api/residential/flats/${pathId(flatId)}`),
  society:()=>api<{society:{name:string;address:string;locality:string;city:string}}>('/api/residential/society'),
  applications:()=>api<{applications:Application[]}>('/api/membership/applications/me'),
  application:(id:string)=>api<{application:Application}>(`/api/membership/applications/${pathId(id)}`),
  create:(p:CreateApplication)=>api<{application:Application}>('/api/membership/applications',{method:'POST',body:p}),
  edit:(id:string,p:Partial<CreateApplication>&{relationship_to_sponsor?:Relationship|null})=>api<{application:Application}>(`/api/membership/applications/${pathId(id)}`,{method:'PATCH',body:p}),
  submit:(id:string)=>api<{application:Application}>(`/api/membership/applications/${pathId(id)}/submit`,{method:'POST',body:{}}),
  invite:(p:{flat_id:string;household_id?:string|null;category:'OWNER'|'TENANT'|'FAMILY_MEMBER';email:string;sponsor_membership_id?:string|null;relationship_to_sponsor?:Relationship|null})=>api<{invitation:{id:string;email:string;expires_at:string}}>('/api/invitations',{method:'POST',body:p}),
  invitations:()=>api<{invitations:Record<string,unknown>[]}>('/api/invitations/me'),
  accept:(p:{token:string;relationship_to_sponsor?:Relationship|null;declared_current_occupant?:boolean|null})=>api<InvitationAcceptance>('/api/invitations/accept',{method:'POST',body:p}),
  evidenceRequests:()=>api<{requests:MemberEvidenceRequest[]}>('/api/me/evidence-requests'),
  uploadMemberEvidence:(id:string,file:File)=>{const form=new FormData();form.set('file',file);return api<{request:MemberEvidenceRequest}>(`/api/me/evidence-requests/${pathId(id)}/upload`,{method:'POST',body:form});},
  documents:(id:string)=>api<unknown>(`/api/documents/application/${pathId(id)}`),
  upload:(p:{application_id:string;document_type:string;file:File})=>{const f=new FormData();f.set('application_id',p.application_id);f.set('document_type',p.document_type);f.set('file',p.file);return api<unknown>('/api/documents/upload',{method:'POST',body:f});},
  ocr:(id:string)=>api<unknown>(`/api/documents/${pathId(id)}/ocr`,{method:'POST',body:{}}),
  ocrHistory:(id:string)=>api<unknown>(`/api/documents/${pathId(id)}/ocr`),
};
export const adminApi={
  households:(offset=0,limit=30)=>api<{households:AdminHousehold[];pagination:Pagination}>(`/api/admin/households?limit=${limit}&offset=${offset}`),
  evidenceRequests:(offset=0,limit=20)=>api<{requests:MemberEvidenceRequest[];pagination:Pagination}>(`/api/admin/evidence-requests?limit=${limit}&offset=${offset}`),
  requestEvidence:(membershipId:string,p:{reason:string;evidence_needed:string})=>api<{request:MemberEvidenceRequest}>(`/api/admin/memberships/${pathId(membershipId)}/evidence-requests`,{method:'POST',body:p}),
  resolveEvidence:(id:string,p:{decision:'ACCEPTED'|'REJECTED'|'CANCELLED';review_note:string})=>api<{request:MemberEvidenceRequest}>(`/api/admin/evidence-requests/${pathId(id)}/resolve`,{method:'POST',body:p}),
  applications:(status:string,offset:number,limit=15)=>api<unknown>(`/api/admin/applications?limit=${limit}&offset=${offset}${status?`&status=${encodeURIComponent(status)}`:''}`),
  detail:(id:string)=>api<unknown>(`/api/admin/applications/${pathId(id)}`),
  decision:(id:string,body:{decision:'APPROVED'|'REJECTED'|'NEEDS_CORRECTION';reason?:string;document_reviewed?:boolean;acknowledge_ocr_warnings?:boolean})=>api<unknown>(`/api/admin/applications/${pathId(id)}/decision`,{method:'POST',body}),
  memberships:(status:string,offset:number,limit=15)=>api<unknown>(`/api/admin/memberships?limit=${limit}&offset=${offset}${status?`&status=${encodeURIComponent(status)}`:''}`),
  status:(id:string,status:'SUSPENDED'|'REVOKED'|'ACTIVE',reason:string)=>api<unknown>(`/api/admin/memberships/${pathId(id)}/status`,{method:'PATCH',body:{status,reason}}),
  occupancy:(id:string,is_current_occupant:boolean,reason:string)=>api<unknown>(`/api/admin/memberships/${pathId(id)}/occupancy`,{method:'PATCH',body:{is_current_occupant,reason}}),
  relationship:(id:string,relationship_to_sponsor:Relationship|null,reason:string)=>api<unknown>(`/api/admin/memberships/${pathId(id)}/relationship`,{method:'PATCH',body:{relationship_to_sponsor,reason}}),
  audit:(offset=0)=>api<unknown>(`/api/admin/audit-logs?limit=15&offset=${offset}`),
};
/** Some Phase 7/8 response JSON schemas are underspecified in OpenAPI. Inspect before rendering. */
export function asRecord(value:unknown):Record<string,unknown> {return value && typeof value==='object' && !Array.isArray(value)?value as Record<string,unknown>:{};}
export function arrayAt(value:unknown,key:string):Record<string,unknown>[] {const entries=asRecord(value)[key];return Array.isArray(entries)?entries.map(asRecord):[];}
export function str(value:unknown):string {return typeof value==='string'?value:'';}
export function num(value:unknown):number {return typeof value==='number'&&Number.isFinite(value)?value:0;}
