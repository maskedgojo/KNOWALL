'use client';
import Link from 'next/link';
import {Badge,Card,EmptyState,ErrorState,Loading,PageHeading} from '@/components/ui';
import {Icon} from '@/components/icons';
import {residentApi} from '@/lib/endpoints';
import {useLoad} from '@/lib/use-load';
import {pretty,shortDate} from '@/lib/format';
export default function ApplicationList(){const load=useLoad(()=>residentApi.applications(),[]);return <><PageHeading eyebrow="RESIDENCY / APPLICATIONS" title="My applications" description="Drafts, corrections and review progress in one place." action={<Link href="/onboarding/new" className="btn btn-primary"><Icon name="plus" size={16}/>New application</Link>}/>{load.loading?<Loading/>:load.error?<ErrorState error={load.error} onRetry={load.refresh}/>:<Card>{load.value?.applications?.length?<div className="table-wrap"><table className="table"><thead><tr><th>Reference</th><th>Flat</th><th>Category</th><th>Created</th><th>State</th><th/></tr></thead><tbody>{load.value.applications.map(a=><tr key={a.id}><td className="font-semibold">{a.id.slice(0,8).toUpperCase()}</td><td>{a.flat?.tower_name} · {a.flat?.flat_number}</td><td>{pretty(a.category)}</td><td>{shortDate(a.created_at)}</td><td><Badge value={a.status}/></td><td><Link href={`/onboarding/${a.id}`}>View details →</Link></td></tr>)}</tbody></table></div>:<EmptyState title="No applications yet" description="Create an owner or tenant application, or join a family household via an email invitation." action={<Link href="/onboarding/new" className="btn btn-primary">Create an application</Link>}/>}</Card>}</>}
