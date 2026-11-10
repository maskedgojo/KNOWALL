import {Protected} from '@/components/shell';
import OfficerWorkspace from '@/features/authority/officer-workspace';
export default function Page(){return <Protected><OfficerWorkspace/></Protected>}
