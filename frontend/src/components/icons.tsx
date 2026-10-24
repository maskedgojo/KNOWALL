import type {SVGProps} from 'react';
type Props=SVGProps<SVGSVGElement>&{name:string;size?:number};
const shapes:Record<string,React.ReactNode>={
  home:<><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M9 21v-8h6v8"/></>,
  building:<><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M9 7h1m4 0h1M9 11h1m4 0h1M9 15h1m4 0h1M10 21v-3h4v3"/></>,
  users:<><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></>,
  file:<><rect x="5" y="2" width="14" height="20" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/></>,
  shield:<><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><path d="m9 12 2 2 4-4"/></>,
  settings:<><circle cx="12" cy="12" r="3"/><path d="M12 2v2m0 16v2M4 12H2m20 0h-2M5 5l1.5 1.5M19 19l-1.5-1.5M19 5l-1.5 1.5M5 19l1.5-1.5"/></>,
  arrow:<><path d="M4 12h16m-6-6 6 6-6 6"/></>,
  back:<><path d="M20 12H4m6 6-6-6 6-6"/></>,
  check:<path d="m5 12 4 4L19 6"/>,
  alert:<><circle cx="12" cy="12" r="10"/><path d="M12 7v5m0 4h.01"/></>,
  clock:<><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></>,
  mail:<><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m2 6 10 7 10-7"/></>,
  lock:<><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></>,
  logoff:<><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/></>,
  upload:<><path d="M12 16V3m-5 5 5-5 5 5"/><path d="M4 16v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/></>,
  scan:<><path d="M3 9V5a2 2 0 0 1 2-2h4m6 0h4a2 2 0 0 1 2 2v4M3 15v4a2 2 0 0 0 2 2h4m6 0h4a2 2 0 0 0 2-2v-4M6 12h12"/></>,
  search:<><circle cx="11" cy="11" r="8"/><path d="m21 21-4.4-4.4"/></>,
  plus:<path d="M12 5v14M5 12h14"/>,
  refresh:<><path d="M20 11a8 8 0 0 0-14-5L3 9m0-6v6h6M4 13a8 8 0 0 0 14 5l3-3m0 6v-6h-6"/></>,
  menu:<path d="M4 6h16M4 12h16M4 18h16"/>,
  close:<path d="M5 5l14 14M19 5 5 19"/>,
  calendar:<><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/></>,
  eye:<><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12"/><circle cx="12" cy="12" r="3"/></>,
  clipboard:<><rect x="5" y="4" width="14" height="18" rx="2"/><rect x="9" y="2" width="6" height="4" rx="1"/></>,
};
export function Icon({name,size=19,...props}:Props){return <svg {...props} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shapes[name]??shapes.file}</svg>}
