/** Same-origin Flask client. No JWT, Next.js auth, persistent token store, or mutation auto-retry. */
import type { ApiProblem } from './types';
let csrfToken: string | null = null;
let pendingToken: Promise<string> | null = null;
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public fields: Record<string,string> = {}) {super(message); this.name = 'ApiError';}
}
export function adoptCsrf(value: unknown) { if (typeof value === 'string' && value) csrfToken = value; }
export function clearCsrf() {csrfToken = null; pendingToken = null;}
export async function refreshCsrf():Promise<string> {
  if (!pendingToken) {
    pendingToken = (async () => {
      let response:Response;
      try {response = await fetch('/api/auth/csrf', {credentials:'same-origin',cache:'no-store'});} catch {throw new ApiError(0,'NETWORK','Cannot reach the backend. Check your connection.');}
      if (!response.ok) throw new ApiError(response.status,'CSRF_FETCH_FAILED','Could not initialize a secure session.');
      const result: {csrf_token?:unknown} = await response.json();
      if (typeof result.csrf_token !== 'string' || !result.csrf_token) throw new ApiError(0,'BAD_RESPONSE','Invalid CSRF response from the backend.');
      csrfToken=result.csrf_token; return csrfToken;
    })().finally(()=>{pendingToken=null;});
  }
  return pendingToken;
}
export type RequestOptions = {method?:'GET'|'POST'|'PATCH'|'DELETE'; body?:unknown; signal?:AbortSignal; headers?:HeadersInit; csrfRetry?:boolean};
const mutating = (method:string) => ['POST','PUT','PATCH','DELETE'].includes(method);
export async function api<T>(path:string, options:RequestOptions={}):Promise<T> {
  if (!path.startsWith('/api/')) throw new Error('Only relative /api/* routes are allowed');
  const method=options.method ?? 'GET';
  const headers=new Headers(options.headers);
  headers.set('Accept','application/json');
  if (mutating(method)) headers.set('X-CSRF-Token',csrfToken ?? await refreshCsrf());
  const isForm = options.body instanceof FormData;
  if (options.body !== undefined && !isForm) headers.set('Content-Type','application/json');
  let response:Response;
  try {
    response=await fetch(path,{method,headers,body:options.body===undefined?undefined:isForm?(options.body as FormData):JSON.stringify(options.body),credentials:'same-origin',cache:'no-store',signal:options.signal,redirect:'follow'});
  } catch (cause) {
    if (cause instanceof Error && cause.name==='AbortError') throw cause;
    throw new ApiError(0,'NETWORK','Network connection interrupted. Check that Flask is running.');
  }
  const ct=response.headers.get('content-type') ?? '';
  const data:unknown=ct.includes('application/json')?await response.json().catch(()=>null):null;
  if (!response.ok) {
    const error=(data && typeof data==='object' && 'error' in data ? (data as ApiProblem).error:undefined);
    if (response.status===403 && error?.code==='CSRF_REQUIRED') {
      clearCsrf();
      const refreshed = await refreshCsrf().then(()=>true).catch(()=>false);
      // Signing out is safe to repeat. Other mutations stay single-attempt so a stale token cannot submit twice.
      if (refreshed && path === '/api/auth/logout' && !options.csrfRetry) return api(path, {...options, csrfRetry:true});
    }
    if (response.status===401 && typeof window!=='undefined') window.dispatchEvent(new Event('knowall:session-expired'));
    const route = path.split('?')[0];
    const collectionMiss = response.status === 404 && !error?.message && /^\/api\/(?:discussions|suggestions|polls|disputes|proposals|governance\/history|admin\/community\/(?:discussions|suggestions|polls|proposals))$/.test(route);
    const messages:Record<number,string>={400:'Please check the information submitted.',401:'Your session has expired. Please sign in again.',403:'You do not have access to this action.',404: collectionMiss ? 'The running Flask server does not have this route yet. Restart Flask so it loads the current Module 2 routes. This is not a missing record.' : 'This record was not found or is no longer accessible.',409:'This request conflicts with the current record state. Review the status before retrying.',413:'The uploaded file exceeds the allowed size.',415:'Unsupported file type.',429:'Too many requests. Please try later.',500:'Flask encountered an internal error. Check the Flask terminal for the server traceback.',502:'The frontend proxy did not receive a valid response from Flask.',503:'A required backend dependency is unavailable. If this is a new Module 2 page, its database migration may not be applied yet.',504:'The request timed out. Check Flask before starting another OCR run.'};
    throw new ApiError(response.status,error?.code ?? `HTTP_${response.status}`,error?.message ?? messages[response.status] ?? 'The request could not be completed.',error?.fields ?? {});
  }
  // Adopt ONLY CSRF values returned by Flask after auth lifecycle transitions.
  if (['/api/auth/login','/api/auth/logout','/api/auth/password/reset'].includes(path) && data && typeof data==='object' && 'csrf_token' in data) adoptCsrf((data as {csrf_token:unknown}).csrf_token);
  return data as T;
}
/** Privacy-safe file fetch: no public URLs, short-lived object URL, caller must revoke. */
export function privateFile(id:string):Promise<{url:string;type:string}> {
  return fetchPrivateFile(`/api/documents/${encodeURIComponent(id)}/file`);
}
/** Private exceptional-member evidence; never expose a static/public URL. */
export function privateMemberEvidence(id:string):Promise<{url:string;type:string}> {
  return fetchPrivateFile(`/api/member-evidence/${encodeURIComponent(id)}/file`);
}
/** Module 3 ticket/milestone photo; Flask checks who may view it. */
export function privateOperationPhoto(id:string):Promise<{url:string;type:string}> {
  return fetchPrivateFile(`/api/operations/photos/${encodeURIComponent(id)}/file`);
}
async function fetchPrivateFile(path:string):Promise<{url:string;type:string}> {
  let response:Response;
  try {response=await fetch(path,{credentials:'same-origin',cache:'no-store'});}catch{throw new ApiError(0,'NETWORK','Could not download this private document.');}
  if (!response.ok) throw new ApiError(response.status,'DOCUMENT_UNAVAILABLE','Document unavailable or access denied.');
  const blob=await response.blob();
  // Flask deliberately serves originals with Content-Disposition: attachment and may
  // return application/octet-stream. Inspect file signatures before enabling an inline
  // viewer; never treat an arbitrary HTML/SVG response as trusted displayable media.
  const signature=new Uint8Array(await blob.slice(0,12).arrayBuffer());
  const matches=(bytes:number[])=>bytes.every((value,index)=>signature[index]===value);
  const mime=matches([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a])?'image/png'
    :matches([0xff,0xd8,0xff])?'image/jpeg'
    :matches([0x25,0x50,0x44,0x46,0x2d])?'application/pdf'
    :'application/octet-stream';
  // A new object URL made from the inspected bytes has inline-capable MIME metadata.
  // It is never a public Flask/static URL and must be revoked by the caller.
  const safeBlob=new Blob([blob],{type:mime});
  return {url:URL.createObjectURL(safeBlob),type:mime};
}
