'use client';
import {useState} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, SelectField, TextareaField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {pretty, shortDate} from '@/lib/format';
import {errorText, useLoad} from '@/lib/use-load';
import {localityApi} from '@/lib/locality-api';
import {isoFromLocal, timeRange} from '@/lib/operations-types';
import {EVENT_CATEGORIES, type EventCategory, type LocalEvent} from '@/lib/locality-types';
import {LocalityBadge, LocalityGate, ReportButton} from './shared';

export default function LocalityEvents(){return <LocalityGate permission="locality.read" title="Local events"><EventsView/></LocalityGate>}

function EventsView(){
  const {access}=useAuth();const can=(permission:string)=>!!access?.permissions.includes(permission);
  const [when,setWhen]=useState<'upcoming'|'past'>('upcoming'),[category,setCategory]=useState('');
  const events=useLoad(()=>localityApi.events(when,category),[when,category]);
  const [submitting,setSubmitting]=useState(false);
  return <>
    <PageHeading eyebrow="LOCALITY" title="Local events" description="Neighbourhood events reviewed by the locality coordinator. Society events appear here only when the Society Admin shares them." action={can('locality.listings.suggest')?<Button variant="secondary" onClick={()=>setSubmitting(open=>!open)}>Suggest an event</Button>:undefined}/>
    {submitting&&<SubmitEvent onDone={()=>setSubmitting(false)}/>}
    {can('society.operations.manage')&&<ShareSocietyEvents/>}
    <Card className="mb-4"><div className="grid-2">
      <SelectField id="events-when" label="Show" value={when} onChange={event=>setWhen(event.target.value as 'upcoming'|'past')}><option value="upcoming">Upcoming and ongoing</option><option value="past">Past</option></SelectField>
      <SelectField id="events-category" label="Category" value={category} onChange={event=>setCategory(event.target.value)}><option value="">All</option>{EVENT_CATEGORIES.map(item=><option key={item} value={item}>{pretty(item)}</option>)}</SelectField>
    </div></Card>
    {events.loading?<Loading label="Loading events…"/>:events.error?<ErrorState error={events.error} onRetry={events.refresh}/>:events.value!.events.length?
      <div className="stack">{events.value!.events.map(event=><EventCard key={event.id} event={event}/>)}</div>
      :<EmptyState title="No events" description={when==='upcoming'?'Approved local events will appear here.':'No past events yet.'}/>}
    {can('locality.listings.suggest')&&<MySubmissions/>}
  </>;
}

function EventCard({event}:{event:LocalEvent}){
  return <Card>
    <div className="between"><h2 className="card-title">{event.title}</h2><LocalityBadge value={event.timing==='COMPLETED'?'EXPIRED':event.timing==='ONGOING'?'ACTIVE':'SCHEDULED'} label={pretty(event.timing)}/></div>
    <p className="small muted mt-1">{timeRange(event.starts_at,event.ends_at)} · {event.venue} · {pretty(event.category)} · Organised by {event.organizer}{event.shared_by_society?' · Shared by the society':''}</p>
    <p className="mt-2">{event.description}</p>
    {event.timing!=='COMPLETED'&&<ReportButton target="EVENT" id={event.id}/>}
  </Card>;
}

function SubmitEvent({onDone}:{onDone:()=>void}){
  const [form,setForm]=useState({title:'',description:'',organizer:'',venue:'',category:'OTHER' as EventCategory,starts:'',ends:''});
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[fields,setFields]=useState<Record<string,string>>({}),[done,setDone]=useState(false);
  const set=(key:keyof typeof form)=>(event:{target:{value:string}})=>setForm(value=>({...value,[key]:event.target.value}));
  async function submit(){setBusy(true);setError('');setFields({});
    try{await localityApi.submitEvent({title:form.title.trim(),description:form.description.trim(),organizer:form.organizer.trim(),venue:form.venue.trim(),category:form.category,starts_at:isoFromLocal(form.starts),ends_at:isoFromLocal(form.ends)});setDone(true);}
    catch(cause){setError(errorText(cause));if(cause instanceof ApiError)setFields(cause.fields);}finally{setBusy(false);}}
  if(done)return <div className="mb-4"><Alert tone="success">Submitted. The event appears once a coordinator approves it. <button className="text-link" onClick={onDone}>Close</button></Alert></div>;
  return <Card className="mb-4"><h2 className="card-title">Suggest a local event</h2>
    <form className="stack mt-3" onSubmit={event=>{event.preventDefault();void submit();}}>
      <div className="grid-2">
        <Field id="event-title" label="Title" value={form.title} maxLength={160} error={fields.title} onChange={set('title')}/>
        <Field id="event-organizer" label="Organiser" value={form.organizer} maxLength={160} error={fields.organizer} onChange={set('organizer')}/>
        <Field id="event-venue" label="Venue" value={form.venue} maxLength={160} error={fields.venue} onChange={set('venue')}/>
        <SelectField id="event-category" label="Category" value={form.category} onChange={set('category')}>{EVENT_CATEGORIES.map(item=><option key={item} value={item}>{pretty(item)}</option>)}</SelectField>
        <Field id="event-starts" label="Starts" type="datetime-local" value={form.starts} error={fields.starts_at} onChange={set('starts')}/>
        <Field id="event-ends" label="Ends" type="datetime-local" value={form.ends} error={fields.ends_at} onChange={set('ends')}/>
      </div>
      <TextareaField id="event-description" label="Description" value={form.description} maxLength={4000} onChange={set('description')}/>
      {fields.description&&<span className="field-error">{fields.description}</span>}
      {error&&<Alert tone="warning">{error}</Alert>}
      <div className="flex gap-2"><Button type="submit" busy={busy}>Submit for review</Button><Button type="button" variant="ghost" onClick={onDone}>Cancel</Button></div>
    </form>
  </Card>;
}

/** Society Admin hand-off from Module 3: only opted-in published events, public fields only. */
function ShareSocietyEvents(){
  const load=useLoad(()=>localityApi.shareable());
  const [busy,setBusy]=useState(''),[message,setMessage]=useState(''),[category,setCategory]=useState<EventCategory>('CULTURAL');
  async function share(id:string){setBusy(id);setMessage('');try{await localityApi.shareSocietyEvent(id,category);setMessage('Shared. It will be listed after coordinator approval.');load.refresh();}catch(cause){setMessage(errorText(cause));}finally{setBusy('');}}
  return <Card className="mb-4">
    <h2 className="card-title">Share society events with the locality</h2>
    <p className="small muted mt-1">Only events you opted in for locality listing in Society events are shown. Title, description, venue and time are shared; RSVP lists and capacity never are.</p>
    {message&&<div className="mt-2"><Alert tone="info">{message}</Alert></div>}
    {load.loading?<Loading label="Loading society events…"/>:load.error?<ErrorState error={load.error} onRetry={load.refresh}/>:load.value!.events.length?<>
      <div className="mt-3 max-w-xs"><SelectField id="share-category" label="List under" value={category} onChange={event=>setCategory(event.target.value as EventCategory)}>{EVENT_CATEGORIES.map(item=><option key={item} value={item}>{pretty(item)}</option>)}</SelectField></div>
      <ul className="stack mt-3">{load.value!.events.map(event=><li key={event.id} className="between"><span>{event.title} · <span className="small muted">{timeRange(event.starts_at,event.ends_at)} · {event.venue}</span></span><Button variant="secondary" busy={busy===event.id} onClick={()=>void share(event.id)}>Share</Button></li>)}</ul>
    </>:<p className="small muted mt-3">No opted-in society events are waiting to be shared.</p>}
  </Card>;
}

function MySubmissions(){
  const load=useLoad(()=>localityApi.myEvents());
  if(load.loading||load.error||!load.value?.events.length)return null;
  return <Card className="mt-6"><h2 className="card-title">My submitted events</h2>
    <ul className="stack mt-3 small">{load.value.events.map(event=><li key={event.id}><strong>{event.title}</strong> · {shortDate(event.starts_at)} · <LocalityBadge value={event.status??'PENDING'}/>{event.decision_reason&&<div className="muted">Coordinator: {event.decision_reason}</div>}</li>)}</ul>
  </Card>;
}
