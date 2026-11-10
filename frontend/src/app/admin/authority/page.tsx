import {Protected} from '@/components/shell';
import AdminAuthority from '@/features/authority/admin-authority';
export default function Page(){return <Protected admin><AdminAuthority/></Protected>}
