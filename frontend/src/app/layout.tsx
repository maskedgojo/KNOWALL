import type {Metadata} from 'next';
import {AuthProvider} from '@/components/auth-provider';
import './globals.css';
export const metadata:Metadata={title:{default:'KNOWALL | Green Valley Residency',template:'%s | KNOWALL'},description:'A connected experience for Green Valley residents',referrer:'no-referrer'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body><AuthProvider>{children}</AuthProvider></body></html>}
