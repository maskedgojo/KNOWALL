'use client';
import {useState} from 'react';
import Link from 'next/link';
import {adminApi,str} from '@/lib/endpoints';
import {records,pager,applicantName,flatText} from './helpers';
import {Badge,Button,Card,EmptyState,ErrorState,Loading,PageHeading,SelectField} from '@/components/ui';
import {Icon} from '@/components/icons';
import {useLoad} from '@/lib/use-load';
import {pretty,shortDate} from '@/lib/format';
const statuses=['','DRAFT','PENDING','IN_REVIEW','NEEDS_CORRECTION','APPROVED','REJECTED'];const LIMIT=15;
export default function AdminQueue(){const [status,setStatus]=useState('PENDING'),[offset,setOffset]=useState(0);const load=useLoad(()=>adminApi.applications(status,offset,LIMIT),[status,offset]);const items=records(load.value,'applications');const page=pager(load.value);
 return <><PageHeading eyebrow="ADMINISTRATION / VERIFICATION" title="Application review queue" description="Review resident applications with human oversight and traceable decisions." action={<Button variant="secondary" onClick={load.refresh}><Icon name="refresh" size={16}/>Refresh</Button>}/>
 <Card><div className="between mb-5"><div className="w-60 max-w-full"><SelectField id="filter" label="Application status" value={status} onChange={e=>{setStatus(e.target.value);setOffset(0)}}>{statuses.map(s=><option key={s} value={s}>{s?pretty(s):'All applications'}</option>)}</SelectField></div><div className="small muted">{page.total===null?'Backend total unavailable':`${page.total} matching records`}</div></div>
 {load.loading?<Loading/>:load.error?<ErrorState error={load.error} onRetry={load.refresh}/>:items.length?<div className="table-wrap"><table className="table"><thead><tr><th>Applicant</th><th>Residence</th><th>Category</th><th>Received</th><th>State</th><th/></tr></thead><tbody>{items.map(a=><tr key={str(a.id)}><td><strong>{applicantName(a)}</strong><span className="block tiny muted">{str(a.id).slice(0,8)}</span></td><td>{flatText(a.flat)}</td><td>{pretty(str(a.category))}</td><td>{shortDate(str(a.submitted_at))}</td><td><Badge value={str(a.status)}/></td><td><Link href={`/admin/applications/${str(a.id)}`}>Review →</Link></td></tr>)}</tbody></table></div>:<EmptyState title="No matching applications" description="Change the status filter to see another portion of the verification queue."/>}
 <div className="form-actions"><Button variant="secondary" disabled={offset===0||load.loading} onClick={()=>setOffset(Math.max(0,offset-LIMIT))}>Previous</Button><span className="small muted">Offset {offset}</span><Button variant="secondary" disabled={load.loading||(page.total!==null?offset+LIMIT>=page.total:items.length<LIMIT)} onClick={()=>setOffset(offset+LIMIT)}>Next</Button></div></Card></>;
}
