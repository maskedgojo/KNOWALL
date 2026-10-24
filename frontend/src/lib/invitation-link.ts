/** Accept a private emailed frontend link or its raw token; never open untrusted URLs. */
export function parseInvitationLink(input:string):{token:string;invitationId?:string}|null {
  const value=input.trim();
  if (!value || value.length>4096) return null;
  try {
    const url=new URL(value);
    if (!['http:','https:'].includes(url.protocol) || !['/invitations/accept','/invitations'].includes(url.pathname)) return null;
    const token=url.searchParams.get('token');
    if (!token || token.length>2048) return null;
    return {token,invitationId:url.searchParams.get('invitation_id')??undefined};
  } catch {
    // Token-only paste is supported for someone who copied the query value.
    return /^[A-Za-z0-9_~.+\/-]{12,2048}$/.test(value)?{token:value}:null;
  }
}
