import {Protected} from '@/components/shell';
import AdminReview from '@/features/admin/review';
export default async function Page({params}:{params:Promise<{id:string}>}){const {id}=await params;return <Protected admin><AdminReview id={id}/></Protected>}
