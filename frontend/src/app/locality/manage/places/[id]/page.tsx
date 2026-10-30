import {Protected} from '@/components/shell';
import PlaceEditor from '@/features/locality/manage/place-editor';
export default async function Page({params}:{params:Promise<{id:string}>}){
  const {id}=await params;
  return <Protected><PlaceEditor id={id}/></Protected>;
}
