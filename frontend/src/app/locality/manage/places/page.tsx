import {Suspense} from 'react';
import {Protected} from '@/components/shell';
import {Loading} from '@/components/ui';
import ManagePlaces from '@/features/locality/manage/places';
export default function Page(){return <Protected><Suspense fallback={<Loading/>}><ManagePlaces/></Suspense></Protected>}
