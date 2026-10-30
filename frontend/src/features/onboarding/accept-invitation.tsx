'use client';
import {useEffect,useMemo,useState} from 'react';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {useAuth} from '@/components/auth-provider';
import {PublicShell,AuthCard} from '@/components/shell';
import {Alert,Badge,Button,Loading,SelectField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {residentApi} from '@/lib/endpoints';
import {pretty,shortDate} from '@/lib/format';
import {acceptancePayload,invitationState,parseInvitations,type InvitationSummary} from '@/lib/invitation-model';
import {captureInvitationLink,clearPendingInvitation} from '@/lib/invitation-handoff';
import {errorText} from '@/lib/use-load';
import type {Flat,Relationship} from '@/lib/types';

const relationships:Relationship[]=['SPOUSE','CHILD','PARENT','SIBLING','GRANDPARENT','GRANDCHILD','OTHER'];

export default function AcceptInvitation(){
 const router=useRouter(),session=useAuth();
 const [token,setToken]=useState('');
 const [hintId,setHintId]=useState<string|undefined>();
 const [loadedToken,setLoadedToken]=useState(false);
 const [list,setList]=useState<InvitationSummary[]|null>(null);
 const [loadingList,setLoadingList]=useState(false);
 const [listError,setListError]=useState('');
 const [selectedId,setSelectedId]=useState('');
 const [flat,setFlat]=useState<Flat|null>(null);
 const [relationship,setRelationship]=useState<Relationship|''>('');
 const [occupancy,setOccupancy]=useState<'unknown'|'yes'|'no'>('unknown');
 const [submitting,setSubmitting]=useState(false);
 const [error,setError]=useState('');
 const [accepted,setAccepted]=useState<string|null>(null);
 const [activated,setActivated]=useState(false);
 const [refreshKey,setRefreshKey]=useState(0);

 // Capture token once, remove it from location/address bar, preserve it through login in
 // sessionStorage for this tab only. No URL containing the token is used after capture.
 useEffect(()=>{
   const t=captureInvitationLink();
   Promise.resolve().then(()=>{setToken(t?.token??'');setHintId(t?.invitationId);setLoadedToken(true);});
 },[]);

 useEffect(()=>{
   if(session.loading || !session.user?.email_verified || !token || accepted || activated) return;
   let active=true;
   void Promise.resolve().then(async()=>{
     setLoadingList(true);setListError('');setList(null);
     try{
       const response=await residentApi.invitations();
       if(active) setList(parseInvitations(response));
     }catch(e){if(active)setListError(errorText(e));}
     finally{if(active)setLoadingList(false);}
   });
   return ()=>{active=false;};
 },[session.loading,session.user?.email_verified,session.user?.email,token,refreshKey,accepted,activated]);

 const matches=useMemo(()=>list?.filter(inv=>!inv.email || inv.email.toLowerCase()===session.user?.email.toLowerCase())??[],[list,session.user?.email]);
 const active=useMemo(()=>matches.filter(inv=>invitationState(inv)==='ACTIVE'),[matches]);
 const chosen=useMemo(()=>selectedId?active.find(inv=>inv.id===selectedId):(hintId?active.find(inv=>inv.id===hintId):(active.length===1?active[0]:undefined)),[active,selectedId,hintId]);

 useEffect(()=>{
   if(!chosen?.flat_id)return;
   let active=true;
   void residentApi.flat(chosen.flat_id).then(result=>{if(active)setFlat(result.flat);}).catch(()=>{if(active)setFlat(null);});
   return()=>{active=false;setFlat(null);};
 },[chosen?.flat_id]);

 const next='/invitations/accept';
 function handleError(e:unknown){
   if(e instanceof ApiError){
     if(e.code==='INVALID_OR_EXPIRED_TOKEN'||(e.status===400 && e.code.includes('TOKEN'))){
       clearPendingInvitation();setToken('');setError('This link is invalid, expired or already used. Ask the sender for a new invitation.');return;
     }
     if(e.status===403 && e.code==='CSRF_REQUIRED'){setError('Your security token expired. It has been refreshed. Check the invitation details, then select Accept again.');return;}
     if(e.code==='EMAIL_VERIFICATION_REQUIRED'){setError('Verify the email address that received this invitation before accepting it.');return;}
     if(e.code==='INVITATION_EMAIL_MISMATCH'){setError('This invitation belongs to another verified email address. Sign in using the email that received it.');return;}
     if(e.code==='RELATIONSHIP_REQUIRED'){setError('Choose your relationship to the household sponsor to continue.');return;}
     if(e.code==='SPONSOR_INELIGIBLE'||e.code==='HOUSEHOLD_MISMATCH'){setError('The sponsoring membership is no longer eligible for this household. Ask the sponsor or society administrator for help.');return;}
     if(e.code==='ALREADY_A_RESIDENT'||e.code==='MEMBERSHIP_CONFLICT'||e.code==='APPLICATION_ALREADY_OPEN'){setError('You already have a membership or an open application that conflicts with this invitation. Review your dashboard and applications.');return;}
     if(e.code==='INVALID_INVITATION'){setError('This invitation is invalid, expired or used. Ask for a new invitation.');clearPendingInvitation();setToken('');return;}
     if(e.status===403){setError('Flask could not authorize this invitation. Confirm that you signed in using the exact verified email that received the link, then try again. '+e.message);return;}
     if(e.status===409){setError('This invitation is no longer actionable or conflicts with an existing application. Check your applications before trying again. '+e.message);return;}
   }
   setError(errorText(e));
 }
 async function recoverAfterUncertainResult(invitationId:string){
   try{
     const response=await residentApi.applications();
     const match=response.applications.find(a=>a.invitation_id===invitationId);
     if(match?.id)return match.id;
   }catch{}
   return null;
 }
 async function submit(e:React.FormEvent){
   e.preventDefault();if(!token||!chosen||!session.user?.email_verified||submitting)return;
   if(chosen.category==='FAMILY_MEMBER'&&!relationship&&!chosen.relationship_to_sponsor){setError('Select your relationship to the household sponsor.');return;}
   setError('');setSubmitting(true);
   try{
     const response=await residentApi.accept(acceptancePayload(token,chosen.category,chosen.category==='FAMILY_MEMBER'?(relationship||chosen.relationship_to_sponsor) as Relationship:null,occupancy));
     if(response.outcome==='FAMILY_MEMBERSHIP_ACTIVATED') {
       if(!response.membership?.id || response.membership.status!=='ACTIVE')
         throw Error('Flask returned family activation without a valid active membership. Refresh your membership page before trying anything again.');
       clearPendingInvitation();setToken('');setActivated(true);
       // Flask creates the membership. Fetch canonical session/access/memberships again;
       // never award resident access or fabricate a membership in React state.
       await Promise.allSettled([session.refresh(),residentApi.memberships()]);
       router.replace('/dashboard?family=activated');
       return;
     }
     if(response.outcome==='APPLICATION_DRAFT_CREATED') {
       if(!response.application?.id || response.application.status!=='DRAFT')
         throw Error('Flask returned a draft outcome without a valid draft. Check your applications before retrying.');
       clearPendingInvitation();setToken('');setAccepted(response.application.id);
       router.replace(`/onboarding/${encodeURIComponent(response.application.id)}?invitation=accepted`);
       return;
     }
     throw Error('The backend returned an unrecognized invitation outcome. Check memberships and applications before retrying.');
   }catch(e){
     // An interrupted POST may have succeeded on Flask. Check the actual invitation_id
     // on server-created applications. Never automatically POST a single-use token twice.
     if(chosen.id && e instanceof ApiError && (e.status===0||e.status===502||e.status===504)){
       // An uncertain family POST may have activated a real membership already.
       // The membership response has no invitation ID; do not infer acceptance
       // from an unrelated family membership or blindly replay the one-time token.
       if(chosen.category==='FAMILY_MEMBER'){
         setError('The connection ended before confirmation. Your family membership may already be active. Check your dashboard and household before attempting this invitation again.');return;
       }
       const recovered=await recoverAfterUncertainResult(chosen.id);
       if(recovered){clearPendingInvitation();setAccepted(recovered);router.replace(`/onboarding/${encodeURIComponent(recovered)}?invitation=accepted`);return;}
     }
     handleError(e);
   }finally{setSubmitting(false);}
 }
 const signedIn=!!session.user;
 return <PublicShell><AuthCard eyebrow="PRIVATE RESIDENCY INVITATION" title="Accept your invitation" subtitle="Confirm an invitation sent to your verified email. Eligible sponsored family members join directly; owners and tenants continue through application review.">
  {!loadedToken||session.loading?<Loading label="Preparing your secure invitation…"/>:
   activated?<Alert tone="success">Your family membership was activated by Flask. Opening your resident dashboard… <Link href="/dashboard" className="text-link">Go to dashboard</Link>.</Alert>:
   !token&&!accepted&&!activated?<Alert tone="warning">No usable invitation token is available in this tab. Open the private acceptance link from your email again. <Link href="/invitations" className="text-link">View invitations</Link>.</Alert>:
   !signedIn?<div className="form-stack">
     <Alert tone="info">Sign in or create an account using the email that received this invitation. The invitation will be retained in this browser tab while you authenticate.</Alert>
     <Link href={`/login?next=${encodeURIComponent(next)}`} className="btn btn-primary">Sign in to continue</Link>
     <Link href={`/register?next=${encodeURIComponent(next)}`} className="btn btn-secondary">Create an account</Link>
   </div>:
   !session.user!.email_verified?<div className="form-stack">
     <Alert tone="warning">Your email is not verified. Verify the invited email before accepting. If verification opens another tab, return to this invitation tab afterward.</Alert>
     <Link href={`/check-inbox?next=${encodeURIComponent(next)}`} className="btn btn-primary">Resend verification email</Link>
     <Button variant="secondary" onClick={()=>void session.refresh()}>I have verified my email · Recheck</Button>
   </div>:
   accepted?<Alert tone="success">Invitation accepted. Opening your new application draft… <Link href={`/onboarding/${encodeURIComponent(accepted)}`} className="text-link">Continue</Link></Alert>:
   <div className="form-stack">
     <Alert tone="info">Signed in as <strong>{session.user!.email}</strong>. Flask will independently confirm this is the invited account. Family invitations can activate membership after Flask validates your sponsor and account. Owner and tenant invitations only create drafts.</Alert>
     <button type="button" className="text-link small" onClick={()=>void session.logout({preserveInvitation:true})}>Not the invited email? Sign out and switch accounts</button>
     {loadingList?<Loading label="Checking invitations addressed to you…"/>:
       listError?<Alert tone="danger">Could not load invitations: {listError} <button type="button" className="text-link" onClick={()=>setRefreshKey(k=>k+1)}>Retry</button></Alert>:
       list&&active.length===0?<Alert tone="warning">There is no active invitation for this verified email. The link may be expired, already used, revoked, or addressed to a different account. <Link href="/onboarding" className="text-link">Check your applications</Link>.</Alert>:
       list?<>
         {active.length>1&&<SelectField id="invite-choice" label="Choose the invitation described in your email" required value={chosen?.id??''} onChange={e=>{setSelectedId(e.target.value);setRelationship('');}}><option value="">Choose an invitation</option>{active.map(i=><option key={i.id} value={i.id}>{pretty(i.category)} — {i.flat_label?`Flat ${i.flat_label}`:i.flat_id?`Flat ${i.flat_id.slice(0,8)}`:'Residence not listed'} — expires {shortDate(i.expires_at)}</option>)}</SelectField>}
         {hintId&&!active.some(inv=>inv.id===hintId)&&<Alert tone="warning">The invitation referenced by this email link is not active for your current account. Sign in with the invited address or request a new invitation.</Alert>}
         {chosen&&<form onSubmit={e=>void submit(e)} className="form-stack">
           <div className="invitation-summary" aria-label="Invitation details">
             <div className="between"><strong>Green Valley Residency</strong><Badge value="ACTIVE"/></div>
             <div className="info-list mt-3">
               <div className="info-row"><span>Category (assigned)</span><strong>{pretty(chosen.category)}</strong></div>
               <div className="info-row"><span>Tower</span><strong>{flat?.tower_name??'See invitation email'}</strong></div>
               <div className="info-row"><span>Flat</span><strong>{flat?.flat_number??chosen.flat_label??'See invitation email'}</strong></div>
               <div className="info-row"><span>Expires</span><strong>{shortDate(chosen.expires_at)}</strong></div>
               {chosen.category==='FAMILY_MEMBER'&&<>
                 <div className="info-row"><span>Household</span><strong>{chosen.household_label??chosen.household_id??'Assigned by sponsor'}</strong></div>
                 <div className="info-row"><span>Sponsor</span><strong>{chosen.sponsor_name??chosen.sponsor_membership_id??'Verified by Flask'}</strong></div>
               </>}
             </div>
           </div>
           {chosen.category==='FAMILY_MEMBER'&&<SelectField id="family-relationship" label="Your relationship to the sponsor" value={relationship||chosen.relationship_to_sponsor||''} onChange={e=>setRelationship(e.target.value as Relationship)} required><option value="">Select relationship</option>{relationships.map(r=><option key={r} value={r}>{pretty(r)}</option>)}</SelectField>}
           <SelectField id="occupancy" label="Do you currently live at this residence? (self-declared)" value={occupancy} onChange={e=>setOccupancy(e.target.value as 'unknown'|'yes'|'no')}><option value="unknown">Not sure / Prefer not to declare yet</option><option value="yes">Yes</option><option value="no">No</option></SelectField>
           {chosen.category==='TENANT'&&<p className="hint">Requested tenancy start and end dates are entered in the application draft after acceptance.</p>}
           <Alert tone="info">{chosen.category==='FAMILY_MEMBER'?'Flask will verify the invited email and active household sponsor. If eligible, your family membership becomes active immediately—no routine documents, OCR, or admin approval.':'Flask will create an owner/tenant application draft. Residence evidence and administrator approval are still required.'}</Alert>
           {error&&<Alert tone="danger">{error}</Alert>}
           <Button busy={submitting} type="submit">{chosen.category==='FAMILY_MEMBER'?'Accept & join household →':'Accept & create application draft →'}</Button>
         </form>}
       </>:null}
     {error&&!chosen&&<Alert tone="danger">{error}</Alert>}
     <Link href="/invitations" className="text-link small">← All invitations</Link>
   </div>}
 </AuthCard></PublicShell>;
}
