import {Protected} from '@/components/shell';
import AdminFacilities from '@/features/operations/admin-facilities';
export default function Page(){return <Protected admin><AdminFacilities/></Protected>}
