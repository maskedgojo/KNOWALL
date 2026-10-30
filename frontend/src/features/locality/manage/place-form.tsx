'use client';
import {useState} from 'react';
import {Alert, Button, Field, SelectField, TextareaField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {errorText} from '@/lib/use-load';
import type {Category, Place, PlaceInput} from '@/lib/locality-types';

const blank=(value:string)=>value.trim()===''?null:value.trim();

/** Create or edit a listing. Edits send only changed fields; Flask re-validates everything. */
export function PlaceForm({categories,place,submitLabel,onSubmit,onCancel}:{categories:Category[];place?:Place;submitLabel:string;onSubmit:(body:PlaceInput,note:string)=>Promise<unknown>;onCancel?:()=>void}){
  const initial={name:place?.name??'',category:place?.category.key??categories[0]?.key??'',description:place?.description??'',address:place?.address??'',
    latitude:place?.latitude==null?'':String(place.latitude),longitude:place?.longitude==null?'':String(place.longitude),phone:place?.phone??'',
    website_url:place?.website_url??'',source_label:place?.source_label??'',source_url:place?.source_url??'',data_origin:place?.data_origin??'FICTIONAL_DEMO'};
  const [form,setForm]=useState(initial),[note,setNote]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[fields,setFields]=useState<Record<string,string>>({});
  const set=(key:keyof typeof form)=>(event:{target:{value:string}})=>setForm(value=>({...value,[key]:event.target.value}));
  function body():PlaceInput{
    const full:PlaceInput={name:form.name.trim(),category:form.category,description:blank(form.description),address:blank(form.address),
      latitude:form.latitude.trim()===''?null:Number(form.latitude),longitude:form.longitude.trim()===''?null:Number(form.longitude),
      phone:blank(form.phone),website_url:blank(form.website_url),source_label:form.source_label.trim(),source_url:blank(form.source_url),data_origin:form.data_origin as PlaceInput['data_origin']};
    if(!place)return full;
    const changed:PlaceInput={};
    for(const key of Object.keys(full) as (keyof PlaceInput)[]){if(form[key]!==initial[key])(changed as Record<string,unknown>)[key]=full[key];}
    // Coordinates travel as a pair.
    if('latitude' in changed||'longitude' in changed){changed.latitude=full.latitude;changed.longitude=full.longitude;}
    return changed;
  }
  async function submit(){setBusy(true);setError('');setFields({});try{await onSubmit(body(),note.trim());}catch(cause){setError(errorText(cause));if(cause instanceof ApiError)setFields(cause.fields);}finally{setBusy(false);}}
  return <form className="stack" onSubmit={event=>{event.preventDefault();void submit();}}>
    <div className="grid-2">
      <Field id="place-name" label="Name" value={form.name} maxLength={160} error={fields.name} onChange={set('name')}/>
      <SelectField id="place-category-input" label="Category" value={form.category} error={fields.category} onChange={set('category')}>{categories.map(item=><option key={item.key} value={item.key}>{item.label}</option>)}</SelectField>
      <Field id="place-address" label="Address" value={form.address} maxLength={300} error={fields.address} onChange={set('address')}/>
      <Field id="place-phone" label="Phone" value={form.phone} maxLength={40} error={fields.phone} onChange={set('phone')}/>
      <Field id="place-lat" label="Latitude" inputMode="decimal" value={form.latitude} error={fields.latitude} hint="Leave both blank if unknown." onChange={set('latitude')}/>
      <Field id="place-lng" label="Longitude" inputMode="decimal" value={form.longitude} error={fields.longitude} onChange={set('longitude')}/>
      <Field id="place-website" label="Website" value={form.website_url} maxLength={500} error={fields.website_url} onChange={set('website_url')}/>
      <SelectField id="place-origin" label="Data origin" value={form.data_origin} error={fields.data_origin} onChange={set('data_origin')}><option value="FICTIONAL_DEMO">Fictional demo listing</option><option value="REAL_WORLD">Real-world listing (needs a source link)</option></SelectField>
      <Field id="place-source" label="Source" value={form.source_label} maxLength={200} error={fields.source_label} hint="Where this information came from." onChange={set('source_label')}/>
      <Field id="place-source-url" label="Source link" value={form.source_url} maxLength={500} error={fields.source_url} onChange={set('source_url')}/>
    </div>
    <TextareaField id="place-description" label="Description" value={form.description} maxLength={2000} onChange={set('description')}/>
    {place&&<Field id="place-note" label="Change note (optional)" value={note} maxLength={500} onChange={event=>setNote(event.target.value)}/>}
    {error&&<Alert tone="warning">{error}</Alert>}
    <div className="flex gap-2"><Button type="submit" busy={busy}>{submitLabel}</Button>{onCancel&&<Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>}</div>
  </form>;
}
