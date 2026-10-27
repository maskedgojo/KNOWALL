import {Protected} from '@/components/shell';
import PollList from '@/features/polls/poll-list';
export default function Page(){return <Protected><PollList/></Protected>}
