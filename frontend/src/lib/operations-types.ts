/** Module 3 society operations payloads. Mirrors backend/app/modules/operations. */
export type Page = {limit:number; offset:number};
export interface Facility {id:string; name:string; description:string; location:string; capacity:number; open_minute:number; close_minute:number; slot_minutes:number; max_minutes_per_booking:number; booking_window_days:number; requires_approval:boolean; is_active:boolean; max_upcoming_per_resident:number|null}
export interface Photo {id:string; caption:string; uploaded_by_staff:boolean; uploaded_by_display_name:string; created_at:string}
export interface Slot {starts_at:string; ends_at:string; available:boolean; reason:'PAST'|'OUTSIDE_BOOKING_WINDOW'|'BLOCKED'|'BOOKED'|null}
export interface Availability {facility:Facility; date:string; slots:Slot[]}
export type BookingStatus='PENDING'|'CONFIRMED'|'REJECTED'|'CANCELLED';
export interface BookingHistory {from_status:string|null; to_status:string; reason:string|null; created_at:string}
export interface Booking {id:string; facility_id:string; facility_name:string; starts_at:string; ends_at:string; purpose:string; status:BookingStatus; decision_reason:string|null; created_at:string; history:BookingHistory[]; resident_display_name?:string}
export type EventStatus='DRAFT'|'PUBLISHED'|'CANCELLED'|'CLOSED';
export type RsvpStatus='GOING'|'WAITLISTED'|'CANCELLED';
export interface SocietyEvent {id:string; title:string; description:string; venue:string; starts_at:string; ends_at:string; capacity:number; status:EventStatus; organizer_display_name:string; going_count:number; waitlist_count:number; my_rsvp:RsvpStatus|null; volunteer_slots:number; volunteer_count:number; i_volunteered:boolean; updates:{message:string; created_at:string}[]; locality_publish_requested?:boolean}
export interface Attendee {user_id:string; display_name:string; status:RsvpStatus; attended:boolean}
export interface Volunteer {user_id:string; display_name:string; note:string}
export type MaintenanceStatus='PLANNED'|'IN_PROGRESS'|'RESOLVED';
export interface MaintenanceItem {id:string; asset:string; title:string; description:string; scheduled_start:string; scheduled_end:string; status:MaintenanceStatus; created_at:string; updates:{message:string; status:string; created_at:string}[]}
export const TICKET_TYPES=['LIFT','PLUMBING','ELECTRICAL','COMMON_AREA','OTHER'] as const;
export type TicketType=typeof TICKET_TYPES[number];
export type TicketStatus='REPORTED'|'ASSIGNED'|'IN_PROGRESS'|'COMPLETED'|'CONFIRMED'|'REOPENED';
export interface TicketUpdate {kind:'STATUS'|'CLARIFICATION'|'FEEDBACK'; message:string; from_status:string|null; to_status:string|null; actor_display_name:string; created_at:string}
export interface MaintenanceTicket {id:string; flat:string; issue_type:TicketType; title:string; description:string; location_note:string; status:TicketStatus; assignee_label:string|null; created_at:string; updated_at:string; timeline:TicketUpdate[]; photos:Photo[]; reporter_display_name?:string}
export type ProjectStatus='PLANNED'|'IN_PROGRESS'|'COMPLETED';
export interface Milestone {id:string; title:string; due_date:string|null; status:ProjectStatus; percent:number; progress_note:string; updated_at:string; photos:Photo[]}
export interface Project {id:string; title:string; description:string; status:ProjectStatus; budget_note:string|null; expected_completion:string|null; progress_percent:number; milestones:Milestone[]; updated_at:string}
export interface OperationsDashboard {
  bookings:{id:string; facility_name:string; starts_at:string; ends_at:string; status:BookingStatus}[];
  events:{id:string; title:string; venue:string; starts_at:string}[];
  disruptions:{id:string; asset:string; title:string; status:MaintenanceStatus; scheduled_start:string; scheduled_end:string}[];
  projects:{id:string; title:string; status:ProjectStatus}[];
  my_open_requests:{id:string; title:string; status:TicketStatus}[];
}
/** Admin-driven ticket transitions; must match ADMIN_TRANSITIONS in maintenance.py. */
export const NEXT_TICKET_STATUS:Partial<Record<TicketStatus,TicketStatus[]>>={REPORTED:['ASSIGNED'],ASSIGNED:['IN_PROGRESS'],IN_PROGRESS:['COMPLETED'],REOPENED:['ASSIGNED','IN_PROGRESS']};
export function minuteLabel(minute:number){const pad=(n:number)=>String(n).padStart(2,'0');return `${pad(Math.floor(minute/60)%24)}:${pad(minute%60)}`;}
export function timeRange(start:string,end:string){const s=new Date(start),e=new Date(end);const day=s.toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'});const t=(d:Date)=>d.toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit'});return `${day} · ${t(s)}–${t(e)}`;}
export function isoFromLocal(value:string){const date=new Date(value);return Number.isNaN(date.getTime())?'':date.toISOString();}
