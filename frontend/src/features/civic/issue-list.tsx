'use client';
import Link from 'next/link';
import {useState} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Card, EmptyState, ErrorState, Loading, PageHeading, SelectField} from '@/components/ui';
import {civicApi} from '@/lib/civic-api';
import {CIVIC_CATEGORIES} from '@/lib/civic-types';
import {pretty} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import {CIVIC_NOTE, CivicMap, IssueCard} from './parts';

export default function CivicIssueList() {
  const {access} = useAuth();
  const canReport = !!access?.permissions.includes('civic.issues.create');
  const [mine, setMine] = useState(false);
  const [category, setCategory] = useState('');
  const [sort, setSort] = useState<'recent' | 'support' | 'priority'>('recent');
  const [selected, setSelected] = useState<string | null>(null);
  const locality = useLoad(() => civicApi.locality(), []);
  const issues = useLoad(() => civicApi.list({mine, category: category || undefined, sort, limit: 100}), [mine, category, sort]);

  if (!canReport) return <PageHeading eyebrow="CIVIC ISSUES" title="Civic issues" description="Current resident access is required."/>;
  const list = issues.value?.issues ?? [];
  return <>
    <PageHeading eyebrow="CIVIC ISSUES" title="Locality issues" description="Report and support problems on public roads and infrastructure around Green Valley."
      action={<Link className="btn btn-primary" href="/civic/new">Report an issue</Link>}/>
    <Alert tone="info">{CIVIC_NOTE}</Alert>
    <div className="flex gap-2 flex-wrap mt-4">
      <SelectField id="civic-scope" label="Show" value={mine ? 'mine' : 'all'} onChange={event => setMine(event.target.value === 'mine')}>
        <option value="all">Open community issues</option><option value="mine">My reports (all states)</option>
      </SelectField>
      <SelectField id="civic-category" label="Category" value={category} onChange={event => setCategory(event.target.value)}>
        <option value="">All categories</option>{CIVIC_CATEGORIES.map(item => <option key={item} value={item}>{pretty(item)}</option>)}
      </SelectField>
      <SelectField id="civic-sort" label="Sort by" value={sort} onChange={event => setSort(event.target.value as typeof sort)}>
        <option value="recent">Newest</option><option value="support">Most supported</option><option value="priority">Community priority</option>
      </SelectField>
    </div>
    <div className="grid-2 mt-4">
      <Card>
        <h2 className="card-title">Area map</h2>
        <p className="small muted mt-1">Pins are coloured by severity. Select a pin to highlight its report.</p>
        <div className="mt-3">{locality.loading ? <Loading label="Loading map…"/> : locality.error || !locality.value ? <ErrorState error={locality.error || 'Map unavailable.'} onRetry={locality.refresh}/>
          : <CivicMap locality={locality.value.locality} selectedId={selected} onSelect={setSelected} pins={list.map(issue => ({id: issue.id, latitude: issue.latitude, longitude: issue.longitude, severity: issue.severity, label: issue.title}))}/>}</div>
      </Card>
      <Card>
        <h2 className="card-title">{mine ? 'My reports' : 'Issues'}{issues.value ? ` (${issues.value.total})` : ''}</h2>
        <div className="mt-3">{issues.loading ? <Loading label="Loading issues…"/> : issues.error ? <ErrorState error={issues.error} onRetry={issues.refresh}/>
          : list.length ? list.map(issue => <IssueCard key={issue.id} issue={issue} selected={issue.id === selected} onSelect={() => setSelected(issue.id)}/>)
            : <EmptyState title="Nothing here yet" description={mine ? 'Reports you create will appear here, including drafts.' : 'No open issues match. Report one to get started.'}/>}</div>
      </Card>
    </div>
  </>;
}
