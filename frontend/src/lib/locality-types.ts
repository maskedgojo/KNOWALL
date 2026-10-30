/** Module 4 locality payloads. Mirrors backend/app/modules/locality. */
export type Page = {limit:number; offset:number};
export interface Category {key:string; label:string; description:string; is_emergency:boolean; place_count?:number}
export interface Locality {id:number; society_id:number; name:string; description:string; is_fictional:boolean; coverage:{type:'RADIUS'; center:{latitude:number; longitude:number}; radius_m:number}; stale_after_days:number; categories:Category[]; updated_at:string|null}
export type VerificationState='VERIFIED'|'STALE'|'UNVERIFIED'|'NEEDS_RECHECK'|'ARCHIVED';
export const STAFF_METHODS=['PHONE_CALL','SITE_VISIT','OFFICIAL_SOURCE','DOCUMENT'] as const;
export type VerificationMethod=typeof STAFF_METHODS[number]|'CORRECTION_REVIEW'|'DEMO_SEED';
export interface Place {id:string; name:string; category:Category; description:string|null; address:string|null; latitude:number|null; longitude:number|null; phone:string|null; website_url:string|null; source_label:string; source_url:string|null; data_origin:'FICTIONAL_DEMO'|'REAL_WORLD'; publication_status:'ACTIVE'|'ARCHIVED'; verification_state:VerificationState; is_stale:boolean; last_verified_at:string|null; last_verification_method:VerificationMethod|null; updated_at:string|null; version:number;
  archived_reason?:string|null; last_verified_by_display_name?:string|null; created_at?:string; open_corrections?:number}
export interface HistoryEntry {id:string; action:string; changes:Record<string,unknown>|null; reason:string|null; created_at:string; actor_display_name?:string|null}
export interface PlaceDetail {place:Place; open_corrections:number; my_corrections:{id:string; issue_type:CorrectionIssue; status:CorrectionStatus; submitted_at:string|null}[]; history:HistoryEntry[]}
export interface StaffPlaceDetail {place:Place; history:HistoryEntry[];
  verifications:{id:string; method:VerificationMethod; scope:string; source_url:string|null; note:string|null; verified_at:string|null; verifier_display_name:string|null}[];
  corrections:{id:string; issue_type:CorrectionIssue; field:string|null; status:CorrectionStatus; proposed_value:string|null; reporter_display_name:string|null; submitted_at:string|null}[]}

export const ISSUES=['WRONG_PHONE','WRONG_ADDRESS','WRONG_COORDINATES','WRONG_NAME','WRONG_CATEGORY','WRONG_WEBSITE','MOVED_OR_CLOSED','DUPLICATE','OTHER'] as const;
export type CorrectionIssue=typeof ISSUES[number]|'MISSING_SERVICE';
export type CorrectionStatus='PENDING'|'CLARIFICATION_REQUESTED'|'APPROVED'|'REJECTED';
export const ISSUE_LABEL:Record<CorrectionIssue,string>={WRONG_PHONE:'Phone number is wrong',WRONG_ADDRESS:'Address is wrong',WRONG_COORDINATES:'Map location is wrong',WRONG_NAME:'Name is wrong',WRONG_CATEGORY:'Category is wrong',WRONG_WEBSITE:'Website is wrong',MOVED_OR_CLOSED:'Moved or permanently closed',DUPLICATE:'Duplicate listing',MISSING_SERVICE:'Missing service',OTHER:'Something else'};
export interface Correction {id:string; place:{id:string; name:string; publication_status:string}|null; issue_type:CorrectionIssue; field:string|null; current_value:string|null; proposed_value:string|null; reason:string; source_url:string|null; status:CorrectionStatus; decision_reason:string|null; reviewed_at:string|null; submitted_at:string; updated_at?:string; history?:HistoryEntry[]}
export interface StaffCorrection extends Correction {reporter_display_name:string; reviewer_display_name:string|null; published_value:string|null; published_changed_since_submission:boolean; competing_open_corrections?:number;
  related_corrections?:{id:string; status:CorrectionStatus; proposed_value:string|null; reporter_display_name:string; submitted_at:string}[];
  place_detail?:{id:string; name:string; category:string|null; address:string|null; phone:string|null; website_url:string|null; source_label:string; data_origin:string; version:number}}
export interface CorrectionInput {issue_type:CorrectionIssue; reason:string; proposed_value?:string; proposed_latitude?:number; proposed_longitude?:number; proposed_category?:string; source_url?:string}
export type Decision='APPROVE'|'REJECT'|'REQUEST_CLARIFICATION';

export const EVENT_CATEGORIES=['CULTURAL','HEALTH','CIVIC','SPORTS','MARKET','OTHER'] as const;
export type EventCategory=typeof EVENT_CATEGORIES[number];
export type LocalEventStatus='PENDING'|'PUBLISHED'|'REJECTED'|'ARCHIVED';
export interface LocalEvent {id:string; title:string; description:string; organizer:string; venue:string; category:EventCategory; starts_at:string; ends_at:string; timing:'UPCOMING'|'ONGOING'|'COMPLETED'; shared_by_society:boolean; published_at:string|null;
  status?:LocalEventStatus; decision_reason?:string|null; created_at?:string; submitted_by_display_name?:string; reviewer_display_name?:string|null; history?:HistoryEntry[]}
export interface EventInput {title:string; description:string; organizer:string; venue:string; category:EventCategory; starts_at:string; ends_at:string}
export interface ShareableEvent {id:string; title:string; venue:string; starts_at:string; ends_at:string}

export const SEVERITIES=['INFO','LOW','MEDIUM','HIGH'] as const;
export type Severity=typeof SEVERITIES[number];
export const SOURCE_TYPES=['OFFICIAL_NOTICE','SOCIETY','COMMUNITY'] as const;
export type SourceType=typeof SOURCE_TYPES[number];
export interface LocalAlert {id:string; title:string; description:string; severity:Severity; source_type:SourceType; source_label:string; source_url:string|null; starts_at:string; expires_at:string; published_at:string|null; archived_at:string|null; state:'ACTIVE'|'SCHEDULED'|'EXPIRED'|'ARCHIVED'|'DRAFT';
  status?:'DRAFT'|'PUBLISHED'|'ARCHIVED'; created_at?:string; created_by_display_name?:string; reviewer_display_name?:string|null; history?:HistoryEntry[]}
export interface AlertInput {title:string; description:string; severity:Severity; source_type:SourceType; source_label:string; source_url?:string; starts_at:string; expires_at:string}

export interface FeedItem {kind:'ALERT'|'EVENT'|'DIRECTORY_UPDATE'; id:string; title:string; summary:string; occurred_at:string|null; link:string; reportable:boolean; severity?:Severity; source_label?:string; expires_at?:string; starts_at?:string; timing?:string}
export interface Report {id:string; target_type:'EVENT'|'ALERT'; target_id:string; target_title:string|null; target_status:string|null; reason:string; status:'OPEN'|'DISMISSED'|'ACTIONED'; review_note:string|null; reporter_display_name:string; reviewer_display_name:string|null; created_at:string; reviewed_at:string|null}
export interface Summary {places_active:number; places_unverified:number; places_needing_recheck:number; corrections_pending:number; corrections_awaiting_reporter:number; events_pending:number; alerts_draft:number; alerts_active:number; reports_open:number}
export type PlaceInput={name?:string; category?:string; description?:string|null; address?:string|null; latitude?:number|null; longitude?:number|null; phone?:string|null; website_url?:string|null; source_label?:string; source_url?:string|null; data_origin?:'FICTIONAL_DEMO'|'REAL_WORLD'};

export const STATE_LABEL:Record<VerificationState,string>={VERIFIED:'Verified',STALE:'Needs re-verification',UNVERIFIED:'Not yet verified',NEEDS_RECHECK:'Flagged for recheck',ARCHIVED:'Archived'};
/** Only http(s) links are ever rendered as clickable. */
export const safeHref=(value:string|null|undefined)=>value&&/^https?:\/\//i.test(value)?value:null;
