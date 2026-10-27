'use client';
import {useAuth} from '@/components/auth-provider';
import {Badge, Card, EmptyState, ErrorState, Loading, PageHeading} from '@/components/ui';
import {shortDate} from '@/lib/format';
import {useLoad} from '@/lib/use-load';
import {operationsApi} from '@/lib/operations-api';
import type {Project} from '@/lib/operations-types';
import {PhotoGallery} from './photos';

export function ProjectCard({project}: {project: Project}) {
  return <Card>
    <div className="between"><h2 className="card-title">{project.title}</h2><Badge value={project.status}/></div>
    <p className="mt-2">{project.description}</p>
    <p className="mt-2 small muted">{project.expected_completion ? `Expected ${shortDate(project.expected_completion)}` : 'No target date'}{project.budget_note ? ` · ${project.budget_note}` : ''}</p>
    <div className="mt-3" aria-label={`${project.progress_percent}% complete`}>
      <div className="small muted mb-1">{project.progress_percent}% complete</div>
      <div style={{height: 8, borderRadius: 4, background: 'rgba(100,116,139,.2)'}}><div style={{width: `${project.progress_percent}%`, height: 8, borderRadius: 4, background: 'currentColor'}}/></div>
    </div>
    {project.milestones.length > 0 && <ol className="mt-3 stack">{project.milestones.map(milestone => <li key={milestone.id} className="notice-card">
      <div className="between"><strong className="small">{milestone.title}</strong><Badge value={milestone.status}/></div>
      <div className="mt-1 small muted">{milestone.percent}%{milestone.due_date ? ` · due ${shortDate(milestone.due_date)}` : ''}</div>
      {milestone.progress_note && <p className="mt-1 small">{milestone.progress_note}</p>}
      {milestone.photos.length > 0 && <div className="mt-2"><PhotoGallery photos={milestone.photos}/></div>}
    </li>)}</ol>}
  </Card>;
}

export default function Development() {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.notices.read');
  const load = useLoad(async () => allowed ? operationsApi.projects() : null, [allowed]);
  if (!allowed) return <PageHeading eyebrow="SOCIETY OPERATIONS" title="Development projects" description="Current resident access is required."/>;
  return <>
    <PageHeading eyebrow="SOCIETY OPERATIONS" title="Development projects" description="Improvement and construction work in the society, with milestones and progress notes."/>
    {load.loading ? <Loading label="Loading projects…"/> : load.error ? <ErrorState error={load.error} onRetry={load.refresh}/> : load.value?.projects.length ? <div className="stack">{load.value.projects.map(project => <ProjectCard key={project.id} project={project}/>)}</div> : <EmptyState title="No projects" description="Society improvement projects will appear here."/>}
  </>;
}
