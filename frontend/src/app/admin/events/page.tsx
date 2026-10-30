import {Protected} from '@/components/shell';
import AdminEvents from '@/features/operations/admin-events';
export default function Page(){return <Protected admin><AdminEvents/></Protected>}
