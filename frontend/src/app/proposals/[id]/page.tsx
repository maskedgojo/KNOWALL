import {Protected} from '@/components/shell';
import ProposalDetail from '@/features/proposals/proposal-detail';
export default async function Page({params}:{params:Promise<{id:string}>}){
  const {id}=await params;
  return <Protected><ProposalDetail id={id}/></Protected>;
}
