import {Protected} from '@/components/shell';
import DisputeDetail from '@/features/disputes/dispute-detail';
export default async function Page({params}:{params:Promise<{id:string}>}){
  const {id}=await params;
  return <Protected><DisputeDetail id={id}/></Protected>;
}
