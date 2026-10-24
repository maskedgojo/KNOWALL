/* eslint-disable @typescript-eslint/no-require-imports */
const {test,after}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const ts=require('typescript');
const root=path.resolve(__dirname,'..');
function load(rel){
 const source=fs.readFileSync(path.join(root,rel),'utf8');
 const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const mod={exports:{}};new Function('module','exports','require',compiled)(mod,mod.exports,require);return mod.exports;
}
const model=load('src/lib/invitation-model.ts');
const handoff=load('src/lib/invitation-handoff.ts');
const origWindow=global.window,origSession=global.sessionStorage,origDateNow=Date.now;
const memory=new Map();let url=new URL('http://localhost:3000/invitations/accept?token=secret-token&invitation_id=id-1');
global.sessionStorage={getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)};
global.window={location:{get href(){return url.href;}},history:{state:null,replaceState:(_s,_title,value)=>{url=new URL(value,url);}}};
after(()=>{global.window=origWindow;global.sessionStorage=origSession;Date.now=origDateNow;});
test('new email link captures token and removes it from browser URL',()=>{
 const t=handoff.captureInvitationLink();assert.deepEqual(t,{token:'secret-token',invitationId:'id-1'});assert.equal(url.pathname,'/invitations/accept');assert.equal(url.search,'');assert.equal(handoff.hasPendingInvitation(),true);
});
test('refresh of acceptance URL retains token only in this tab until cleared',()=>{
 const t=handoff.captureInvitationLink();assert.equal(t.token,'secret-token');handoff.clearPendingInvitation();assert.equal(handoff.pendingInvitation(),null);
});
test('legacy email link /invitations?token is also captured',()=>{
 url=new URL('http://localhost:3000/invitations?token=old-link');const t=handoff.captureInvitationLink();assert.equal(t.token,'old-link');assert.equal(url.search,'');handoff.clearPendingInvitation();
});
test('pending handoff expires after one day',()=>{
 let time=1000000000;Date.now=()=>time;handoff.rememberInvitation('secret');time+=24*3600*1000+1;assert.equal(handoff.pendingInvitation(),null);Date.now=origDateNow;
});
const raw={invitations:[{id:'one',category:'OWNER',status:'ACTIVE',email:'invitee@example.com',flat_id:'flat-1',expires_at:'2099-01-01T00:00:00Z'},{id:'fam',category:'FAMILY_MEMBER',status:'ACTIVE',email:'invitee@example.com',sponsor_membership_id:'sponsor-1',relationship_to_sponsor:'CHILD'}]};
test('real invitation parser respects backend supplied category and sponsor fields',()=>{
 const list=model.parseInvitations(raw);assert.equal(list.length,2);assert.equal(list[0].category,'OWNER');assert.equal(list[0].sponsor_name,null);assert.equal(list[1].relationship_to_sponsor,'CHILD');
});
test('owner and tenant payload never send relationship_to_sponsor',()=>{
 for(const category of ['OWNER','TENANT']){const value=model.acceptancePayload('token',category,'SPOUSE','yes');assert.deepEqual(value,{token:'token',declared_current_occupant:true});assert.equal('relationship_to_sponsor' in value,false);}
});
test('family payload sends relationship and nullable occupancy',()=>{
 assert.deepEqual(model.acceptancePayload('token','FAMILY_MEMBER','CHILD','unknown'),{token:'token',declared_current_occupant:null,relationship_to_sponsor:'CHILD'});
});
test('expired and used invitations cannot be treated as active',()=>{
 const base=model.parseInvitations(raw)[0];assert.equal(model.invitationState({...base,expires_at:'2000-01-01T00:00:00Z'}),'EXPIRED');assert.equal(model.invitationState({...base,status:'USED'}),'USED');assert.equal(model.invitationState({...base,status:'REVOKED'}),'REVOKED');
});
test('expected Next App Router route exists and Flask contract uses POST',()=>{
 assert.equal(fs.existsSync(path.join(root,'src/app/invitations/accept/page.tsx')),true);
 const openapi=JSON.parse(fs.readFileSync(path.join(root,'contracts/openapi.json'),'utf8'));
 assert.ok(openapi.paths['/api/invitations/accept'].post);
 assert.ok(openapi.paths['/api/invitations/me'].get);
});
test('existing Next rewrites remain intact; referral token leakage header added',()=>{
 const config=fs.readFileSync(path.join(root,'next.config.ts'),'utf8');
 assert.match(config,/source: "\/api\/:path\*"/);assert.match(config,/127\.0\.0\.1:5000\/api/);assert.match(config,/Referrer-Policy/);
});
