import {Protected} from '@/components/shell';
import ApplicationDetail from '@/features/onboarding/detail';
export default async function Page({params,searchParams}:{params:Promise<{id:string}>;searchParams:Promise<{invitation?:string}>}){
  const [{id},query]=await Promise.all([params,searchParams]);
  return <Protected><ApplicationDetail id={id} fromInvitation={query.invitation==='accepted'}/></Protected>;
}
