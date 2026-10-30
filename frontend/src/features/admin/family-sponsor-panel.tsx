import {Alert,Badge,Card} from '@/components/ui';
import {pretty,shortDate} from '@/lib/format';
import {type SponsorContext,sponsorReviewStatus} from '@/lib/family-review';

/** Sensitive sponsor identity is supplied only by the admin application-detail API. */
export function FamilySponsorPanel({sponsor,relationship}:{sponsor:SponsorContext|null;relationship:string}) {
  const state=sponsorReviewStatus(sponsor);
  return <Card className="mb-5" aria-label="Verified family sponsor context">
    <div className="card-head">
      <div>
        <h2 className="card-title">Family sponsor & household verification</h2>
        <p className="small muted mt-2">Family applications are evaluated against the linked eligible sponsor, not automatically against the applicant name on property evidence.</p>
      </div>
      <Badge value={state==='ELIGIBLE'?'ACTIVE':state==='INELIGIBLE'?'NEEDS_REVIEW':'NOT_VERIFIED'}/>
    </div>
    {sponsor?<>
      <div className="admin-review-summary">
        <div><span>Linked sponsor name</span><strong>{sponsor.display_name}</strong></div>
        <div><span>Sponsor membership</span><strong>{pretty(sponsor.category)} · {pretty(sponsor.membership_status)}</strong></div>
        <div><span>Relationship to sponsor</span><strong>{pretty(relationship)||'Unknown'}</strong></div>
        <div><span>Household</span><strong>{sponsor.household_label||`ID ${sponsor.household_id.slice(0,8)}`}</strong></div>
        <div><span>Sponsor membership ID</span><strong>{sponsor.membership_id.slice(0,8)}…</strong></div>
        <div><span>Validity</span><strong>{shortDate(sponsor.valid_from||'')} – {sponsor.valid_until?shortDate(sponsor.valid_until):'No end date supplied'}</strong></div>
      </div>
      <div className="mt-4"><Alert tone={state==='ELIGIBLE'?'info':'warning'}>
        {state==='ELIGIBLE'
          ?'Flask reports an eligible, active sponsor bound to the same household and flat. Independently inspect the submitted documents and confirm the claimed family relationship before approving.'
          :'Flask does not report an active eligible sponsor. Do not approve until eligibility is resolved.'}
      </Alert></div>
    </>:<Alert tone="warning">
      The current Flask application-detail response does not supply a verified sponsor identity, membership status, and same-household/flat binding. A name appearing on an occupancy letter cannot be assumed to belong to this applicant’s sponsor. Ask the backend to include the admin-only sponsor_context field before approving.
    </Alert>}
    <p className="small muted mt-3">An owner and tenant may have different households in the same flat. Sponsor identity and relationship must be checked against the exact household and sponsor membership ID.</p>
  </Card>;
}
