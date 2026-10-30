'use client';
import {useState, type FormEvent} from 'react';
import {useAuth} from '@/components/auth-provider';
import {Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Loading, PageHeading, TextareaField} from '@/components/ui';
import {errorText, useLoad} from '@/lib/use-load';
import {operationsAdminApi} from '@/lib/operations-api';
import type {Milestone, Project} from '@/lib/operations-types';
import {PhotoGallery, PhotoUpload} from './photos';

export default function AdminDevelopment() {
  const {access} = useAuth();
  const allowed = !!access?.permissions.includes('society.operations.manage');
  const load = useLoad(async () => allowed ? operationsAdminApi.projects() : null, [allowed]);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [expected, setExpected] = useState('');
  const [budget, setBudget] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  if (!allowed) return <PageHeading eyebrow="ADMINISTRATION" title="Development projects" description="Limited to a verified Society Admin."/>;

  async function run(key: string, action: () => Promise<unknown>) {
    setBusy(key); setError('');
    try { await action(); load.refresh(); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(''); }
  }

  function create(event: FormEvent) {
    event.preventDefault();
    void run('create', async () => {
      await operationsAdminApi.createProject({title, description, expected_completion: expected || undefined, budget_note: budget || undefined});
      setTitle(''); setDescription(''); setExpected(''); setBudget('');
    });
  }

  return <>
    <PageHeading eyebrow="ADMINISTRATION" title="Development projects" description="Track improvement projects through milestones. A project can only be completed when every milestone is complete."/>
    {error && <div className="mb-4"><Alert tone="danger">{error}</Alert></div>}
    <div className="grid-2">
      <div className="stack">{load.loading ? <Loading/> : load.error ? <ErrorState error={load.error} onRetry={load.refresh}/> : load.value?.projects.length ? load.value.projects.map(project => <ProjectEditor key={project.id} project={project} busy={busy} run={run}/>) : <EmptyState title="No projects" description="Create the first society project."/>}</div>
      <Card>
        <h2 className="card-title">New project</h2>
        <form className="stack mt-3" onSubmit={create}>
          <Field id="project-title" label="Title" value={title} onChange={event => setTitle(event.target.value)} minLength={3} maxLength={160} required/>
          <TextareaField id="project-description" label="Description" value={description} onChange={event => setDescription(event.target.value)} required/>
          <Field id="project-expected" label="Expected completion" type="date" value={expected} onChange={event => setExpected(event.target.value)}/>
          <Field id="project-budget" label="Budget note (optional)" value={budget} onChange={event => setBudget(event.target.value)} maxLength={300}/>
          <Button type="submit" busy={busy === 'create'}>Create project</Button>
        </form>
      </Card>
    </div>
  </>;
}

function ProjectEditor({project, busy, run}: {project: Project; busy: string; run: (key: string, action: () => Promise<unknown>) => Promise<void>}) {
  const [milestone, setMilestone] = useState('');
  const [due, setDue] = useState('');
  const allDone = project.milestones.length > 0 && project.milestones.every(item => item.status === 'COMPLETED');
  return <Card>
    <div className="between"><h2 className="card-title">{project.title}</h2><Badge value={project.status}/></div>
    <p className="mt-1 small muted">{project.progress_percent}% complete</p>
    <div className="mt-3 stack">{project.milestones.map(item => <MilestoneRow key={`${item.id}-${item.updated_at}`} projectId={project.id} item={item} busy={busy} run={run}/>)}</div>
    <form className="mt-3 flex gap-2 flex-wrap items-end" onSubmit={event => { event.preventDefault(); void run(`add-${project.id}`, async () => { await operationsAdminApi.addMilestone(project.id, {title: milestone, due_date: due || undefined}); setMilestone(''); setDue(''); }); }}>
      <Field id={`milestone-${project.id}`} label="New milestone" value={milestone} onChange={event => setMilestone(event.target.value)} minLength={3} maxLength={160} required/>
      <Field id={`milestone-due-${project.id}`} label="Due" type="date" value={due} onChange={event => setDue(event.target.value)}/>
      <Button type="submit" variant="secondary" busy={busy === `add-${project.id}`}>Add</Button>
    </form>
    {project.status !== 'COMPLETED' && <div className="mt-3"><Button disabled={!allDone} busy={busy === project.id} onClick={() => void run(project.id, () => operationsAdminApi.updateProject(project.id, {status: 'COMPLETED'}))}>Mark project complete</Button></div>}
  </Card>;
}

function MilestoneRow({projectId, item, busy, run}: {projectId: string; item: Milestone; busy: string; run: (key: string, action: () => Promise<unknown>) => Promise<void>}) {
  const [percent, setPercent] = useState(item.percent);
  const [note, setNote] = useState(item.progress_note);
  const key = `m-${item.id}`;
  return <div className="notice-card">
    <div className="between"><strong className="small">{item.title}</strong><Badge value={item.status}/></div>
    {item.photos.length > 0 && <div className="mt-2"><PhotoGallery photos={item.photos}/></div>}
    <PhotoUpload id={`milestone-photo-${item.id}`} label="Add progress photo" onUpload={file => run(`p-${item.id}`, () => operationsAdminApi.milestonePhoto(projectId, item.id, file))}/>
    {item.status !== 'COMPLETED' && <div className="mt-2 flex gap-2 flex-wrap items-end">
      <Field id={`percent-${item.id}`} label="Progress %" type="number" min={0} max={100} value={percent} onChange={event => setPercent(Number(event.target.value))}/>
      <Field id={`note-${item.id}`} label="Progress note" value={note} onChange={event => setNote(event.target.value)} maxLength={4000}/>
      <Button variant="secondary" busy={busy === key} onClick={() => void run(key, () => operationsAdminApi.updateMilestone(projectId, item.id, {percent, status: 'IN_PROGRESS', ...(note.trim() ? {progress_note: note} : {})}))}>Save</Button>
      <Button busy={busy === key} onClick={() => void run(key, () => operationsAdminApi.updateMilestone(projectId, item.id, {status: 'COMPLETED'}))}>Complete</Button>
    </div>}
  </div>;
}
