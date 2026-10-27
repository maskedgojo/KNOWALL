import {Protected} from '@/components/shell';
import PollDetail from '@/features/polls/poll-detail';
export default async function Page({params}:{params:Promise<{id:string}>}){
  const {id}=await params;
  return <Protected><PollDetail id={id}/></Protected>;
}
