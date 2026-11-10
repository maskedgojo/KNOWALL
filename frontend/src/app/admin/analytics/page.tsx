import {Protected} from '@/components/shell';
import CivicAnalytics from '@/features/authority/analytics';
export default function Page(){return <Protected admin><CivicAnalytics/></Protected>}
