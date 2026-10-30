'use client';
import {useState} from 'react';
import {Alert, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, SelectField, TextareaField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {pretty, shortDate} from '@/lib/format';
import {errorText, useLoad} from '@/lib/use-load';
import {localityAdminApi} from '@/lib/locality-api';
import {isoFromLocal} from '@/lib/operations-types';
import {SEVERITIES, SOURCE_TYPES, type Severity, type SourceType} from '@/lib/locality-types';
import {HistoryList, LocalityBadge, LocalityGate, SafeLink} from '../shared';
import {DeskTabs, ReasonAction} from './common';

export default function ManageAlerts(){return <LocalityGate permission="locality.manage" title="Alerts"><AlertsView/></LocalityGate>}

function AlertsView(){
  const load=useLoad(()=>localityAdminApi.alerts());
  const [creating,setCreating]=useState(false),[error,setError]=useState('');
  async function publish(id:string){setError('');try{await localityAdminApi.publishAlert(id);load.refresh();}catch(cause){setError(errorText(cause));}}
  return <>
    <PageHeading eyebrow="LOCALITY COORDINATOR" title="Alerts" description="Draft an alert with its source, then publish it. Alerts expire on their own." action={<Button onClick={()=>setCreating(open=>!open)}>{creating?'Close form':'New alert'}</Button>}/>
    <DeskTabs/>
    {creating&&<AlertForm onCreated={()=>{setCreating(false);load.refresh();}}/>}
    {error&&<div className="mb-4"><Alert tone="warning">{error}</Alert></div>}
    {load.loading?<Loading label="Loading alerts…"/>:load.error?<ErrorState error={load.error} onRetry={load.refresh}/>:load.value!.alerts.length?<div className="stack">{load.value!.alerts.map(alert=><Card key={alert.id}>
      <div className="between"><h2 className="card-title">{alert.title}</h2><span className="flex gap-2"><LocalityBadge value={alert.severity}/><LocalityBadge value={alert.state}/></span></div>
      <p className="mt-2">{alert.description}</p>
      <p className="small muted mt-2">{alert.source_label} ({pretty(alert.source_type)}){alert.source_url&&<> · <SafeLink href={alert.source_url}>source</SafeLink></>} · {shortDate(alert.starts_at)} to {shortDate(alert.expires_at)} · drafted by {alert.created_by_display_name}</p>
      <div className="flex flex-wrap gap-2 mt-3">
        {alert.state==='DRAFT'&&<Button onClick={()=>void publish(alert.id)}>Publish</Button>}
        {alert.state!=='ARCHIVED'&&<ReasonAction label="Archive" variant="danger" onConfirm={async reason=>{await localityAdminApi.archiveAlert(alert.id,reason);load.refresh();}}/>}
      </div>
      {alert.history&&<details className="mt-3"><summary className="small text-link">History</summary><div className="mt-2"><HistoryList entries={alert.history}/></div></details>}
    </Card>)}</div>:<EmptyState title="No alerts" description="Create the first alert for this locality."/>}
  </>;
}

function AlertForm({onCreated}:{onCreated:()=>void}){
  const [form,setForm]=useState({title:'',description:'',severity:'MEDIUM' as Severity,source_type:'OFFICIAL_NOTICE' as SourceType,source_label:'',source_url:'',starts:'',expires:''});
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[fields,setFields]=useState<Record<string,string>>({});
  const set=(key:keyof typeof form)=>(event:{target:{value:string}})=>setForm(value=>({...value,[key]:event.target.value}));
  async function submit(){setBusy(true);setError('');setFields({});
    try{await localityAdminApi.createAlert({title:form.title.trim(),description:form.description.trim(),severity:form.severity,source_type:form.source_type,source_label:form.source_label.trim(),...(form.source_url.trim()?{source_url:form.source_url.trim()}:{}),starts_at:isoFromLocal(form.starts),expires_at:isoFromLocal(form.expires)});onCreated();}
    catch(cause){setError(errorText(cause));if(cause instanceof ApiError)setFields(cause.fields);}finally{setBusy(false);}}
  return <Card className="mb-4"><h2 className="card-title">New alert (saved as draft)</h2>
    <form className="stack mt-3" onSubmit={event=>{event.preventDefault();void submit();}}>
      <div className="grid-2">
        <Field id="alert-title" label="Title" value={form.title} maxLength={160} error={fields.title} onChange={set('title')}/>
        <SelectField id="alert-severity" label="Severity" value={form.severity} onChange={set('severity')}>{SEVERITIES.map(item=><option key={item} value={item}>{pretty(item)}</option>)}</SelectField>
        <SelectField id="alert-source-type" label="Source type" value={form.source_type} onChange={set('source_type')}>{SOURCE_TYPES.map(item=><option key={item} value={item}>{pretty(item)}</option>)}</SelectField>
        <Field id="alert-source" label="Source" value={form.source_label} maxLength={200} error={fields.source_label} hint="Who issued this information." onChange={set('source_label')}/>
        <Field id="alert-source-url" label={form.source_type==='OFFICIAL_NOTICE'?'Link to the notice (required)':'Source link (optional)'} value={form.source_url} maxLength={500} error={fields.source_url} onChange={set('source_url')}/>
        <span/>
        <Field id="alert-starts" label="Starts" type="datetime-local" value={form.starts} error={fields.starts_at} onChange={set('starts')}/>
        <Field id="alert-expires" label="Expires" type="datetime-local" value={form.expires} error={fields.expires_at} hint="At most 30 days after the start." onChange={set('expires')}/>
      </div>
      <TextareaField id="alert-description" label="Details" value={form.description} maxLength={4000} onChange={set('description')}/>
      {fields.description&&<span className="field-error">{fields.description}</span>}
      {error&&<Alert tone="warning">{error}</Alert>}
      <div><Button type="submit" busy={busy}>Save draft</Button></div>
    </form>
  </Card>;
}
