/** Module 5 civic issue payloads. Mirrors backend/app/modules/civic. */
export const CIVIC_CATEGORIES=['ROAD_DAMAGE','STREETLIGHT','GARBAGE','DRAINAGE','WATER_SUPPLY','FOOTPATH','TRAFFIC','PUBLIC_SPACE','OTHER'] as const;
export type CivicCategory=typeof CIVIC_CATEGORIES[number];
export const CIVIC_SEVERITIES=['LOW','MEDIUM','HIGH','CRITICAL'] as const;
export type CivicSeverity=typeof CIVIC_SEVERITIES[number];
export type CivicPrivacy='ANONYMOUS'|'PUBLIC_NAME';
export type CivicState='DRAFT'|'SUBMITTED'|'UNDER_REVIEW'|'NEEDS_INFO'|'VALIDATED'|'READY_FOR_ROUTING'|'REJECTED'|'MERGED'|'WITHDRAWN';
export type EvidenceVisibility='PRIVATE'|'RESIDENTS';
export type ConcernType='ABUSIVE'|'SENSITIVE_IMAGE'|'PERSONAL_INFO'|'FALSE_INFO'|'OFF_TOPIC'|'OTHER';
export const CONCERN_TYPES:ConcernType[]=['ABUSIVE','SENSITIVE_IMAGE','PERSONAL_INFO','FALSE_INFO','OFF_TOPIC','OTHER'];
export type ReportDisposition='DISMISSED'|'REDACTED'|'CORRECTION_REQUESTED'|'REMOVED';

export interface CivicLocality {id:number; name:string; center_lat:number; center_lon:number; radius_m:number; required_supporters:number; max_evidence_per_issue:number}
export interface CivicEvidence {id:string; caption:string; visibility:EvidenceVisibility; mime_type:string; created_at:string}
export interface CivicPriority {score:number; band:'LOW'|'MEDIUM'|'HIGH'; inputs:{supporters:number; supporter_points:number; days_open:number; age_points:number; severity:CivicSeverity; severity_points:number}; formula:string; disclaimer:string}
export interface CivicHandoff {routing_status:'PENDING_INTAKE'|'ACKNOWLEDGED'; routed_at:string; authority_case_id:string|null; acknowledged_at:string|null}
export interface CivicIssue {
  id:string; locality_id:number; title:string; description:string; category:CivicCategory; severity:CivicSeverity; state:CivicState;
  latitude:number; longitude:number; address_hint:string; privacy:CivicPrivacy|null; reporter_display_name:string; viewer_is_reporter:boolean;
  support_count:number; viewer_has_supported:boolean; evidence_count:number; evidence:CivicEvidence[]; priority:CivicPriority;
  canonical_issue_id:string|null; handoff:CivicHandoff|null; created_at:string; submitted_at:string|null; validated_at:string|null; updated_at:string;
  reporter_user_id?:string; authoritative_status?:Record<string,unknown>|null; readiness?:{unmet:string[]; required_supporters:number};
}
export interface SimilarMatch {distance_m:number; title_similarity:number; match_score:number}
export type SimilarIssue=CivicIssue&{match:SimilarMatch};
export interface TimelineEvent {type:'STATE_CHANGE'|'ROUTED'|'AUTHORITY_ACKNOWLEDGED'; from_state?:string|null; to_state?:string; actor_role?:string; reason?:string; routing_status?:string; authority_case_id?:string; at:string}
export interface CivicTimeline {issue_id:string; state:CivicState; events:TimelineEvent[]; support_count:number; priority:CivicPriority; authoritative_status:Record<string,unknown>|null}
export interface CivicList {issues:CivicIssue[]; total:number; limit:number; offset:number}
export interface CivicReport {id:string; issue_id:string; concern_type:ConcernType; concern:string; status:'OPEN'|'RESOLVED'; disposition:ReportDisposition|null; resolution_note:string; created_at:string; resolved_at:string|null}
export interface CivicHandoffRecord {id:string; canonical_issue_id:string; routing_status:string; routed_at:string; authority_case_id:string|null; acknowledged_at:string|null; payload:Record<string,unknown>}

/** States in which other residents may support an issue. Mirrors SUPPORTABLE_STATES in the backend. */
export const SUPPORTABLE:CivicState[]=['VALIDATED','READY_FOR_ROUTING'];
export const REPORTER_EDITABLE:CivicState[]=['DRAFT','NEEDS_INFO'];
export const REPORTER_WITHDRAWABLE:CivicState[]=['DRAFT','SUBMITTED','NEEDS_INFO'];
export const EVIDENCE_EDITABLE:CivicState[]=['DRAFT','SUBMITTED','NEEDS_INFO','UNDER_REVIEW','VALIDATED'];
export const QUEUE_STATES:CivicState[]=['SUBMITTED','UNDER_REVIEW','NEEDS_INFO','VALIDATED'];
