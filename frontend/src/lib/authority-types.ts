/** Module 6 authority case payloads. Mirrors backend/app/modules/authority. */
export const CASE_STATUSES=['ROUTED','ACKNOWLEDGED','CLARIFICATION_REQUESTED','IN_PROGRESS','RESOLVED','REOPENED','CLOSED'] as const;
export type CaseStatus=typeof CASE_STATUSES[number];
export type Verdict='CONFIRMED'|'DISPUTED';
export type EvidenceType='PROGRESS'|'RESOLUTION';
export type ClosureBasis='COMMUNITY_VERIFIED'|'WINDOW_MAJORITY'|'COORDINATOR_AFTER_WINDOW';

/** Statuses in which the department works on the case (progress, photos, clarification). Mirrors WORKABLE. */
export const WORKABLE:CaseStatus[]=['ACKNOWLEDGED','IN_PROGRESS','REOPENED'];
/** Statuses in which a case may still be reassigned. Mirrors TRANSFERABLE. */
export const TRANSFERABLE:CaseStatus[]=['ROUTED','ACKNOWLEDGED'];
export const OPEN_STATUSES:CaseStatus[]=['ROUTED','ACKNOWLEDGED','CLARIFICATION_REQUESTED','IN_PROGRESS','REOPENED'];

export const SIMULATION_LABEL='Simulated authority workflow for demonstration. These departments and officials are not real government bodies, and nothing is sent to any government system.';

export interface DepartmentRef {id:number; name:string; is_demo:boolean}
export interface Department extends DepartmentRef {code:string; description:string; contact_label:string; requires_resolution_proof:boolean; escalation_department_id:number|null; is_active:boolean; label:string;
  jurisdiction?:{id:number; locality_id:number; category:string; priority:number}[]; escalation_rule?:{threshold_hours:number; target_label:string}|null;
  officers?:{id:string; user_id:string; title:string; display_name:string}[]}

/** The shared status Module 5 shows on the civic issue (`authoritative_status`). */
export interface CasePublicStatus {authority_case_id:string; case_id:string; status:CaseStatus; status_label:string; department:DepartmentRef|null; is_overdue:boolean; due_at:string; round:number; reopen_count:number;
  resolved_at:string|null; verification_closes_at:string|null; closed_at:string|null; closure_basis:ClosureBasis|null; updated_at:string; simulated:true}
export interface ResolutionEvidence {id:string; round:number; evidence_type:EvidenceType; caption:string; mime_type:string; created_at:string}
export interface Tally {round:number; confirmed:number; disputed:number; close_threshold:number; reopen_threshold:number}

export interface CaseTracker extends CasePublicStatus {
  civic_issue_id:string;
  timeline:{sequence:number; action:string; to_status:string; status_label:string; summary:string; at:string}[];
  evidence:ResolutionEvidence[];
  verification:Tally&{open:boolean; viewer_is_affected:boolean; viewer_can_verify:boolean; viewer_verdict:Verdict|null};
  open_clarification:{id:string; question:string; asked_at:string}|null;
  simulation_notice:string;
}

export interface CaseEvent {sequence:number; action:string; from_status:string|null; to_status:string; public_summary:string; actor_kind:string; at:string; reason?:string; actor_display_name?:string; department_id?:number|null; details?:Record<string,unknown>|null}
export interface CaseSummary extends Omit<CasePublicStatus,'department'> {civic_issue_id:string; department:Department; owner_user_id:string|null; owner_display_name:string; title:string; category:string; severity:string; community_support:number; created_at:string}
export interface CaseDetail extends CaseSummary {
  issue:{summary:string; location:{locality_id?:number; latitude?:number; longitude?:number; address_hint?:string}; evidence:{evidence_id:string; mime_type:string; caption:string; visibility:string}[]; priority:unknown; merged_duplicate_issue_ids:string[]; validated_at:string|null};
  events:CaseEvent[];
  transfers:{from_department_id:number; to_department_id:number; reason:string; at:string}[];
  escalations:{id:string; kind:'AUTO_OVERDUE'|'MANUAL'; target_label:string; reason:string; due_at_snapshot:string; triggered_at:string; outcome:'OPEN'|'RESPONDED'|'CLOSED'; outcome_at:string|null}[];
  evidence:ResolutionEvidence[];
  verifications:{id:string; round:number; verdict:Verdict; reason:string; has_photo:boolean; resident_display_name:string; at:string}[];
  clarifications:{id:string; question:string; status:'OPEN'|'ANSWERED'; response:string|null; asked_at:string; responded_at:string|null}[];
  tally:Tally;
}
export interface CaseList {cases:CaseSummary[]; total:number; limit:number; offset:number; simulation_notice:string}
export interface IntakeItem {canonical_issue_id:string; routed_at:string; title:string; category:string; severity:string; community_support:number; suggested_department:{id:number; name:string}|null}
export interface AuthorityMe {officer:{id:string; title:string; department:Department}|null; is_coordinator:boolean; simulation_notice:string}
export interface CaseNotification {id:string; case_id:string; event_type:string; message:string; created_at:string; read_at:string|null}

interface Durations {count:number; average_hours:number|null; median_hours:number|null; max_hours:number|null}
export interface CivicAnalytics {
  generated_at:string; simulation_notice:string;
  totals:{cases:number; open:number; overdue:number; pending_intake:number; transfers:number; reopens:number; reopened_cases:number};
  by_status:Record<CaseStatus,number>;
  by_department:{department_id:number; name:string; total:number; open:number; resolved:number; closed:number; overdue:number}[];
  durations:{intake_to_acknowledge:Durations; intake_to_first_resolution:Durations; intake_to_close:Durations};
  escalations:{total:number; auto_overdue:number; manual:number; open:number; responded:number};
  outcomes:{closed_by_basis:Record<ClosureBasis,number>; verifications:{confirmed:number; disputed:number}};
  reconciliation:{cases_checked:number; consistent:boolean; status_sum_matches_total:boolean; mismatches:{case_id:string; reference:string; problems:string[]}[]};
  last_snapshot:{trigger:string; at:string; counts:Record<string,unknown>}|null;
  audit:{case_id:string; reference:string; sequence:number; action:string; from_status:string|null; to_status:string; actor_kind:string; actor_display_name:string; reason:string; at:string}[];
}
