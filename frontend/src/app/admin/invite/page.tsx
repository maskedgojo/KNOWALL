import {Protected} from '@/components/shell';
import AdminInvite from '@/features/admin/invite';
export default function Page(){return <Protected admin><AdminInvite/></Protected>}
