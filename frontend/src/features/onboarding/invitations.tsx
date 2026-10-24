'use client';

import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {useEffect,useMemo,useState} from 'react';
import {adminRole,useAuth} from '@/components/auth-provider';
import {Alert,Badge,Button,Card,EmptyState,ErrorState,Loading,PageHeading} from '@/components/ui';
import {residentApi} from '@/lib/endpoints';
import {errorText,useLoad} from '@/lib/use-load';
import {pretty,shortDate} from '@/lib/format';
import {parseInvitations,invitationState} from '@/lib/invitation-model';
import {hasPendingInvitation,rememberInvitation,pendingInvitation} from '@/lib/invitation-handoff';
import {parseInvitationLink} from '@/lib/invitation-link';

export default function Invitations(){
  const router=useRouter();
  const {access}=useAuth();
  const received=useLoad(()=>residentApi.invitations(),[]);
  const applications=useLoad(()=>residentApi.applications(),[]);
  const [hasEmailToken,setHasEmailToken]=useState(false);
  const [link,setLink]=useState('');
  const [linkError,setLinkError]=useState('');
  const [flatLabels,setFlatLabels]=useState<Record<string,string>>({});
  useEffect(()=>{Promise.resolve().then(()=>setHasEmailToken(hasPendingInvitation()));},[]);
  useEffect(()=>{
    const ids=[...new Set(parseInvitations(received.value).map(i=>i.flat_id).filter((x):x is string=>!!x))];
    let active=true;
    void Promise.all(ids.map(async(id)=>{
      try{const {flat}=await residentApi.flat(id);return [id,`${flat.tower_name} · ${flat.flat_number}`] as const;}
      catch{return null;}
    })).then(rows=>{
      if(active){
        const labels:Record<string,string>={};
        for(const row of rows)if(row)labels[row[0]]=row[1];
        setFlatLabels(labels);
      }
    });
    return()=>{active=false;};
  },[received.value]);
  const items=parseInvitations(received.value);
  const activeItems=items.filter(i=>invitationState(i)==='ACTIVE');
  const knownApplications=useMemo(()=>applications.value?.applications??[],[applications.value]);
  const admin=adminRole(access);
  const canSendFamily=!!access?.active_memberships.some(m=>
    m.status==='ACTIVE'&&(m.category==='OWNER'||m.category==='TENANT'));
  // Flask currently exposes only incoming invitations in GET /api/invitations/me.
  // No sent list is invented from audit logs or browser-local state.

  function continueEmailLink(event:React.FormEvent<HTMLFormElement>){
    event.preventDefault();
    const pending=parseInvitationLink(link);
    if(!pending){setLinkError('Paste the full private invitation URL from your email (or its one-time token).');return;}
    rememberInvitation(pending.token,pending.invitationId);
    setLink('');setLinkError('');
    router.push('/invitations/accept');
  }

  const stored=pendingInvitation();
  const canContinueToken=hasEmailToken&&!!stored&&
    (activeItems.length===1||!!stored.invitationId&&activeItems.some(x=>x.id===stored.invitationId));

  return <>
    <PageHeading eyebrow="RESIDENCY / INVITATIONS" title="Invitations" description="Track invitations addressed to you and continue the private invitation acceptance flow."/>
    <div className="grid-2">
      <Card>
        <div className="between mb-4"><h2 className="card-title">Received invitations</h2><Badge value={String(items.length)}/></div>
        {received.loading?<Loading label="Loading received invitations…"/>:
         received.error?<ErrorState error={received.error} onRetry={received.refresh}/>:
         items.length?items.map(inv=>{
           const state=invitationState(inv);
           const application=knownApplications.find(a=>a.invitation_id===inv.id);
           return <div className="notice-card mb-3" key={inv.id}>
             <div className="between"><strong>{pretty(inv.category)}</strong><Badge value={state}/></div>
             <p className="small muted">{inv.flat_id&&flatLabels[inv.flat_id]?`Tower / flat: ${flatLabels[inv.flat_id]}`:inv.flat_label?`Flat ${inv.flat_label}`:inv.flat_id?`Flat reference: ${inv.flat_id}`:'Residence information available through your private email link'}</p>
             {inv.category==='FAMILY_MEMBER'&&<p className="small muted">{inv.household_label??'Sponsored household'}{inv.sponsor_name?` · Sponsor: ${inv.sponsor_name}`:''}</p>}
             <p className="small muted">Sent to: {inv.email} · Expires: {shortDate(inv.expires_at)}</p>
             {application?
               <div className="mt-3"><p className="small muted">This invitation created a {pretty(application.status)} application.</p><Link className="btn btn-secondary mt-2" href={`/onboarding/${encodeURIComponent(application.id)}`}>{application.status==='DRAFT'?'Continue onboarding':'View application'} →</Link></div>
              :state==='ACTIVE'?<div className="mt-3">
                <p className="hint">A private single-use token is required. The invitation listing cannot expose it.</p>
                {hasEmailToken&&canContinueToken&&<Link className="btn btn-primary mt-2" href="/invitations/accept">Continue acceptance →</Link>}
                <p className="hint mt-2">Alternatively, paste the link from the invitation email in the acceptance section.</p>
               </div>
              :<p className="hint mt-2">{state==='USED'?'This invitation has already been used. Family membership activation appears on your dashboard; Owner/Tenant draft applications appear under Applications.':'This invitation is no longer active. Ask the sender for a new one.'}</p>}
           </div>;
         }):<EmptyState title="No received invitations" description="Invitations sent to your verified email will appear here."/>}
        {applications.error&&<p className="hint mt-3">Application shortcuts are unavailable right now: {errorText(applications.error)}. <Link className="text-link" href="/onboarding">Open applications</Link>.</p>}
      </Card>
      <div className="stack-sm">
        <Card>
          <h2 className="card-title mb-3">Accept a private invitation</h2>
          <Alert tone="info">Sponsored Family Member invitations activate an eligible household membership immediately. Owner/Tenant invitations create draft applications requiring evidence and administrator review.</Alert>
          <p className="small muted mt-4 mb-3">To protect invitees, Flask does not return the one-time token in the invitation list. Use the private link received by email.</p>
          <form className="form-stack" onSubmit={continueEmailLink}>
            <label className="field" htmlFor="private-invitation-link">
              <span className="field-title">Paste invitation email link</span>
              <input type="text" id="private-invitation-link" className="input" value={link}
                onChange={e=>{setLink(e.target.value);setLinkError('');}}
                autoComplete="off" spellCheck={false} placeholder="http://localhost:3000/invitations/accept?token=…"/>
              <span className="hint">This value is not submitted to a server until you choose to accept on the next screen.</span>
            </label>
            {linkError&&<Alert tone="danger">{linkError}</Alert>}
            <Button type="submit" disabled={!link.trim()}>Review invitation →</Button>
          </form>
          <div className="form-actions"><Link href="/dashboard" className="btn btn-secondary">View memberships</Link><Link href="/onboarding" className="btn btn-secondary">View my applications</Link></div>
        </Card>
        <Card>
          <h2 className="card-title mb-3">Invitations you sent</h2>
          <p className="small muted">Your sent invitation history is not available yet. Invitations you have sent cannot currently be retrieved, but you can send a new one below.</p>
          <Alert tone="warning">Your outgoing invitations will appear here once sent-history support is connected. This currently shows only invitations addressed <strong>to</strong> you.</Alert>
          <div className="form-actions">
            {admin&&<Link className="btn btn-primary" href="/admin/invite">Send an owner / tenant invitation →</Link>}
            {canSendFamily&&<Link className="btn btn-secondary" href="/household">Invite a family member →</Link>}
          </div>
        </Card>
      </div>
    </div>
  </>;
}
