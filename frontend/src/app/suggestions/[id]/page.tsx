import {Protected} from '@/components/shell';
import SuggestionDetail from '@/features/suggestions/suggestion-detail';
export default async function Page({params}:{params:Promise<{id:string}>}){
  const {id}=await params;
  return <Protected><SuggestionDetail id={id}/></Protected>;
}
