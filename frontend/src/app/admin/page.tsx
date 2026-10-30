import {Protected} from '@/components/shell';
import AdminOverview from '@/features/admin/overview';
export default function Page(){return <Protected admin><AdminOverview/></Protected>}
