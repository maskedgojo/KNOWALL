import {Protected} from '@/components/shell';
import CivicIssueDetail from '@/features/civic/issue-detail';
export default async function Page({params}:{params:Promise<{id:string}>}){
  const {id}=await params;
  return <Protected><CivicIssueDetail id={id}/></Protected>;
}
