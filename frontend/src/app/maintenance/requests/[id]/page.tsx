import {Protected} from '@/components/shell';
import TicketDetail from '@/features/operations/ticket-detail';
export default async function Page({params}:{params:Promise<{id:string}>}){
  const {id}=await params;
  return <Protected><TicketDetail id={id}/></Protected>;
}
