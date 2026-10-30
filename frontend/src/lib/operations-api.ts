import {api} from './api';
import type {Attendee,Availability,Booking,Facility,MaintenanceItem,MaintenanceTicket,OperationsDashboard,Page,Photo,Project,ProjectStatus,SocietyEvent,TicketStatus,TicketType,MaintenanceStatus,Volunteer} from './operations-types';
const pathId=(id:string)=>encodeURIComponent(id);
const paged=(limit=30,offset=0)=>`limit=${limit}&offset=${offset}`;
export type FacilityInput=Partial<Omit<Facility,'id'>>;
function photoForm(file:File,caption:string){const form=new FormData();form.append('file',file);if(caption)form.append('caption',caption);return form;}
/** Ticket photos: the reporter or a Society Admin may upload; Flask decides. */
export const uploadTicketPhoto=(id:string,file:File,caption='')=>api<{photos:Photo[]}>(`/api/maintenance/requests/${pathId(id)}/photos`,{method:'POST',body:photoForm(file,caption)});

export const operationsApi={
  dashboard:()=>api<OperationsDashboard>('/api/operations/dashboard'),
  facilities:()=>api<{facilities:Facility[]}>('/api/facilities'),
  availability:(id:string,date:string)=>api<Availability>(`/api/facilities/${pathId(id)}/availability?date=${encodeURIComponent(date)}`),
  book:(body:{facility_id:string; starts_at:string; ends_at:string; purpose:string})=>api<{booking:Booking}>('/api/bookings',{method:'POST',body}),
  myBookings:()=>api<{bookings:Booking[]; pagination:Page}>(`/api/bookings/me?${paged()}`),
  cancelBooking:(id:string,reason?:string)=>api<{booking:Booking}>(`/api/bookings/${pathId(id)}/cancel`,{method:'POST',body:reason?{reason}:{}}),
  events:()=>api<{events:SocietyEvent[]; pagination:Page}>(`/api/events?${paged()}`),
  event:(id:string)=>api<{event:SocietyEvent}>(`/api/events/${pathId(id)}`),
  rsvp:(id:string)=>api<{event:SocietyEvent}>(`/api/events/${pathId(id)}/rsvp`,{method:'POST',body:{}}),
  cancelRsvp:(id:string)=>api<{event:SocietyEvent}>(`/api/events/${pathId(id)}/rsvp`,{method:'DELETE',body:{}}),
  volunteer:(id:string,note='')=>api<{event:SocietyEvent}>(`/api/events/${pathId(id)}/volunteer`,{method:'POST',body:note?{note}:{}}),
  withdrawVolunteer:(id:string)=>api<{event:SocietyEvent}>(`/api/events/${pathId(id)}/volunteer`,{method:'DELETE',body:{}}),
  maintenance:()=>api<{items:MaintenanceItem[]; pagination:Page}>(`/api/maintenance?${paged()}`),
  report:(body:{issue_type:TicketType; title:string; description:string; location_note?:string})=>api<{request:MaintenanceTicket}>('/api/maintenance/requests',{method:'POST',body}),
  myTickets:()=>api<{requests:MaintenanceTicket[]; pagination:Page}>(`/api/maintenance/requests/me?${paged()}`),
  ticket:(id:string)=>api<{request:MaintenanceTicket}>(`/api/maintenance/requests/${pathId(id)}`),
  feedback:(id:string,action:'CLARIFY'|'CONFIRM'|'REOPEN',message?:string)=>api<{request:MaintenanceTicket}>(`/api/maintenance/requests/${pathId(id)}/feedback`,{method:'POST',body:message?{action,message}:{action}}),
  projects:()=>api<{projects:Project[]; pagination:Page}>(`/api/development?${paged()}`),
  project:(id:string)=>api<{project:Project}>(`/api/development/${pathId(id)}`),
};

export const operationsAdminApi={
  facilities:()=>api<{facilities:Facility[]}>('/api/admin/facilities'),
  createFacility:(body:FacilityInput)=>api<{facility:Facility}>('/api/admin/facilities',{method:'POST',body}),
  updateFacility:(id:string,body:FacilityInput)=>api<{facility:Facility}>(`/api/admin/facilities/${pathId(id)}`,{method:'PATCH',body}),
  blackout:(id:string,body:{starts_at:string; ends_at:string; reason:string})=>api<{cancelled_booking_ids:string[]}>(`/api/admin/facilities/${pathId(id)}/blackouts`,{method:'POST',body}),
  bookings:(status?:string)=>api<{bookings:Booking[]; pagination:Page}>(`/api/admin/bookings?${paged(100)}${status?`&status=${encodeURIComponent(status)}`:''}`),
  decide:(id:string,decision:'APPROVE'|'REJECT',reason?:string)=>api<{booking:Booking}>(`/api/bookings/${pathId(id)}/decision`,{method:'POST',body:reason?{decision,reason}:{decision}}),
  events:()=>api<{events:SocietyEvent[]; pagination:Page}>(`/api/admin/events?${paged()}`),
  createEvent:(body:{title:string; description:string; venue:string; starts_at:string; ends_at:string; capacity:number; volunteer_slots?:number; locality_publish_requested?:boolean})=>api<{event:SocietyEvent}>('/api/events',{method:'POST',body}),
  eventAction:(id:string,action:'publish'|'cancel'|'close')=>api<{event:SocietyEvent}>(`/api/events/${pathId(id)}/${action}`,{method:'POST',body:{}}),
  postEventUpdate:(id:string,message:string)=>api<{event:SocietyEvent}>(`/api/events/${pathId(id)}/updates`,{method:'POST',body:{message}}),
  attendees:(id:string)=>api<{attendees:Attendee[]; volunteers:Volunteer[]}>(`/api/admin/events/${pathId(id)}/attendees`),
  attendance:(id:string,user_id:string,attended:boolean)=>api<{attended:boolean}>(`/api/events/${pathId(id)}/attendance`,{method:'POST',body:{user_id,attended}}),
  maintenance:()=>api<{items:MaintenanceItem[]; pagination:Page}>(`/api/admin/maintenance?${paged()}`),
  schedule:(body:{asset:string; title:string; description:string; scheduled_start:string; scheduled_end:string})=>api<{item:MaintenanceItem}>('/api/maintenance',{method:'POST',body}),
  updateItem:(id:string,message:string,status?:MaintenanceStatus)=>api<{item:MaintenanceItem}>(`/api/maintenance/${pathId(id)}/updates`,{method:'POST',body:status?{message,status}:{message}}),
  tickets:(status?:string)=>api<{requests:MaintenanceTicket[]; pagination:Page}>(`/api/admin/maintenance/requests?${paged(100)}${status?`&status=${encodeURIComponent(status)}`:''}`),
  moveTicket:(id:string,body:{status:TicketStatus; message:string; assignee_label?:string})=>api<{request:MaintenanceTicket}>(`/api/maintenance/requests/${pathId(id)}/status`,{method:'PATCH',body}),
  projects:()=>api<{projects:Project[]; pagination:Page}>(`/api/admin/development?${paged()}`),
  createProject:(body:{title:string; description:string; budget_note?:string; expected_completion?:string})=>api<{project:Project}>('/api/development',{method:'POST',body}),
  updateProject:(id:string,body:{status?:ProjectStatus; budget_note?:string; expected_completion?:string})=>api<{project:Project}>(`/api/development/${pathId(id)}`,{method:'PATCH',body}),
  addMilestone:(id:string,body:{title:string; due_date?:string})=>api<{project:Project}>(`/api/development/${pathId(id)}/milestones`,{method:'POST',body}),
  updateMilestone:(id:string,milestoneId:string,body:{status?:ProjectStatus; percent?:number; progress_note?:string})=>api<{project:Project}>(`/api/development/${pathId(id)}/milestones/${pathId(milestoneId)}`,{method:'PATCH',body}),
  milestonePhoto:(id:string,milestoneId:string,file:File,caption='')=>api<{photos:Photo[]}>(`/api/development/${pathId(id)}/milestones/${pathId(milestoneId)}/photos`,{method:'POST',body:photoForm(file,caption)}),
};
