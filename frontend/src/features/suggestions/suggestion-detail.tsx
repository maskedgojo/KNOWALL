'use client';
import Link from 'next/link';
import {useAuth} from '@/components/auth-provider';
import {Badge, Card, ErrorState, Loading, PageHeading} from '@/components/ui';
import {suggestionApi} from '@/lib/endpoints';
import {pretty, shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';

export default function SuggestionDetail({id}: {id: string}) {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.notices.read');
  const load = useLoad(async () => allowed ? suggestionApi.one(id) : null, [allowed, id]);
  if (!allowed) return <PageHeading eyebrow="RESIDENT PORTAL" title="Suggestion unavailable" description="Current resident access is required to read this suggestion."/>;
  if (load.loading) return <Loading label="Loading suggestion…"/>;
  if (load.error || !load.value) return <ErrorState error={load.error || 'This suggestion is not available.'} onRetry={load.refresh}/>;
  const suggestion = load.value.suggestion;
  return <>
    <PageHeading eyebrow="RESIDENT PORTAL / SUGGESTION" title={suggestion.title} description={`${suggestion.author_display_name} · ${shortDate(suggestion.created_at)}`} action={<Link className="btn btn-secondary" href="/suggestions">All suggestions</Link>}/>
    <Card>
      <div className="between"><Badge value={suggestion.status}/><span className="small muted">{pretty(suggestion.category)}</span></div>
      <p className="mt-4 whitespace-pre-wrap">{suggestion.description}</p>
      <p className="mt-4 small muted">Status stays submitted. Committee decisions are not available.</p>
    </Card>
  </>;
}
