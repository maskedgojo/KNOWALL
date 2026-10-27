import {Protected} from '@/components/shell';
import ManageNotices from '@/features/notices/manage-notices';
export default function Page(){return <Protected admin><ManageNotices/></Protected>}
