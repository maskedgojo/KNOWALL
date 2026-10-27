import {Protected} from '@/components/shell';
import AdminDevelopment from '@/features/operations/admin-development';
export default function Page(){return <Protected admin><AdminDevelopment/></Protected>}
