/**
 * A routine login starts a fresh workspace. Never honor a page URL saved by a
 * previous account: it may be an administrator-only route.
 * Only an explicit, tab-scoped invitation handoff may interrupt the dashboard.
 */
export function destinationAfterLogin(roles:readonly string[], pendingInvitation:boolean):string {
  if (pendingInvitation) return '/invitations/accept';
  return roles.some(role=>role==='SOCIETY_ADMIN'||role==='PLATFORM_ADMIN')?'/admin':'/dashboard';
}

/** Protected routes do not write a return destination into ordinary logins. */
export const signedOutDestination='/login';
