import {Protected} from '@/components/shell';
import NoticeDetail from '@/features/notices/notice-detail';
export default async function Page({params}:{params:Promise<{id:string}>}){
  const {id}=await params;
  return <Protected><NoticeDetail id={id}/></Protected>;
}
