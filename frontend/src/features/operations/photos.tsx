/* eslint-disable @next/next/no-img-element -- session-scoped blob URLs cannot use Next image optimization */
'use client';
import {useEffect, useState, type FormEvent} from 'react';
import {Alert, Button, Field} from '@/components/ui';
import {privateOperationPhoto} from '@/lib/api';
import {shortDate} from '@/lib/format';
import {errorText} from '@/lib/use-load';
import type {Photo} from '@/lib/operations-types';

/** Loads one private photo through Flask on demand; the object URL is revoked on unmount. */
function PrivatePhoto({photo}: {photo: Photo}) {
  const [file, setFile] = useState<{url: string; type: string} | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => () => { if (file) URL.revokeObjectURL(file.url); }, [file]);
  async function open() {
    setBusy(true); setError('');
    try { setFile(await privateOperationPhoto(photo.id)); } catch (cause) { setError(errorText(cause)); } finally { setBusy(false); }
  }
  return <figure className="notice-card">
    {file?.type.startsWith('image/') ? <img src={file.url} alt={photo.caption || 'Private photo'} style={{maxWidth: '100%', maxHeight: 260, borderRadius: 6}}/>
      : <Button variant="secondary" type="button" busy={busy} onClick={() => void open()}>View photo</Button>}
    {error && <Alert tone="danger">{error}</Alert>}
    <figcaption className="small muted mt-1">{photo.caption || 'No caption'} · {photo.uploaded_by_staff ? 'Staff' : photo.uploaded_by_display_name} · {shortDate(photo.created_at)}</figcaption>
  </figure>;
}

export function PhotoGallery({photos}: {photos: Photo[]}) {
  if (!photos.length) return <p className="small muted">No photos yet.</p>;
  return <div className="stack">{photos.map(photo => <PrivatePhoto key={photo.id} photo={photo}/>)}</div>;
}

/** JPG/PNG up to 5 MB; Flask re-checks type, size and permission. */
export function PhotoUpload({id, onUpload, label = 'Add a photo'}: {id: string; onUpload: (file: File, caption: string) => Promise<unknown>; label?: string}) {
  const [file, setFile] = useState<File | null>(null);
  const [caption, setCaption] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [inputKey, setInputKey] = useState(0);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true); setError('');
    try { await onUpload(file, caption); setFile(null); setCaption(''); setInputKey(key => key + 1); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }
  return <form className="stack mt-3" onSubmit={submit}>
    {error && <Alert tone="warning">{error}</Alert>}
    <label className="field" htmlFor={`${id}-file`}><span className="field-title">{label}</span>
      <input key={inputKey} id={`${id}-file`} className="input" type="file" accept="image/png,image/jpeg" onChange={event => setFile(event.target.files?.[0] ?? null)}/>
      <span className="hint">JPG or PNG, up to 5 MB. Photos are private and only shown to people allowed to see this record.</span>
    </label>
    <Field id={`${id}-caption`} label="Caption (optional)" value={caption} onChange={event => setCaption(event.target.value)} maxLength={200}/>
    <Button type="submit" variant="secondary" busy={busy} disabled={!file}>Upload photo</Button>
  </form>;
}
