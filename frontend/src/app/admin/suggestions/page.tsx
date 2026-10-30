import {Protected} from '@/components/shell';
import CommunityActivity from '@/features/community/community-activity';
export default function Page(){return <Protected admin><CommunityActivity only="suggestions"/></Protected>}
