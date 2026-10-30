'use client';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {useState, type FormEvent} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, SelectField, TextareaField} from '@/components/ui';
import {ApiError} from '@/lib/api';
import {suggestionApi} from '@/lib/endpoints';
import {pretty, shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import type {SuggestionCategory} from '@/lib/types';

const CATEGORIES: SuggestionCategory[] = ['MAINTENANCE', 'SAFETY', 'AMENITIES', 'COMMUNITY', 'OTHER'];

export default function SuggestionList() {
  const {access} = useAuth();
  const router = useRouter();
  const allowed = !!access?.permissions.includes('society.notices.read');
  const load = useLoad(async () => allowed ? suggestionApi.list() : {suggestions: [], pagination: {limit: 30, offset: 0}}, [allowed]);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState<SuggestionCategory>('MAINTENANCE');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (!allowed) return <PageHeading eyebrow="RESIDENT PORTAL" title="Suggestions" description="Current resident access is required to view and submit suggestions."/>;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError('');
    try {
      const created = await suggestionApi.create({title, description, category});
      router.push(`/suggestions/${created.suggestion.id}`);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'The suggestion could not be submitted.');
    } finally {
      setBusy(false);
    }
  }

  return <>
    <PageHeading eyebrow="RESIDENT PORTAL" title="Suggestions" description="Ideas from eligible residents. A suggestion stays submitted until a committee decision workflow is approved."/>
    <div className="grid-2">
      <div>
        {load.loading ? <Loading label="Loading suggestions…"/> : load.error ? <ErrorState error={load.error} onRetry={load.refresh}/> : load.value?.suggestions.length ? <div className="stack">{load.value.suggestions.map(suggestion => <Card key={suggestion.id}><div className="between"><h2 className="card-title">{suggestion.title}</h2><Badge value={suggestion.status}/></div><p className="mt-3">{suggestion.description}</p><div className="mt-3 between"><span className="small muted">{pretty(suggestion.category)} · {suggestion.author_display_name} · {shortDate(suggestion.created_at)}</span><Link className="text-link small" href={`/suggestions/${suggestion.id}`}>Open suggestion</Link></div></Card>)}</div> : <EmptyState title="No suggestions yet" description="Submit an idea for other eligible residents to read."/>}
      </div>
      <Card>
        <h2 className="card-title">Submit a suggestion</h2>
        <form className="stack mt-4" onSubmit={submit}>
          {error && <Alert tone="warning">{error}</Alert>}
          <Field id="suggestion-title" label="Title" value={title} onChange={event => setTitle(event.target.value)} minLength={3} maxLength={160} required/>
          <SelectField id="suggestion-category" label="Category" value={category} onChange={event => setCategory(event.target.value as SuggestionCategory)} required>
            {CATEGORIES.map(item => <option key={item} value={item}>{pretty(item)}</option>)}
          </SelectField>
          <TextareaField id="suggestion-description" label="Description" value={description} onChange={event => setDescription(event.target.value)} minLength={1} maxLength={8000} required/>
          <Button type="submit" busy={busy}>Submit suggestion</Button>
        </form>
      </Card>
    </div>
  </>;
}
