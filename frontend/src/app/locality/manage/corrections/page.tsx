import {Suspense} from 'react';
import {Protected} from '@/components/shell';
import {Loading} from '@/components/ui';
import ManageCorrections from '@/features/locality/manage/corrections';
export default function Page(){return <Protected><Suspense fallback={<Loading/>}><ManageCorrections/></Suspense></Protected>}
