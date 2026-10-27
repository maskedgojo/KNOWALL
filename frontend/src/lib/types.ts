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
export type NoticeStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED';
export interface Notice {id:string; society_id:number; title:string; body:string; status:NoticeStatus; expires_at:string|null; published_at:string|null; archived_at:string|null; replaces_notice_id:string|null; created_by_user_id:string; published_by_user_id:string|null; archived_by_user_id:string|null; created_at:string; updated_at:string; visible_to_residents:boolean}
export interface NoticePage {notices:Notice[]; pagination:{limit:number; offset:number}}
export interface Discussion {id:string; society_id:number; title:string; body:string; created_by_user_id:string; author_display_name:string; created_at:string; updated_at:string; comment_count:number}
export interface DiscussionComment {id:string; discussion_id:string; parent_comment_id:string|null; body:string; created_by_user_id:string; author_display_name:string; created_at:string}
export interface DiscussionPage {discussions:Discussion[]; pagination:{limit:number; offset:number}}
export type SuggestionCategory = 'MAINTENANCE' | 'SAFETY' | 'AMENITIES' | 'COMMUNITY' | 'OTHER';
export interface Suggestion {id:string; society_id:number; title:string; description:string; category:SuggestionCategory; status:'SUBMITTED'; created_by_user_id:string; author_display_name:string; created_at:string; updated_at:string}
export interface SuggestionPage {suggestions:Suggestion[]; pagination:{limit:number; offset:number}}
export interface GovernanceEvent {id:string; occurred_at:string; event_type:string; summary:string; resource_path:string|null}
export interface GovernanceHistory {events:GovernanceEvent[]; pagination:{limit:number; offset:number}}
export interface PollOption {id:string; label:string; position:number; vote_count:number|null}
export interface Poll {id:string; society_id:number; question:string; binding:false; status:'SCHEDULED'|'OPEN'|'CLOSED'; opens_at:string; closes_at:string; created_by_user_id:string; author_display_name:string; created_at:string; my_option_id:string|null; options:PollOption[]}
export interface PollPage {polls:Poll[]; pagination:{limit:number; offset:number}}
export interface Dispute {id:string; society_id:number; title:string; description:string; status:'SUBMITTED'; created_at:string; updated_at:string}
export interface DisputePage {disputes:Dispute[]; pagination:{limit:number; offset:number}}
export interface Proposal {id:string; society_id:number; title:string; summary:string; status:'SUBMITTED'; voting_open:false; created_by_user_id:string; author_display_name:string; created_at:string; updated_at:string}
export interface ProposalPage {proposals:Proposal[]; pagination:{limit:number; offset:number}}
export interface AdminDiscussion {id:string; title:string; body:string; author_display_name:string; created_at:string; updated_at:string; comment_count:number}
export interface AdminDiscussionComment {id:string; discussion_id:string; parent_comment_id:string|null; body:string; author_display_name:string; created_at:string}
export interface AdminSuggestion {id:string; title:string; description:string; category:SuggestionCategory; status:'SUBMITTED'; author_display_name:string; created_at:string; updated_at:string}
export interface AdminPollOption {id:string; label:string; position:number; vote_count:number|null}
export interface AdminPoll {id:string; question:string; binding:false; status:'SCHEDULED'|'OPEN'|'CLOSED'; opens_at:string; closes_at:string; author_display_name:string; options:AdminPollOption[]}
export interface AdminProposal {id:string; title:string; summary:string; status:'SUBMITTED'; voting_open:false; author_display_name:string; created_at:string; updated_at:string}

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
