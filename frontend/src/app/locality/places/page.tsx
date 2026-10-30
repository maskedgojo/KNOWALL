import {Suspense} from 'react';
import {Protected} from '@/components/shell';
import {Loading} from '@/components/ui';
import Directory from '@/features/locality/directory';
export default function Page(){return <Protected><Suspense fallback={<Loading/>}><Directory/></Suspense></Protected>}
