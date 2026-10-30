import {Protected} from '@/components/shell';
import AdminQueue from '@/features/admin/queue';
export default function Page(){return <Protected admin><AdminQueue/></Protected>}
