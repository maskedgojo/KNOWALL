/** Based on backend/app/openapi.json v0.9.1. Backend authorization always wins. */
export type Category = 'OWNER' | 'TENANT' | 'FAMILY_MEMBER';
export type Relationship = 'SPOUSE' | 'CHILD' | 'PARENT' | 'SIBLING' | 'GRANDPARENT' | 'GRANDCHILD' | 'OTHER';
export type ApplicationStatus = 'DRAFT' | 'PENDING' | 'IN_REVIEW' | 'NEEDS_CORRECTION' | 'APPROVED' | 'REJECTED';
export type MembershipStatus = 'ACTIVE' | 'SUSPENDED' | 'EXPIRED' | 'REVOKED';
export interface User { id: string; display_name: string; email: string; phone: string | null; email_verified: boolean; account_status: 'ACTIVE' | 'SUSPENDED' | 'DISABLED'; date_of_birth: string | null; occupation: string | null; }
export interface Tower {id: string; name: string}
export interface Flat {id: string; tower_id: string; tower_name: string; flat_number: string; floor_number: number}
export interface Membership {id: string; household_id: string; household_label: string; flat: Flat; category: Category; status: MembershipStatus; access_state: string; valid_from: string; valid_until: string | null; sponsor_membership_id: string | null; relationship_to_sponsor: Relationship | null; is_current_occupant: boolean | null; occupancy_confirmed_at: string | null; declared_current_occupant?: boolean | null}
export interface Access {user_id: string; email_verified: boolean; roles: string[]; verified_resident: boolean; active_memberships: Membership[]; permissions: string[]}
export interface Application {id:string; flat: Flat; category: Category; status: ApplicationStatus; household_id: string | null; sponsor_membership_id: string | null; invitation_id: string | null; resulting_membership_id: string | null; applicant_notes: string | null; requested_valid_from: string | null; requested_valid_until: string | null; evidence_required: boolean; documents_uploaded: number; created_at: string; submitted_at: string | null; decided_at: string | null; relationship_to_sponsor: Relationship | null; declared_current_occupant: boolean | null;}
export interface CreateApplication {flat_id: string; category:'OWNER'|'TENANT'; applicant_notes?: string | null; requested_valid_from?:string|null; requested_valid_until?:string|null; declared_current_occupant?:boolean|null}
export interface FamilyMember {user_id:string; display_name:string; category:Category; membership_id:string; sponsor_membership_id:string|null; relationship_to_sponsor:Relationship|null; is_current_occupant:boolean|null}
export interface FamilyHousehold {household_id:string; household_label:string; flat:Flat; members:FamilyMember[]; relationships:{sponsor_membership_id:string;family_membership_id:string;relationship_to_sponsor:Relationship|null}[]}
export interface Household {id:string; label:string; flat:Flat; members:FamilyMember[]}
export interface ApiProblem {error:{code:string;message:string;fields?:Record<string,string>}}

/** New Family Auto-Activation API: the outcome, NOT invitation category, determines navigation. */
export type InvitationAcceptance =
  | {outcome:'FAMILY_MEMBERSHIP_ACTIVATED'; application:null; membership:Membership; access?:Access}
  | {outcome:'APPLICATION_DRAFT_CREATED'; application:Application; membership:null};

export interface AdminHouseholdMember {
  membership_id:string; display_name:string; category:Category; membership_status:MembershipStatus;
  access_state:string; relationship_to_sponsor:Relationship|null; sponsor_membership_id:string|null;
  sponsor_display_name:string|null; declared_current_occupant:boolean|null;
  is_current_occupant:boolean|null; valid_from:string;valid_until:string|null;
}
export interface AdminHousehold {
  household_id:string;household_label:string;flat:Flat;members:AdminHouseholdMember[];
}
export interface Pagination {total:number;limit:number;offset:number}
export type MemberEvidenceState='REQUESTED'|'SUBMITTED'|'ACCEPTED'|'REJECTED'|'CANCELLED';
export interface MemberEvidenceRequest {
  id:string;membership_id:string;reason:string;evidence_needed:string;status:MemberEvidenceState;
  created_at?:string;submitted_at?:string|null;resolved_at?:string|null;retention_deadline?:string|null;
  document?:Record<string,unknown>|null;review_note?:string|null;
}
