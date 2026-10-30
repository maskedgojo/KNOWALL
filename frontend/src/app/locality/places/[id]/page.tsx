import {Protected} from '@/components/shell';
import PlaceDetail from '@/features/locality/place-detail';
export default async function Page({params}:{params:Promise<{id:string}>}){
  const {id}=await params;
  return <Protected><PlaceDetail id={id}/></Protected>;
}
