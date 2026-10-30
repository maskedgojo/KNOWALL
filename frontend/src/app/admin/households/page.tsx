import {Protected} from '@/components/shell';
import AdminHouseholds from '@/features/admin/households';
export default function Page(){return <Protected admin><AdminHouseholds/></Protected>}
