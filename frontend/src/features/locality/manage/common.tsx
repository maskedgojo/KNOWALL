'use client';
import {useState} from 'react';
import Link from 'next/link';
import {usePathname} from 'next/navigation';
import {Alert, Button, TextareaField} from '@/components/ui';
import {errorText} from '@/lib/use-load';

const DESK:[string,string][]=[['/locality/manage','Desk'],['/locality/manage/places','Places'],['/locality/manage/corrections','Corrections'],['/locality/manage/events','Events'],['/locality/manage/alerts','Alerts'],['/locality/manage/reports','Reports']];
export function DeskTabs(){
  const pathname=usePathname();
  return <nav aria-label="Locality desk" className="flex flex-wrap gap-2 mb-4">{DESK.map(([href,label])=>{const active=href==='/locality/manage'?pathname===href:pathname===href||pathname.startsWith(href+'/');
    return <Link key={href} href={href} aria-current={active?'page':undefined} className={`btn ${active?'btn-primary':'btn-secondary'}`}>{label}</Link>;})}</nav>;
}

/** A moderation button that always asks for a reason before calling Flask. */
export function ReasonAction({label,confirmLabel,variant='secondary',minimum=3,placeholder,onConfirm}:{label:string;confirmLabel?:string;variant?:'primary'|'secondary'|'ghost'|'danger';minimum?:number;placeholder?:string;onConfirm:(reason:string)=>Promise<unknown>}){
  const [open,setOpen]=useState(false),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  if(!open)return <Button variant={variant} onClick={()=>setOpen(true)}>{label}</Button>;
  async function confirm(){setBusy(true);setError('');try{await onConfirm(reason.trim());setOpen(false);setReason('');}catch(cause){setError(errorText(cause));}finally{setBusy(false);}}
  return <div className="stack w-full">
    <TextareaField id={`reason-${label.replace(/\W+/g,'-').toLowerCase()}`} label={`Reason (required, at least ${minimum} characters)`} value={reason} maxLength={1000} placeholder={placeholder} onChange={event=>setReason(event.target.value)}/>
    {error&&<Alert tone="warning">{error}</Alert>}
    <div className="flex gap-2"><Button variant={variant} busy={busy} disabled={reason.trim().length<minimum} onClick={()=>void confirm()}>{confirmLabel??label}</Button><Button variant="ghost" onClick={()=>setOpen(false)}>Cancel</Button></div>
  </div>;
}
