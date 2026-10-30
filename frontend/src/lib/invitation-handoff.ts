/**
 * Invite token handoff for navigation through login/email verification.
 * Session storage is scoped to one browser tab: NOT a cookie/auth session,
 * never localStorage, and cleared after successful acceptance or expiry.
 * We strip the token query immediately on the first client render.
 */
const KEY = 'knowall:invitation-pending-v2';
const TTL = 24 * 60 * 60 * 1000;
type Pending = {token: string; recordedAt: number; invitationId?: string};

function read(): Pending | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const v: unknown = JSON.parse(raw);
    if (typeof v !== 'object' || v === null) return null;
    const p = v as Partial<Pending>;
    if (typeof p.token !== 'string' || !p.token || typeof p.recordedAt !== 'number' ||
      Date.now() - p.recordedAt > TTL || p.recordedAt > Date.now()) {
      sessionStorage.removeItem(KEY);
      return null;
    }
    return {token:p.token,recordedAt:p.recordedAt,invitationId:typeof p.invitationId==='string'?p.invitationId:undefined};
  } catch { return null; }
}
export function rememberInvitation(token:string, invitationId?:string): void {
  if (typeof window === 'undefined' || !token) return;
  try {sessionStorage.setItem(KEY,JSON.stringify({token,invitationId,recordedAt:Date.now()}));}catch{
    // Restricted browser storage: the token remains in component state until navigation.
  }
}
export function pendingInvitation(): {token:string;invitationId?:string} | null {
  const item=read();return item?{token:item.token,invitationId:item.invitationId}:null;
}
export function hasPendingInvitation():boolean{return !!pendingInvitation();}
export function clearPendingInvitation():void {if(typeof window!=='undefined')try{sessionStorage.removeItem(KEY)}catch{}}
/** Capture both the new /invitations/accept link and legacy /invitations?token link. */
export function captureInvitationLink(): {token:string;invitationId?:string}|null {
  if (typeof window==='undefined') return null;
  const url=new URL(window.location.href);
  const token=url.searchParams.get('token');
  const invitationId=url.searchParams.get('invitation_id')??undefined;
  if (token) {
    rememberInvitation(token,invitationId);
    url.searchParams.delete('token');
    url.searchParams.delete('invitation_id');
    window.history.replaceState(window.history.state,'',url.pathname+url.search+url.hash);
    return {token,invitationId};
  }
  return pendingInvitation();
}
