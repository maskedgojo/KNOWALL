/* eslint-disable @typescript-eslint/no-require-imports */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
const root=path.resolve(__dirname,'..');
function source(p){return fs.readFileSync(path.join(root,p),'utf8');}
function load(rel){
  const compiled=ts.transpileModule(source(rel),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const mod={exports:{}};
  new Function('module','exports',compiled)(mod,mod.exports);
  return mod.exports;
}
const routes=load('src/lib/login-routing.ts');
const invitations=load('src/lib/invitation-link.ts');
test('resident login ignores any prior administrator page',()=>{
  assert.equal(routes.destinationAfterLogin(['APPLICANT','RESIDENT'],false),'/dashboard');
});
test('administrator login uses their own dashboard',()=>{
  assert.equal(routes.destinationAfterLogin(['SOCIETY_ADMIN'],false),'/admin');
});
test('intentional private invitation is the only post-login route exception',()=>{
  assert.equal(routes.destinationAfterLogin(['RESIDENT'],true),'/invitations/accept');
});
test('routine protected routes do not persist old ?next query on login redirect',()=>{
  assert.equal(routes.signedOutDestination,'/login');
  assert.doesNotMatch(source('src/components/shell.tsx'),/router\.replace\(`\/login\?next=/);
  assert.doesNotMatch(source('src/features/auth/auth-screens.tsx'),/secureNext\(next/);
});
test('logout normally clears pending account-specific invitation state',()=>{
  const auth=source('src/components/auth-provider.tsx');
  assert.match(auth,/if\(!options\?\.preserveInvitation\) clearPendingInvitation\(\)/);
  assert.match(source('src/features/onboarding/accept-invitation.tsx'),/preserveInvitation:true/);
});
test('parses a single-use emailed invitation link without navigation to its URL',()=>{
  assert.deepEqual(invitations.parseInvitationLink('https://example.test/invitations/accept?token=exampleToken0123456789&invitation_id=one'),
    {token:'exampleToken0123456789',invitationId:'one'});
  assert.deepEqual(invitations.parseInvitationLink('exampleToken0123456789'),{token:'exampleToken0123456789'});
});
test('rejects unrelated and unsafe URLs and invalid tokens',()=>{
  for(const link of ['','https://example.com/login?token=exampleToken0123456789','javascript:alert(1)',
    'https://example.test/api/invitations/accept?token=exampleToken0123456789','bad']){
    assert.equal(invitations.parseInvitationLink(link),null);
  }
});
test('received list links already accepted invitations to real returned application IDs',()=>{
  const ui=source('src/features/onboarding/invitations.tsx');
  assert.match(ui,/knownApplications\.find\(a=>a\.invitation_id===inv\.id\)/);
  assert.match(ui,/onboarding\/\$\{encodeURIComponent\(application\.id\)\}/);
  assert.match(ui,/rememberInvitation\(pending\.token,pending\.invitationId\)/);
});
test('outgoing history is NOT falsely reported as available without a Flask endpoint',()=>{
  const spec=JSON.parse(source('contracts/openapi.json'));
  assert.equal(spec.paths['/api/invitations/sent'],undefined);
  assert.equal(spec.paths['/api/invitations/{invitation_id}/accept'],undefined);
  const ui=source('src/features/onboarding/invitations.tsx');
  assert.match(ui,/Your sent invitation history is not available yet/);
});
