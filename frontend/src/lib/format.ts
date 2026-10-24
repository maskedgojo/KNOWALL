export const pretty=(value:string|null|undefined)=>value?value.replace(/_/g,' ').toLowerCase().replace(/\b\w/g,c=>c.toUpperCase()):'Not provided';
export function occupancy(value:boolean|null|undefined){return value===true?'Confirmed occupant':value===false?'Confirmed non-occupant':'Not verified / Unknown';}
export function shortDate(value:string|null|undefined){if(!value)return '—'; const date=new Date(value);return Number.isNaN(date.getTime())?value:date.toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'});}
export function secureNext(value:string|null, fallback='/dashboard'){return value?.startsWith('/')&&!value.startsWith('//')&&!value.startsWith('/\\')&&!value.startsWith('/api/')?value:fallback;}
