import {Protected} from '@/components/shell';
import AdminDisputes from '@/features/disputes/admin-disputes';
export default function Page(){return <Protected admin><AdminDisputes/></Protected>}
