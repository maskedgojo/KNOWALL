import {Protected} from '@/components/shell';
import DiscussionDetail from '@/features/discussions/discussion-detail';
export default async function Page({params}:{params:Promise<{id:string}>}){
  const {id}=await params;
  return <Protected><DiscussionDetail id={id}/></Protected>;
}
