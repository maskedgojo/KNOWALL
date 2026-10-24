'use client';
import {createContext,useCallback,useContext,useEffect,useState} from 'react';
import {authApi,residentApi} from '@/lib/endpoints';
import {clearCsrf} from '@/lib/api';
import {clearPendingInvitation} from '@/lib/invitation-handoff';
import type {Access,User} from '@/lib/types';
import {useRouter} from 'next/navigation';
type State={user:User|null;access:Access|null;loading:boolean;refresh:()=>Promise<void>;signedIn:(user:User)=>Promise<void>;logout:(options?:{preserveInvitation?:boolean})=>Promise<void>};
const AuthContext=createContext<State|null>(null);
export const adminRole=(a:Access|null)=>!!a?.roles.some(r=>r==='SOCIETY_ADMIN'||r==='PLATFORM_ADMIN');
export function AuthProvider({children}:{children:React.ReactNode}){
  const [user,setUser]=useState<User|null>(null),[access,setAccess]=useState<Access|null>(null),[loading,setLoading]=useState(true);
  const router=useRouter();
  const refresh=useCallback(async()=>{
    try{const {user:current}=await authApi.me();const permission=await residentApi.access();setUser(current);setAccess(permission);}catch{setUser(null);setAccess(null);}finally{setLoading(false);}
  },[]);
  const signedIn=useCallback(async(current:User)=>{setLoading(true);setUser(current);try{setAccess(await residentApi.access());}finally{setLoading(false);}},[]);
  const logout=useCallback(async(options?:{preserveInvitation?:boolean})=>{
    await authApi.logout();
    if(!options?.preserveInvitation) clearPendingInvitation();
    setUser(null);setAccess(null);router.replace('/login');
  },[router]);
  useEffect(()=>{void Promise.resolve().then(refresh);const onExpired=()=>{clearCsrf();setUser(null);setAccess(null);setLoading(false);};const onVisibility=()=>{if(document.visibilityState==='visible')void refresh();};const onFocus=()=>void refresh();window.addEventListener('knowall:session-expired',onExpired);document.addEventListener('visibilitychange',onVisibility);window.addEventListener('focus',onFocus);return()=>{window.removeEventListener('knowall:session-expired',onExpired);document.removeEventListener('visibilitychange',onVisibility);window.removeEventListener('focus',onFocus)};},[refresh]);
  return <AuthContext.Provider value={{user,access,loading,refresh,signedIn,logout}}>{children}</AuthContext.Provider>;
}
export function useAuth(){const ctx=useContext(AuthContext);if(!ctx)throw new Error('Missing AuthProvider');return ctx}
