'use client';
import {useState} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert,Button,Card,ErrorState,Field,Loading,PageHeading} from '@/components/ui';
import {residentApi} from '@/lib/endpoints';
import {errorText,useLoad} from '@/lib/use-load';
import type {User} from '@/lib/types';
export default function Profile(){
 const load=useLoad(()=>residentApi.profile(),[]);
 return <><PageHeading eyebrow="ACCOUNT / PERSONAL INFORMATION" title="Personal profile" description="Your personal information is private and not shared in household directory views."/>{load.loading?<Loading/>:load.error?<ErrorState error={load.error} onRetry={load.refresh}/>:load.value&&<ProfileEditor key={JSON.stringify(load.value.user)} initial={load.value.user} reload={load.refresh}/>}</>;
}
function ProfileEditor({initial,reload}:{initial:User;reload:()=>void}){
 const {refresh}=useAuth();
 const [name,setName]=useState(initial.display_name),[phone,setPhone]=useState(initial.phone??''),[dob,setDob]=useState(initial.date_of_birth??''),[occupation,setOccupation]=useState(initial.occupation??''),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
 async function save(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');setMessage('');try{await residentApi.updateProfile({display_name:name.trim(),phone:phone.trim()||null,date_of_birth:dob||null,occupation:occupation.trim()||null});await refresh();reload();setMessage('Your profile has been updated successfully.')}catch(e){setError(errorText(e))}finally{setBusy(false)}}
 return <div className="grid-2"><Card><h2 className="card-title mb-5">Edit your information</h2>{message&&<div className="mb-4"><Alert tone="success">{message}</Alert></div>}{error&&<div className="mb-4"><Alert tone="danger">{error}</Alert></div>}<form onSubmit={save} className="form-stack"><Field label="Full name" id="profile-name" required minLength={2} maxLength={120} value={name} onChange={e=>setName(e.target.value)}/><Field label="Phone" id="profile-phone" type="tel" value={phone} onChange={e=>setPhone(e.target.value)}/><Field label="Date of birth (optional)" id="profile-dob" type="date" value={dob} onChange={e=>setDob(e.target.value)}/><Field label="Occupation (optional)" id="profile-occupation" maxLength={100} value={occupation} onChange={e=>setOccupation(e.target.value)}/><div className="form-actions"><Button type="submit" busy={busy}>Save changes</Button></div></form></Card><Card><h2 className="card-title mb-4">Privacy & identity</h2><div className="info-list"><div className="info-row"><span>Email address</span><span>{initial.email}</span></div><div className="info-row"><span>Email verification</span><span>{initial.email_verified?'Verified':'Pending'}</span></div><div className="info-row"><span>Account status</span><span>{initial.account_status}</span></div></div><div className="mt-5"><Alert tone="info">Date of birth and occupation remain private to your account. Membership and occupancy permissions are controlled by the Flask backend.</Alert></div></Card></div>;
}
