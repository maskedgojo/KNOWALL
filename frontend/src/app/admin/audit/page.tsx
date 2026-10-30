import {Protected} from '@/components/shell';
import AdminAudit from '@/features/admin/audit';
export default function Page(){return <Protected admin><AdminAudit/></Protected>}
