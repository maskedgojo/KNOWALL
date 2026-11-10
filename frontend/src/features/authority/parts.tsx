/* eslint-disable @next/next/no-img-element -- session-scoped blob URLs cannot use Next image optimization */
'use client';
import {useEffect, useState} from 'react';
import {Alert, Button} from '@/components/ui';
import {authorityFile} from '@/lib/authority-api';
import {SIMULATION_LABEL, type CaseStatus} from '@/lib/authority-types';
import {pretty, shortDate} from '@/lib/format';
import {errorText} from '@/lib/use-load';

/** Required on every Module 6 screen: the authority workflow is simulated. */
export function SimulationBanner() {
  return <div className="alert alert-warning" role="note" data-testid="simulation-banner">
    <strong>SIMULATED AUTHORITY</strong>
    <div>{SIMULATION_LABEL}</div>
  </div>;
}

const TONE: Record<CaseStatus, string> = {
  ROUTED: 'badge-neutral', ACKNOWLEDGED: 'badge-neutral', CLARIFICATION_REQUESTED: 'badge-warning', IN_PROGRESS: 'badge-neutral',
  RESOLVED: 'badge-warning', REOPENED: 'badge-danger', CLOSED: 'badge-success',
};

export function CaseBadge({status, overdue}: {status: CaseStatus; overdue?: boolean}) {
  return <span className="flex gap-1 items-center">
    <span className={`badge ${TONE[status] ?? 'badge-neutral'}`}>{pretty(status)}</span>
    {overdue && <span className="badge badge-danger">Overdue</span>}
  </span>;
}

export function dateTime(value: string | null | undefined) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('en-IN', {day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'});
}

/** Loads one private photo through Flask on demand; the object URL is revoked on unmount. */
export function PrivatePhoto({path, caption, meta}: {path: string; caption: string; meta?: string}) {
  const [file, setFile] = useState<{url: string; type: string} | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => () => {if (file) URL.revokeObjectURL(file.url);}, [file]);
  async function open() {
    setBusy(true); setError('');
    try {setFile(await authorityFile(path));} catch (cause) {setError(errorText(cause));} finally {setBusy(false);}
  }
  return <figure className="notice-card">
    {file ? <img src={file.url} alt={caption || 'Case photo'} style={{maxWidth: '100%', maxHeight: 260, borderRadius: 6}}/>
      : <Button variant="secondary" type="button" busy={busy} onClick={() => void open()}>View photo</Button>}
    {error && <Alert tone="danger">{error}</Alert>}
    <figcaption className="small muted mt-1">{caption || 'No caption'}{meta ? ` · ${meta}` : ''}</figcaption>
  </figure>;
}

export function evidenceMeta(item: {evidence_type: string; round: number; created_at: string}) {
  return `${pretty(item.evidence_type)} · round ${item.round} · ${shortDate(item.created_at)}`;
}
