import {Protected} from '@/components/shell';
import CaseWorkspace from '@/features/authority/case-workspace';
export default async function Page({params}:{params:Promise<{id:string}>}){
  const {id}=await params;
  return <Protected><CaseWorkspace id={id}/></Protected>;
}
