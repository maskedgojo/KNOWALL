import {arrayAt,asRecord,num,str} from '@/lib/endpoints';
/** Phase 8 OpenAPI gives untyped JSON for queue/document/admin responses. These adapters intentionally never synthesize records. */
export function records(data:unknown,key:string){return arrayAt(data,key)}
export function pager(data:unknown){const page=asRecord(asRecord(data).pagination);return {total:typeof page.total==='number'?num(page.total):null,limit:num(page.limit)||15,offset:num(page.offset)}}
export function flatText(value:unknown){const v=asRecord(value);return [str(v.tower_name),str(v.flat_number)].filter(Boolean).join(' · ')||'Not available'}
export function applicantName(value:Record<string,unknown>){const a=asRecord(value.applicant);const u=asRecord(value.user);return str(a.display_name)||str(a.name)||str(u.display_name)||str(value.applicant_name)||'Applicant';}
export function documentList(value:unknown){const d=asRecord(value);const app=asRecord(d.application);return Array.isArray(d.documents)?arrayAt(d,'documents'):arrayAt(app,'documents')}
export function reviewList(value:unknown){const d=asRecord(value);const app=asRecord(d.application);return Array.isArray(d.reviews)?arrayAt(d,'reviews'):arrayAt(app,'reviews')}
