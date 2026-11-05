import {Protected} from '@/components/shell';
import AdminMaintenance from '@/features/operations/admin-maintenance';
export default function Page(){return <Protected admin><AdminMaintenance/></Protected>}
