import {Protected} from '@/components/shell';
import CivicIssueList from '@/features/civic/issue-list';
export default function Page(){return <Protected><CivicIssueList/></Protected>}
