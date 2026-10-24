'use client';
import {ErrorState} from '@/components/ui';
export default function GlobalError({reset}:{error:Error&{digest?:string};reset:()=>void}){return <main className="center-screen"><ErrorState error="This page encountered an unexpected error." onRetry={reset}/></main>}
