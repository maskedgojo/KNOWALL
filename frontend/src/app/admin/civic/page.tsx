import {Protected} from '@/components/shell';
import AdminCivic from '@/features/civic/admin-civic';
export default function Page(){return <Protected admin><AdminCivic/></Protected>}
