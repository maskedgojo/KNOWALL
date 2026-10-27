import {Protected} from '@/components/shell';
import DiscussionList from '@/features/discussions/discussion-list';
export default function Page(){return <Protected><DiscussionList/></Protected>}
