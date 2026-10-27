import {Protected} from '@/components/shell';
import ProposalList from '@/features/proposals/proposal-list';
export default function Page(){return <Protected><ProposalList/></Protected>}
