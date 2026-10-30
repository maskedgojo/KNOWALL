'use client';
import {useState,useEffect,type ReactNode} from 'react';
import Link from 'next/link';
import {usePathname,useRouter} from 'next/navigation';
import {adminRole,useAuth} from './auth-provider';
import {Icon} from './icons';
import {Loading} from './ui';
type NavItem=[href:string,label:string,icon:string];
type NavGroup={label:string;items:NavItem[]};
const RESIDENT:NavItem[]=[['/dashboard','Overview','home'],['/onboarding','Applications','clipboard'],['/household','Household & family','users'],['/invitations','Invitations','mail'],['/evidence-requests','Evidence requests','file'],['/profile','My profile','settings']];
const ADMIN:NavItem[]=[['/admin','Overview','home'],['/admin/applications','Application reviews','file'],['/admin/memberships','Memberships','users'],['/admin/households','Household directory','building'],['/admin/evidence-requests','Evidence reviews','shield'],['/admin/invite','Invite residents','mail'],['/admin/audit','Audit trail','shield']];
// Community and Services groups use the same labels in both workspaces; admin links
// open the oversight/moderation views, resident links the participation views.
const RESIDENT_COMMUNITY:NavItem[]=[['/notices','Official notices','clipboard'],['/discussions','Discussions','users'],['/suggestions','Suggestions','file'],['/polls','Informal polls','check'],['/proposals','Proposals','file'],['/disputes','My disputes','lock'],['/governance','Governance history','shield']];
const ADMIN_COMMUNITY:NavItem[]=[['/admin/notices','Official notices','clipboard'],['/admin/discussions','Discussions','users'],['/admin/suggestions','Suggestions','file'],['/admin/polls','Informal polls','check'],['/admin/proposals','Proposals','file'],['/admin/disputes','Disputes','lock']];
const RESIDENT_BOOKINGS:NavItem[]=[['/facilities','Amenities','building'],['/bookings','My bookings','calendar']];
const RESIDENT_SERVICES:NavItem[]=[['/events','Society events','calendar'],['/maintenance','Maintenance','settings'],['/development','Development projects','clipboard']];
// Module 4: residents browse and suggest; only a Locality Coordinator gets the desk.
const RESIDENT_LOCALITY:NavItem[]=[['/locality','Locality overview','home'],['/locality/places','Essential services','search'],['/locality/events','Local events','calendar'],['/locality/alerts','Local alerts','alert']];
const LOCALITY_DESK:NavItem[]=[['/locality/manage','Locality desk','shield'],['/locality/manage/places','Places','building'],['/locality/manage/corrections','Corrections','check'],['/locality/manage/events','Event moderation','calendar'],['/locality/manage/alerts','Alert management','alert'],['/locality/manage/reports','Content reports','file']];
const ADMIN_LOCALITY:NavItem[]=[['/locality','Locality overview','home'],['/locality/events','Share society events','calendar']];
const ADMIN_SERVICES:NavItem[]=[['/admin/facilities','Amenities & bookings','building'],['/admin/events','Society events','calendar'],['/admin/maintenance','Maintenance','settings'],['/admin/development','Development projects','clipboard']];
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
  const {user,access,logout}=useAuth();const pathname=usePathname();const [open,setOpen]=useState(false);
  const can=(permission:string)=>!!access?.permissions.includes(permission);
  const residentNav:NavGroup[]=[{label:'MY HOME',items:RESIDENT},
    {label:'COMMUNITY',items:can('society.notices.read')?RESIDENT_COMMUNITY:[]},
    {label:'SERVICES',items:[...(can('society.facilities.book')?RESIDENT_BOOKINGS:[]),...(can('society.notices.read')?RESIDENT_SERVICES:[])]},
    {label:'LOCALITY',items:can('locality.read')?[...RESIDENT_LOCALITY,...(can('locality.listings.suggest')?[['/locality/corrections','My corrections','clipboard'] as NavItem]:[])]:[]},
    {label:'LOCALITY DESK',items:can('locality.manage')?LOCALITY_DESK:[]}];
  const adminNav:NavGroup[]=[{label:'RESIDENTS',items:ADMIN},
    {label:'COMMUNITY',items:can('society.notices.manage')?ADMIN_COMMUNITY:[]},
    {label:'SERVICES',items:can('society.operations.manage')?ADMIN_SERVICES:[]},
    {label:'LOCALITY',items:can('locality.read')?ADMIN_LOCALITY:[]}];
  const nav=(admin?adminNav:residentNav).filter(group=>group.items.length);
  // Section roots highlight only on their own page, not on every child route.
  const active=(href:string)=>pathname===href||(!['/admin','/locality','/locality/manage'].includes(href)&&pathname.startsWith(href+'/'));
  return <div className="app-layout">
    {open&&<button className="mobile-overlay" aria-label="Close navigation" onClick={()=>setOpen(false)}/>}
    <aside className={`sidebar ${open?'sidebar-open':''}`}>
      <Link className="brand" href={admin?'/admin':'/dashboard'} onClick={()=>setOpen(false)}><span className="brand-logo"><Icon name="building" size={20}/></span><span>KNOWALL<small>GREEN VALLEY RESIDENCY</small></span></Link>
      <div className="side-group-label">{admin?'ADMINISTRATION':'RESIDENT SERVICES'}</div>
      <nav aria-label={admin?'Administration':'Resident navigation'} className="side-nav">{nav.map((group,index)=><div key={group.label} className="side-section">{index>0&&<div className="side-section-label">{group.label}</div>}{group.items.map(([href,label,icon])=><Link href={href} key={href} onClick={()=>setOpen(false)} className={`side-link ${active(href)?'side-active':''}`}><Icon name={icon} size={18}/><span>{label}</span></Link>)}</div>)}</nav>
      {adminRole(access)&&<div className="side-switch"><span className="side-group-label">WORKSPACES</span><Link href={admin?'/dashboard':'/admin'} className="side-link"><Icon name="refresh" size={17}/>{admin?'Resident workspace':'Administration'}</Link></div>}
      <div className="sidebar-bottom"><div className="community-note"><Icon name="shield" size={16}/><span>One community.<br/>One secure home.</span></div><button className="side-link logout-btn" onClick={()=>void logout()}><Icon name="logoff" size={18}/>Sign out</button></div>
    </aside>
    <div className="workspace"><header className="topbar"><div className="topbar-left"><button className="menu-button" aria-label="Open navigation" onClick={()=>setOpen(true)}><Icon name="menu"/></button><span className="topbar-org"><span className="org-dot"/>Green Valley Residency</span><span className="crumb">/</span><span className="topbar-current">{admin?'Administration':'Resident portal'}</span></div><div className="topbar-right"><div className="live-dot"/><span className="topbar-account">{user?.display_name}</span><div className="avatar">{user?.display_name?.slice(0,1).toUpperCase()||'K'}</div></div></header><main className="main-area">{children}</main><footer className="footer"><span>© KNOWALL · Green Valley Residency</span><span>Security and privacy by design</span></footer></div>
  </div>;
}
export function PublicShell({children}:{children:ReactNode}){return <main className="auth-layout"><section className="auth-brand"><Link className="brand brand-invert" href="/"><span className="brand-logo"><Icon name="building" size={20}/></span><span>KNOWALL<small>COMMUNITY, SIMPLIFIED</small></span></Link><div className="auth-brand-body"><div className="brand-eyebrow">A BETTER WAY TO BELONG</div><h1>Your home.<br/><em>Your community.</em><br/>All connected.</h1><p>One secure place for residential verification, household relationships and community services.</p><div className="brand-feature"><Icon name="shield" size={20}/><span>Privacy-first identity verification and resident access</span></div><div className="brand-feature"><Icon name="users" size={20}/><span>Clear connections across your household</span></div><div className="brand-feature"><Icon name="building" size={20}/><span>Built for Green Valley Residency</span></div></div><div className="auth-brand-foot"><span className="brand-line"/> One community. One connected experience.</div></section><section className="auth-content"><div className="auth-mobile-brand"><Link href="/" className="brand"><span className="brand-logo"><Icon name="building"/></span><span>KNOWALL</span></Link></div>{children}</section></main>}
export function AuthCard({children,eyebrow,title,subtitle}:{children:ReactNode;eyebrow?:string;title:string;subtitle:string}){return <div className="auth-card">{eyebrow&&<span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1><p className="auth-subtitle">{subtitle}</p>{children}</div>}
