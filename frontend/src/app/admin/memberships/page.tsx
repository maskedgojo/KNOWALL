import {Protected} from '@/components/shell';
import AdminMemberships from '@/features/admin/memberships';
export default function Page(){return <Protected admin><AdminMemberships/></Protected>}
