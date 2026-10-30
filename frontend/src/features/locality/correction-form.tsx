'use client';
import {useState} from 'react';
import {Alert, Button, Field, SelectField, TextareaField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {errorText} from '@/lib/use-load';
import {ISSUE_LABEL, ISSUES, type Category, type CorrectionInput, type CorrectionIssue} from '@/lib/locality-types';

const TEXT_FIELD:Partial<Record<CorrectionIssue,{label:string;hint:string}>>={
  WRONG_PHONE:{label:'Correct phone number',hint:'Digits, spaces, +, - or brackets.'},
  WRONG_ADDRESS:{label:'Correct address',hint:'As it appears on the signboard.'},
  WRONG_NAME:{label:'Correct name',hint:''},
  WRONG_WEBSITE:{label:'Correct website',hint:'A full https:// link.'},
  OTHER:{label:'Suggested change (optional)',hint:''},
  MISSING_SERVICE:{label:'Name of the missing service',hint:''},
};

/** Builds only the fields Flask accepts for each issue type; Flask validates again. */
export function CorrectionForm({categories,missing=false,onSubmit,onCancel}:{categories:Category[];missing?:boolean;onSubmit:(body:CorrectionInput)=>Promise<unknown>;onCancel?:()=>void}){
  const [issue,setIssue]=useState<CorrectionIssue>(missing?'MISSING_SERVICE':'WRONG_PHONE');
  const [value,setValue]=useState(''),[lat,setLat]=useState(''),[lng,setLng]=useState(''),[category,setCategory]=useState(categories[0]?.key??'');
  const [reason,setReason]=useState(''),[source,setSource]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[fields,setFields]=useState<Record<string,string>>({});
  const text=TEXT_FIELD[issue];
  async function submit(){
    const body:CorrectionInput={issue_type:issue,reason:reason.trim()};
    if(text&&value.trim())body.proposed_value=value.trim();
    if(issue==='WRONG_COORDINATES'){body.proposed_latitude=Number(lat);body.proposed_longitude=Number(lng);}
    if(issue==='WRONG_CATEGORY'||issue==='MISSING_SERVICE')body.proposed_category=category;
    if(source.trim())body.source_url=source.trim();
    setBusy(true);setError('');setFields({});
    try{await onSubmit(body);}catch(cause){setError(errorText(cause));if(cause instanceof ApiError)setFields(cause.fields);}finally{setBusy(false);}
  }
  return <form className="stack" onSubmit={event=>{event.preventDefault();void submit();}}>
    {!missing&&<SelectField id="correction-issue" label="What is wrong?" value={issue} onChange={event=>{setIssue(event.target.value as CorrectionIssue);setValue('');setFields({});}}>
      {ISSUES.map(item=><option key={item} value={item}>{ISSUE_LABEL[item]}</option>)}
    </SelectField>}
    {text&&<Field id="correction-value" label={text.label} hint={text.hint} value={value} maxLength={500} error={fields.proposed_value} onChange={event=>setValue(event.target.value)}/>}
    {issue==='WRONG_COORDINATES'&&<div className="grid-2">
      <Field id="correction-lat" label="Latitude" inputMode="decimal" value={lat} error={fields.proposed_latitude} onChange={event=>setLat(event.target.value)}/>
      <Field id="correction-lng" label="Longitude" inputMode="decimal" value={lng} error={fields.proposed_longitude} onChange={event=>setLng(event.target.value)}/>
    </div>}
    {(issue==='WRONG_CATEGORY'||issue==='MISSING_SERVICE')&&<SelectField id="correction-category" label={missing?'Category':'Correct category'} value={category} error={fields.proposed_category} onChange={event=>setCategory(event.target.value)}>
      {categories.map(item=><option key={item.key} value={item.key}>{item.label}</option>)}
    </SelectField>}
    <TextareaField id="correction-reason" label="How do you know? (required)" value={reason} maxLength={1000} placeholder="For example: I called the old number and it is disconnected; the new number is on the shop board." onChange={event=>setReason(event.target.value)}/>
    {fields.reason&&<span className="field-error">{fields.reason}</span>}
    <Field id="correction-source" label="Supporting link (optional)" hint="An official page or notice, if you have one." value={source} maxLength={500} error={fields.source_url} onChange={event=>setSource(event.target.value)}/>
    {error&&<Alert tone="warning">{error}</Alert>}
    <p className="small muted">A coordinator reviews every report before the listing changes. Your name is not shown to other residents.</p>
    <div className="flex gap-2"><Button type="submit" busy={busy} disabled={reason.trim().length<10}>Submit for review</Button>{onCancel&&<Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>}</div>
  </form>;
}
