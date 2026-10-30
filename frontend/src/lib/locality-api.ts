import {api} from './api';
import type {AlertInput,Category,Correction,CorrectionInput,Decision,EventInput,FeedItem,LocalAlert,LocalEvent,Locality,Page,Place,PlaceDetail,PlaceInput,Report,ShareableEvent,StaffCorrection,StaffPlaceDetail,Summary} from './locality-types';
const pathId=(id:string)=>encodeURIComponent(id);
function query(params:Record<string,string|number|undefined>){const search=new URLSearchParams();for(const [key,value] of Object.entries(params))if(value!==undefined&&value!=='')search.set(key,String(value));const text=search.toString();return text?`?${text}`:'';}

/** Resident-facing Module 4 routes: Flask checks locality.read / locality.listings.suggest. */
export const localityApi={
  profile:()=>api<{locality:Locality}>('/api/locality/profile'),
  categories:()=>api<{categories:Category[]}>('/api/locality/categories'),
  places:(params:{q?:string; category?:string; limit?:number; offset?:number}={})=>api<{places:Place[]; total:number; pagination:Page}>(`/api/locality/places${query({limit:100,...params})}`),
  place:(id:string)=>api<PlaceDetail>(`/api/locality/places/${pathId(id)}`),
  reportCorrection:(placeId:string,body:CorrectionInput)=>api<{correction:Correction}>(`/api/locality/places/${pathId(placeId)}/corrections`,{method:'POST',body}),
  reportMissing:(body:CorrectionInput)=>api<{correction:Correction}>('/api/locality/corrections',{method:'POST',body}),
  myCorrections:()=>api<{corrections:Correction[]}>('/api/locality/corrections/me'),
  respond:(id:string,body:{message:string}&Partial<CorrectionInput>)=>api<{correction:Correction}>(`/api/locality/corrections/${pathId(id)}/respond`,{method:'POST',body}),
  events:(when:'upcoming'|'past'='upcoming',category='')=>api<{events:LocalEvent[]}>(`/api/locality/events${query({when,category})}`),
  myEvents:()=>api<{events:LocalEvent[]}>('/api/locality/events/mine'),
  submitEvent:(body:EventInput)=>api<{event:LocalEvent}>('/api/locality/events/submit',{method:'POST',body}),
  shareable:()=>api<{events:ShareableEvent[]}>('/api/locality/events/shareable'),
  shareSocietyEvent:(source_event_id:string,category:string)=>api<{event:LocalEvent}>('/api/locality/events/submit',{method:'POST',body:{source_event_id,category}}),
  alerts:()=>api<{active:LocalAlert[]; scheduled:LocalAlert[]; past:LocalAlert[]}>('/api/locality/alerts'),
  feed:()=>api<{pinned:FeedItem[]; items:FeedItem[]}>('/api/locality/feed'),
  report:(target_type:'EVENT'|'ALERT',target_id:string,reason:string)=>api<{report:{id:string; status:string}}>('/api/locality/reports',{method:'POST',body:{target_type,target_id,reason}}),
};

/** Coordinator routes: Flask requires locality.manage (LOCALITY_COORDINATOR only). */
export const localityAdminApi={
  summary:()=>api<{summary:Summary}>('/api/locality/admin/summary'),
  updateProfile:(body:Partial<{name:string; description:string; center_latitude:number; center_longitude:number; coverage_radius_m:number; stale_after_days:number}>)=>api<{locality:Locality}>('/api/locality/admin/profile',{method:'PATCH',body}),
  places:(params:{q?:string; category?:string; state?:string}={})=>api<{places:Place[]; total:number; pagination:Page}>(`/api/locality/admin/places${query({limit:100,...params})}`),
  place:(id:string)=>api<StaffPlaceDetail>(`/api/locality/admin/places/${pathId(id)}`),
  createPlace:(body:PlaceInput)=>api<{place:Place}>('/api/locality/admin/places',{method:'POST',body}),
  updatePlace:(id:string,body:PlaceInput&{expected_version:number; note?:string})=>api<{place:Place}>(`/api/locality/admin/places/${pathId(id)}`,{method:'PATCH',body}),
  verifyPlace:(id:string,body:{method:string; note:string; source_url?:string})=>api<{place:Place}>(`/api/locality/admin/places/${pathId(id)}/verify`,{method:'POST',body}),
  markStale:(id:string,reason:string)=>api<{place:Place}>(`/api/locality/admin/places/${pathId(id)}/mark-stale`,{method:'POST',body:{reason}}),
  archivePlace:(id:string,reason:string)=>api<{place:Place}>(`/api/locality/admin/places/${pathId(id)}/archive`,{method:'POST',body:{reason}}),
  restorePlace:(id:string,reason:string)=>api<{place:Place}>(`/api/locality/admin/places/${pathId(id)}/restore`,{method:'POST',body:{reason}}),
  corrections:(status='')=>api<{corrections:StaffCorrection[]; total:number; pagination:Page}>(`/api/locality/admin/corrections${query({status,limit:100})}`),
  correction:(id:string)=>api<{correction:StaffCorrection}>(`/api/locality/admin/corrections/${pathId(id)}`),
  decideCorrection:(id:string,decision:Decision,reason:string)=>api<{correction:StaffCorrection}>(`/api/locality/admin/corrections/${pathId(id)}/decision`,{method:'POST',body:{decision,reason}}),
  events:(status='')=>api<{events:LocalEvent[]}>(`/api/locality/admin/events${query({status})}`),
  decideEvent:(id:string,decision:'PUBLISH'|'REJECT'|'ARCHIVE',reason:string)=>api<{event:LocalEvent}>(`/api/locality/admin/events/${pathId(id)}/decision`,{method:'POST',body:{decision,reason}}),
  alerts:()=>api<{alerts:LocalAlert[]}>('/api/locality/admin/alerts'),
  createAlert:(body:AlertInput)=>api<{alert:LocalAlert}>('/api/locality/admin/alerts',{method:'POST',body}),
  publishAlert:(id:string)=>api<{alert:LocalAlert}>(`/api/locality/admin/alerts/${pathId(id)}/publish`,{method:'POST',body:{}}),
  archiveAlert:(id:string,reason:string)=>api<{alert:LocalAlert}>(`/api/locality/admin/alerts/${pathId(id)}/archive`,{method:'POST',body:{reason}}),
  reports:(status='')=>api<{reports:Report[]}>(`/api/locality/admin/reports${query({status})}`),
  decideReport:(id:string,decision:'DISMISS'|'ARCHIVE_CONTENT',reason:string)=>api<unknown>(`/api/locality/admin/reports/${pathId(id)}/decision`,{method:'POST',body:{decision,reason}}),
};
