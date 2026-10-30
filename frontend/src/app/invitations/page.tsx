'use client';
import {useEffect,useState} from 'react';
import {useRouter} from 'next/navigation';
import {Protected} from '@/components/shell';
import {Loading} from '@/components/ui';
import Invitations from '@/features/onboarding/invitations';
import {captureInvitationLink} from '@/lib/invitation-handoff';
export default function Page(){
  const [checked,setChecked]=useState(false),router=useRouter();
  useEffect(()=>{
    const invite=captureInvitationLink();
    if(invite){router.replace('/invitations/accept');return;}
    Promise.resolve().then(()=>setChecked(true));
  },[router]);
  return checked?<Protected><Invitations/></Protected>:<div className="center-screen"><Loading label="Opening invitations…"/></div>;
}
