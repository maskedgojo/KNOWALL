/* eslint-disable @typescript-eslint/no-require-imports -- CommonJS Node built-in test runner */
const {test,beforeEach,afterEach}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
// Transpile only the platform-independent API client; avoids requiring Next native binaries.
const text=fs.readFileSync(path.join(__dirname,'../src/lib/api.ts'),'utf8');
const compiled=ts.transpileModule(text,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const apiModule={exports:{}};new Function('module','exports','require',compiled)(apiModule,apiModule.exports,require);
const {api,clearCsrf,ApiError}=apiModule.exports;
let calls=[];let queue=[];const originalFetch=global.fetch;
function reply(data,status=200){return new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json'}})}
beforeEach(()=>{clearCsrf();calls=[];queue=[];global.fetch=async (url,init={})=>{calls.push({url,init});const v=queue.shift();if(!v)throw Error('No queued response');return v;}});
afterEach(()=>{global.fetch=originalFetch;clearCsrf()});
test('first mutation obtains guest CSRF and sends same-origin cookie credentials',async()=>{
 queue=[reply({csrf_token:'guest-value'}),reply({message:'ok'})];
 await api('/api/auth/register',{method:'POST',body:{display_name:'Test Person',email:'test@example.com',password:'secret123'}});
 assert.deepEqual(calls.map(c=>c.url),['/api/auth/csrf','/api/auth/register']);
 assert.equal(calls[1].init.credentials,'same-origin');
 assert.equal(calls[1].init.headers.get('X-CSRF-Token'),'guest-value');
 assert.equal(calls[1].init.headers.get('Content-Type'),'application/json');
});
test('Flask login rotates CSRF for next mutation',async()=>{
 queue=[reply({csrf_token:'guest'}),reply({user:{id:'x'},csrf_token:'rotated'}),reply({message:'ok'})];
 await api('/api/auth/login',{method:'POST',body:{email:'x@x.com',password:'pwd'}});
 await api('/api/me/profile',{method:'PATCH',body:{display_name:'Name'}});
 assert.equal(calls[1].init.headers.get('X-CSRF-Token'),'guest');
 assert.equal(calls[2].init.headers.get('X-CSRF-Token'),'rotated');
});
test('GET calls do not send CSRF or JSON content-type',async()=>{
 queue=[reply({towers:[]})];await api('/api/residential/towers');
 assert.equal(calls.length,1);assert.equal(calls[0].init.headers.has('X-CSRF-Token'),false);
 assert.equal(calls[0].init.headers.has('Content-Type'),false);
});
test('multipart upload does not set Content-Type boundary manually',async()=>{
 const f=new FormData();f.set('application_id','x');queue=[reply({csrf_token:'guest'}),reply({document:{id:'ok'}})];
 await api('/api/documents/upload',{method:'POST',body:f});
 assert.equal(calls[1].init.headers.has('Content-Type'),false);
 assert.equal(calls[1].init.headers.get('X-CSRF-Token'),'guest');
});
test('logout retries once after the session CSRF token changes',async()=>{
 queue=[reply({csrf_token:'guest'}),reply({user:{id:'x'},csrf_token:'stale'}),reply({error:{code:'CSRF_REQUIRED',message:'Request a CSRF token from GET /api/auth/csrf and send it in X-CSRF-Token.'}},403),reply({csrf_token:'fresh'}),reply({message:'Logged out.',csrf_token:'after'})];
 await api('/api/auth/login',{method:'POST',body:{email:'x@x.com',password:'pwd'}});
 const result=await api('/api/auth/logout',{method:'POST',body:{}});
 assert.equal(result.message,'Logged out.');
 assert.equal(calls[2].init.headers.get('X-CSRF-Token'),'stale');
 assert.equal(calls[3].url,'/api/auth/csrf');
 assert.equal(calls[4].url,'/api/auth/logout');
 assert.equal(calls[4].init.headers.get('X-CSRF-Token'),'fresh');
});
test('CSRF_REQUIRED refreshes token but never blindly replays mutation',async()=>{
 queue=[reply({csrf_token:'old'}),reply({error:{code:'CSRF_REQUIRED',message:'Expired'}},403),reply({csrf_token:'fresh'})];
 await assert.rejects(()=>api('/api/invitations/accept',{method:'POST',body:{token:'private'}}),e=>e instanceof ApiError && e.code==='CSRF_REQUIRED');
 assert.deepEqual(calls.map(c=>c.url),['/api/auth/csrf','/api/invitations/accept','/api/auth/csrf']);
});
test('Flask field errors are preserved for forms',async()=>{
 queue=[reply({csrf_token:'guest'}),reply({error:{code:'VALIDATION_ERROR',message:'Invalid',fields:{email:'Invalid email'}}},400)];
 await assert.rejects(()=>api('/api/auth/register',{method:'POST',body:{}}),e=>e instanceof ApiError&&e.fields.email==='Invalid email');
});
test('a stale Flask 404 on community activity collections is not reported as a missing record',async()=>{
 for (const path of ['/api/admin/community/discussions','/api/admin/community/suggestions','/api/admin/community/polls','/api/admin/community/proposals']) {
  queue=[new Response('<html>not found</html>',{status:404,headers:{'content-type':'text/html'}})];
  await assert.rejects(()=>api(`${path}?limit=30&offset=0`),error=>error instanceof ApiError && error.status===404 && /Restart Flask/.test(error.message) && !/no longer accessible/.test(error.message));
 }
});
test('only relative /api URLs are permitted',async()=>{
 await assert.rejects(()=>api('http://localhost:5000/api/auth/me'),/Only relative/);assert.equal(calls.length,0);
});
