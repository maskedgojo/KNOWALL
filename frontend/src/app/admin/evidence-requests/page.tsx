import {Protected} from '@/components/shell';
import AdminEvidenceRequests from '@/features/admin/evidence-requests';
export default function Page(){return <Protected admin><AdminEvidenceRequests/></Protected>}
