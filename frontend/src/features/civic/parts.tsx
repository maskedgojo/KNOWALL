/* eslint-disable @next/next/no-img-element -- session-scoped blob URLs cannot use Next image optimization */
'use client';
import Link from 'next/link';
import {useEffect, useState, type MouseEvent} from 'react';
import {Alert, Badge, Button} from '@/components/ui';
import {civicEvidenceFile} from '@/lib/civic-api';
import {insideCoverage, project, unproject} from '@/lib/civic-geo';
import type {CivicEvidence, CivicIssue, CivicLocality, CivicPriority} from '@/lib/civic-types';
import {pretty, shortDate} from '@/lib/format';
import {errorText} from '@/lib/use-load';

const SIZE = 400;
const TONE: Record<string, string> = {CRITICAL: '#b42318', HIGH: '#d97706', MEDIUM: '#2563eb', LOW: '#667085'};

export interface Pin {id: string; latitude: number; longitude: number; severity: string; label: string}

/** Offline area map: coverage circle plus pins. Click to choose a location when `onPick` is given. */
export function CivicMap({locality, pins = [], selectedId, picked, onSelect, onPick}: {
  locality: CivicLocality; pins?: Pin[]; selectedId?: string | null; picked?: {lat: number; lon: number} | null;
  onSelect?: (id: string) => void; onPick?: (lat: number, lon: number) => void;
}) {
  function click(event: MouseEvent<SVGSVGElement>) {
    if (!onPick) return;
    const box = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * SIZE;
    const y = ((event.clientY - box.top) / box.height) * SIZE;
    const point = unproject({center_lat: locality.center_lat, center_lon: locality.center_lon, radius_m: locality.radius_m}, x, y, SIZE);
    onPick(Number(point.lat.toFixed(6)), Number(point.lon.toFixed(6)));
  }
  const place = (lat: number, lon: number) => project(locality, lat, lon, SIZE);
  const mark = picked ? place(picked.lat, picked.lon) : null;
  return <svg viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={`Area map of ${locality.name}`} onClick={click}
    style={{width: '100%', maxWidth: 520, background: 'var(--surface-2, #f4f6f8)', border: '1px solid var(--border, #d0d5dd)', borderRadius: 8, cursor: onPick ? 'crosshair' : 'default'}}>
    <circle cx={SIZE / 2} cy={SIZE / 2} r={SIZE / 2 - 2} fill="none" stroke="#98a2b3" strokeDasharray="6 4"/>
    <circle cx={SIZE / 2} cy={SIZE / 2} r={5} fill="#475467"/>
    <text x={SIZE / 2 + 9} y={SIZE / 2 + 4} fontSize="11" fill="#475467">Green Valley</text>
    {pins.map(pin => {
      const {x, y} = place(pin.latitude, pin.longitude);
      const active = pin.id === selectedId;
      return <g key={pin.id} onClick={event => {event.stopPropagation(); onSelect?.(pin.id);}} style={{cursor: onSelect ? 'pointer' : 'default'}}>
        <title>{pin.label}</title>
        <circle cx={x} cy={y} r={active ? 10 : 7} fill={TONE[pin.severity] ?? TONE.LOW} stroke="#fff" strokeWidth={active ? 3 : 2}/>
      </g>;
    })}
    {mark && <g><circle cx={mark.x} cy={mark.y} r={11} fill="none" stroke="#12b76a" strokeWidth={3}/><circle cx={mark.x} cy={mark.y} r={3} fill="#12b76a"/></g>}
  </svg>;
}

export function mapNotice(locality: CivicLocality, lat: number, lon: number) {
  return insideCoverage(locality, lat, lon) ? '' : 'This point is outside the area covered by KNOWALL.';
}

/** Loads one private photo through Flask on demand; the object URL is revoked on unmount. */
export function EvidencePhoto({item, onRemove, extra}: {item: CivicEvidence; onRemove?: () => void; extra?: React.ReactNode}) {
  const [file, setFile] = useState<{url: string; type: string} | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => () => {if (file) URL.revokeObjectURL(file.url);}, [file]);
  async function open() {
    setBusy(true); setError('');
    try {setFile(await civicEvidenceFile(item.id));} catch (cause) {setError(errorText(cause));} finally {setBusy(false);}
  }
  return <figure className="notice-card">
    {file ? <img src={file.url} alt={item.caption || 'Issue photo'} style={{maxWidth: '100%', maxHeight: 260, borderRadius: 6}}/>
      : <Button variant="secondary" type="button" busy={busy} onClick={() => void open()}>View photo</Button>}
    {error && <Alert tone="danger">{error}</Alert>}
    <figcaption className="small muted mt-1">{item.caption || 'No caption'} · {item.visibility === 'PRIVATE' ? 'Private to reporter and coordinators' : 'Visible to residents'} · {shortDate(item.created_at)}</figcaption>
    <div className="flex gap-2 flex-wrap mt-1">{extra}{onRemove && <button type="button" className="text-link small" onClick={onRemove}>Remove</button>}</div>
  </figure>;
}

/** Shows the exact inputs behind the priority indicator. It never claims authority action. */
export function PriorityCard({priority}: {priority: CivicPriority}) {
  const i = priority.inputs;
  return <div className="notice-card">
    <div className="between"><strong>Community priority</strong><span className="badge badge-neutral">{pretty(priority.band)} · {priority.score}</span></div>
    <ul className="mt-2 small">
      <li>{i.supporters} supporter{i.supporters === 1 ? '' : 's'} → {i.supporter_points} points</li>
      <li>{i.days_open} days open → {i.age_points} points</li>
      <li>{pretty(i.severity)} severity → {i.severity_points} points</li>
    </ul>
    <p className="mt-2 small muted">{priority.formula}</p>
    <p className="mt-1 small muted">{priority.disclaimer}</p>
  </div>;
}

export function IssueCard({issue, selected, onSelect}: {issue: CivicIssue; selected?: boolean; onSelect?: () => void}) {
  return <div className="notice-card mb-3" style={selected ? {outline: '2px solid var(--primary, #1d4ed8)'} : undefined} onMouseEnter={onSelect}>
    <div className="between"><Link href={`/civic/${issue.id}`}><strong>{issue.title}</strong></Link><Badge value={issue.state}/></div>
    <div className="mt-1 small muted">{pretty(issue.category)} · {pretty(issue.severity)} · {issue.support_count} supporter{issue.support_count === 1 ? '' : 's'} · {issue.reporter_display_name} · {shortDate(issue.created_at)}</div>
    {issue.address_hint && <div className="small muted">{issue.address_hint}</div>}
    {issue.canonical_issue_id && <div className="small mt-1">Merged — see <Link className="text-link" href={`/civic/${issue.canonical_issue_id}`}>the main report</Link></div>}
  </div>;
}

export const CIVIC_NOTE = 'Civic issues are for public roads, lights, drains and similar locality problems. Problems inside the society belong in Maintenance or Suggestions.';
