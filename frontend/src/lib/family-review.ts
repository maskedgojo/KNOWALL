/**
 * Application-detail extension agreed with Flask: sponsor_context is an
 * administrator-only summary, not a resident-facing lookup endpoint.
 * Never fabricate names or infer a sponsor solely from a shared flat.
 */
export type SponsorContext = {
  membership_id: string;
  display_name: string;
  category: 'OWNER' | 'TENANT';
  membership_status: string;
  household_id: string;
  household_label: string | null;
  flat_id: string;
  eligible_to_sponsor: boolean;
  valid_from: string | null;
  valid_until: string | null;
};

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
}
function nonempty(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : null;
}

/** Strictly accept a single documented admin-only shape, never a guessed name. */
export function sponsorFromApplicationDetail(detail: unknown): SponsorContext | null {
  const top = record(detail);
  const application = record(top.application);
  const source = record(top.sponsor_context ?? application.sponsor_context);
  const membership_id = nonempty(source.membership_id);
  const display_name = nonempty(source.display_name);
  const household_id = nonempty(source.household_id);
  const flat_id = nonempty(source.flat_id);
  const category = nonempty(source.category);
  const membership_status = nonempty(source.membership_status);
  if (!membership_id || !display_name || !household_id || !flat_id || !membership_status ||
      (category !== 'OWNER' && category !== 'TENANT') ||
      typeof source.eligible_to_sponsor !== 'boolean') return null;
  // Never display a sponsor record that conflicts with the family application's
  // explicit sponsor binding, household or flat. Missing identifiers mean the
  // backend must supply a complete authorized sponsor context first.
  if (nonempty(application.sponsor_membership_id) !== membership_id ||
      nonempty(application.household_id) !== household_id ||
      nonempty(record(application.flat).id) !== flat_id) return null;
  return {
    membership_id,display_name,household_id,flat_id,
    category,membership_status,eligible_to_sponsor:source.eligible_to_sponsor,
    household_label:nonempty(source.household_label),
    valid_from:nonempty(source.valid_from),valid_until:nonempty(source.valid_until),
  };
}

/** Exact, whitespace/case normalized text equality is only an OCR review hint. */
export function namesComparable(a:string,b:string):boolean {
  const normalize=(s:string)=>s.normalize('NFKC').trim().replace(/\s+/g,' ').toLocaleLowerCase('en');
  return Boolean(a.trim()&&b.trim())&&normalize(a)===normalize(b);
}

export function sponsorReviewStatus(sponsor:SponsorContext|null): 'MISSING'|'INELIGIBLE'|'ELIGIBLE' {
  if (!sponsor) return 'MISSING';
  return sponsor.membership_status==='ACTIVE'&&sponsor.eligible_to_sponsor?'ELIGIBLE':'INELIGIBLE';
}
