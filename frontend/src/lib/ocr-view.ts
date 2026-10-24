/** Presentation-only adapters for Flask OCR responses. No synthetic matches or OCR decisions. */
export type ComparisonStatus = 'MATCH' | 'MISMATCH' | 'UNKNOWN';
export type OcrComparison = {
  field: string;
  label: string;
  entered: string;
  extracted: string;
  status: ComparisonStatus;
};
export type OcrView = {
  id: string;
  status: string;
  createdAt: string | null;
  completedAt: string | null;
  errorMessage: string | null;
  comparisons: OcrComparison[];
  warnings: string[];
};

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
}
function display(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Not provided';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  return 'Not available';
}
function valueString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}
const fieldLabels: Record<string, string> = {
  resident_name: 'Resident name',
  tower: 'Tower',
  flat_number: 'Flat number',
  category: 'Resident category',
  society: 'Society',
};
function labelFor(field: string): string {
  return fieldLabels[field] ?? field.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase());
}
function warningsFrom(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0);
}
function sourceRuns(payload: unknown): unknown[] {
  if (Array.isArray(payload)) return payload;
  const data = record(payload);
  for (const key of ['results', 'ocr_results', 'runs']) {
    if (Array.isArray(data[key])) return data[key] as unknown[];
  }
  if (data.ocr_result && typeof data.ocr_result === 'object') return [data.ocr_result];
  if (data.result && typeof data.result === 'object') return [data.result];
  if (Object.keys(data).length) return [data];
  return [];
}
function parseRun(raw: unknown, extraWarnings: unknown): OcrView | null {
  const run = record(raw);
  if (!Object.keys(run).length) return null;
  const comparisons = Object.entries(record(run.comparison_results)).map(([field, value]) => {
    const item = record(value);
    const backendStatus = valueString(item.status)?.toUpperCase();
    const status: ComparisonStatus = backendStatus === 'MATCH' ? 'MATCH' : backendStatus === 'MISMATCH' ? 'MISMATCH' : 'UNKNOWN';
    return {field,label:labelFor(field),entered:display(item.entered),extracted:display(item.extracted),status};
  });
  const warnings = [...new Set([...warningsFrom(run.warnings), ...warningsFrom(extraWarnings)])];
  return {
    id: valueString(run.id) ?? '',
    status: valueString(run.status)?.toUpperCase() ?? 'UNKNOWN',
    createdAt: valueString(run.created_at),
    completedAt: valueString(run.completed_at),
    errorMessage: valueString(run.error_message),
    comparisons,
    warnings,
  };
}
/** Reads the *latest* saved run; a previous successful run cannot mask a newer failure. */
export function latestOcr(payload: unknown, extraWarnings?: unknown): OcrView | null {
  const runs = sourceRuns(payload).map((entry, index) => ({entry,index}));
  if (!runs.length) return null;
  const timestamps = runs.map(run => {
    const item = record(run.entry);
    const date = item.created_at ?? item.completed_at;
    return typeof date === 'string' ? Date.parse(date) : Number.NaN;
  });
  const ordered = timestamps.every(Number.isFinite)
    ? runs.sort((a,b)=> timestamps[b.index]-timestamps[a.index])
    : runs; // Respect backend order if dates are absent.
  return parseRun(ordered[0].entry, extraWarnings);
}
export function ocrSummary(view: OcrView): {matched:number; mismatched:number; unconfirmed:number} {
  return view.comparisons.reduce((totals,row) => {
    if (row.status === 'MATCH') totals.matched++;
    else if (row.status === 'MISMATCH') totals.mismatched++;
    else totals.unconfirmed++;
    return totals;
  }, {matched:0,mismatched:0,unconfirmed:0});
}
