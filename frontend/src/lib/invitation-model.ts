/** Parse only optional fields actually supplied by the Flask invitation listing. */
import type {Category,Relationship} from './types';
export type InvitationSummary={id:string;category:Category;email:string;status:string;expires_at:string;flat_id:string|null;household_id:string|null;sponsor_membership_id:string|null;relationship_to_sponsor:Relationship|null;flat_label:string|null;household_label:string|null;sponsor_name:string|null};
const cats:Category[]=['OWNER','TENANT','FAMILY_MEMBER'];
const rels:Relationship[]=['SPOUSE','CHILD','PARENT','SIBLING','GRANDPARENT','GRANDCHILD','OTHER'];
const string=(v:unknown)=>typeof v==='string'?v:'';
const rec=(v:unknown):Record<string,unknown>=>v&&typeof v==='object'&&!Array.isArray(v)?v as Record<string,unknown>:{};
export function parseInvitations(payload:unknown):InvitationSummary[] {
  const list=rec(payload).invitations;
  if(!Array.isArray(list)) return [];
  return list.flatMap((value:unknown)=>{
    const v=rec(value),cat=v.category;
    if(!cats.includes(cat as Category) || !string(v.id)) return [];
    const flat=rec(v.flat),household=rec(v.household),sponsor=rec(v.sponsor);
    const rel=v.relationship_to_sponsor;
    return [{
      id:string(v.id),category:cat as Category,email:string(v.email),status:string(v.status).toUpperCase(),expires_at:string(v.expires_at),
      flat_id:string(v.flat_id)||string(flat.id)||null,household_id:string(v.household_id)||string(household.id)||null,
      sponsor_membership_id:string(v.sponsor_membership_id)||null,
      relationship_to_sponsor:rels.includes(rel as Relationship)?rel as Relationship:null,
      flat_label:string(flat.flat_number)||null,household_label:string(v.household_label)||string(household.label)||null,
      sponsor_name:string(v.sponsor_name)||string(sponsor.display_name)||null
    }];
  });
}
export function invitationState(inv:InvitationSummary,now=Date.now()): 'ACTIVE'|'USED'|'EXPIRED'|'REVOKED'|'OTHER' {
  if (inv.status==='USED' || inv.status==='ACCEPTED') return 'USED';
  if (inv.status==='EXPIRED')return 'EXPIRED';
  if (inv.status==='REVOKED')return 'REVOKED';
  if(inv.expires_at && Number.isFinite(Date.parse(inv.expires_at))&&Date.parse(inv.expires_at)<=now)return 'EXPIRED';
  return inv.status==='ACTIVE'?'ACTIVE':'OTHER';
}
export function acceptancePayload(token:string,category:Category,relationship:Relationship|null,occupancy:'unknown'|'yes'|'no') {
  return {token,declared_current_occupant:occupancy==='unknown'?null:occupancy==='yes',
    ...(category==='FAMILY_MEMBER'?{relationship_to_sponsor:relationship}:{}),
  };
}
