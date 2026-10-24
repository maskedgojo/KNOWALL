'use client';
import {useState,useEffect,type ReactNode} from 'react';
import Link from 'next/link';
import {usePathname,useRouter} from 'next/navigation';
import {adminRole,useAuth} from './auth-provider';
import {Icon} from './icons';
import {Loading} from './ui';
const RESIDENT=[['/dashboard','Overview','home'],['/onboarding','Applications','clipboard'],['/household','Household & family','users'],['/invitations','Invitations','mail'],['/evidence-requests','Evidence requests','file'],['/profile','My profile','settings']];
const ADMIN=[['/admin','Overview','home'],['/admin/applications','Application reviews','file'],['/admin/memberships','Memberships','users'],['/admin/households','Household directory','building'],['/admin/evidence-requests','Evidence reviews','shield'],['/admin/invite','Invite residents','mail'],['/admin/audit','Audit trail','shield']];
export function Protected({children,admin=false}:{children:ReactNode;admin?:boolean}){
  const {user,access,loading}=useAuth();const router=useRouter();
  useEffect(()=>{if(!loading&&!user){
    // An admin URL from an old account must never survive into a new login.
    router.replace('/login');
  }},[loading,user,router]);
  if(loading)return <div className="center-screen"><Loading label="Checking your session…"/></div>;
  if(!user)return <div className="center-screen"><Loading label="Redirecting to sign in…"/></div>;
  if(admin&&!adminRole(access))return <div className="center-screen"><div className="card p-8 text-center"><h2>Access restricted</h2><p className="muted">Only authorized society administrators can access this workspace.</p><Link className="btn btn-primary mt-5" href="/dashboard">Return to dashboard</Link></div></div>;
  return <AppShell admin={admin}>{children}</AppShell>;
}
function AppShell({children,admin}:{children:ReactNode;admin:boolean}){
  const {user,access,logout}=useAuth();const pathname=usePathname();const [open,setOpen]=useState(false);const nav=admin?ADMIN:RESIDENT;
  return <div className="app-layout">
    {open&&<button className="mobile-overlay" aria-label="Close navigation" onClick={()=>setOpen(false)}/>}
    <aside className={`sidebar ${open?'sidebar-open':''}`}>
      <Link className="brand" href={admin?'/admin':'/dashboard'} onClick={()=>setOpen(false)}><span className="brand-logo"><Icon name="building" size={20}/></span><span>KNOWALL<small>GREEN VALLEY RESIDENCY</small></span></Link>
      <div className="side-group-label">{admin?'ADMINISTRATION':'RESIDENT SERVICES'}</div>
      <nav aria-label={admin?'Administration':'Resident navigation'} className="side-nav">{nav.map(([href,label,icon])=><Link href={href} key={href} onClick={()=>setOpen(false)} className={`side-link ${pathname===href||(href!='/admin'&&pathname.startsWith(href+'/'))?'side-active':''}`}><Icon name={icon} size={18}/><span>{label}</span></Link>)}</nav>
      {adminRole(access)&&<div className="side-switch"><span className="side-group-label">WORKSPACES</span><Link href={admin?'/dashboard':'/admin'} className="side-link"><Icon name="refresh" size={17}/>{admin?'Resident workspace':'Administration'}</Link></div>}
      <div className="sidebar-bottom"><div className="community-note"><Icon name="shield" size={16}/><span>One community.<br/>One secure home.</span></div><button className="side-link logout-btn" onClick={()=>void logout()}><Icon name="logoff" size={18}/>Sign out</button></div>
    </aside>
    <div className="workspace"><header className="topbar"><div className="topbar-left"><button className="menu-button" aria-label="Open navigation" onClick={()=>setOpen(true)}><Icon name="menu"/></button><span className="topbar-org"><span className="org-dot"/>Green Valley Residency</span><span className="crumb">/</span><span className="topbar-current">{admin?'Administration':'Resident portal'}</span></div><div className="topbar-right"><div className="live-dot"/><span className="topbar-account">{user?.display_name}</span><div className="avatar">{user?.display_name?.slice(0,1).toUpperCase()||'K'}</div></div></header><main className="main-area">{children}</main><footer className="footer"><span>© KNOWALL · Green Valley Residency</span><span>Security and privacy by design</span></footer></div>
  </div>;
}
export function PublicShell({children}:{children:ReactNode}){return <main className="auth-layout"><section className="auth-brand"><Link className="brand brand-invert" href="/"><span className="brand-logo"><Icon name="building" size={20}/></span><span>KNOWALL<small>COMMUNITY, SIMPLIFIED</small></span></Link><div className="auth-brand-body"><div className="brand-eyebrow">A BETTER WAY TO BELONG</div><h1>Your home.<br/><em>Your community.</em><br/>All connected.</h1><p>One secure place for residential verification, household relationships and community services.</p><div className="brand-feature"><Icon name="shield" size={20}/><span>Privacy-first identity verification and resident access</span></div><div className="brand-feature"><Icon name="users" size={20}/><span>Clear connections across your household</span></div><div className="brand-feature"><Icon name="building" size={20}/><span>Built for Green Valley Residency</span></div></div><div className="auth-brand-foot"><span className="brand-line"/> One community. One connected experience.</div></section><section className="auth-content"><div className="auth-mobile-brand"><Link href="/" className="brand"><span className="brand-logo"><Icon name="building"/></span><span>KNOWALL</span></Link></div>{children}</section></main>}
export function AuthCard({children,eyebrow,title,subtitle}:{children:ReactNode;eyebrow?:string;title:string;subtitle:string}){return <div className="auth-card">{eyebrow&&<span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1><p className="auth-subtitle">{subtitle}</p>{children}</div>}
