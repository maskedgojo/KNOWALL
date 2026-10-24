const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');

test('invitation success branches on Flask outcome rather than client category',()=>{
 const code=read('src/features/onboarding/accept-invitation.tsx');
 assert.match(code,/response\.outcome==='FAMILY_MEMBERSHIP_ACTIVATED'/);
 assert.match(code,/response\.outcome==='APPLICATION_DRAFT_CREATED'/);
 assert.match(code,/response\.membership\?\.id/);
 assert.match(code,/response\.application\?\.id/);
 assert.match(code,/residentApi\.memberships\(\)/);
 assert.match(code,/session\.refresh\(\)/);
 assert.match(code,/router\.replace\('\/dashboard\?family=activated'\)/);
 assert.match(code,/router\.replace\(`\/onboarding\/\$\{encodeURIComponent\(response\.application\.id\)\}/);
});

test('family activation no longer requires application or OCR in acceptance flow',()=>{
 const code=read('src/features/onboarding/accept-invitation.tsx');
 assert.doesNotMatch(code,/residentApi\.submit\(/);
 assert.doesNotMatch(code,/residentApi\.ocr\(/);
 assert.match(code,/join household/);
});

test('owner/tenant application pages remain and historical family reviews are preserved',()=>{
 for(const p of ['src/app/onboarding/[id]/page.tsx','src/app/admin/applications/[id]/page.tsx'])assert.equal(fs.existsSync(path.join(__dirname,'..',p)),true);
});

test('new protected household and evidence pages exist',()=>{
 for(const p of ['src/app/admin/households/page.tsx','src/app/admin/evidence-requests/page.tsx','src/app/evidence-requests/page.tsx']){
  const code=read(p); assert.match(code,/<Protected/);
 }
});

test('typed API clients use only specified new Flask routes',()=>{
 const code=read('src/lib/endpoints.ts');
 for(const route of ['/api/admin/households','/api/me/evidence-requests','/api/admin/evidence-requests','/api/member-evidence/']){
  assert.match(code+read('src/lib/api.ts'),new RegExp(route.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
 }
 assert.match(code,/form\.set\('file',file\)/);
 assert.match(code,/api\/me\/evidence-requests\/\$\{pathId\(id\)\}\/upload/);
 assert.match(code,/api\/admin\/memberships\/\$\{pathId\(membershipId\)\}\/evidence-requests/);
});

test('resident evidence UI validates private files, displays requests and does not suspend automatically',()=>{
 const code=read('src/features/evidence/resident-requests.tsx');
 assert.match(code,/5\*1024\*1024/);
 assert.match(code,/['"]image\/png['"]/);
 assert.match(code,/['"]application\/pdf['"]/);
 assert.match(code,/residentApi\.uploadMemberEvidence/);
 assert.match(code,/item\.status==='REQUESTED'/);
 assert.doesNotMatch(code,/adminApi\.status\(/);
});

test('admin review enforces current evidence lifecycle restrictions',()=>{
 const code=read('src/features/admin/evidence-requests.tsx');
 assert.match(code,/item\.status==='REQUESTED'&&action!=='CANCELLED'/);
 assert.match(code,/item\.status==='SUBMITTED'&&action==='CANCELLED'/);
 assert.match(code,/adminApi\.resolveEvidence/);
});

test('admin directory is grouped by backend household IDs, not by flats',()=>{
 const code=read('src/features/admin/households.tsx');
 assert.match(code,/households\.map\(h=>/);
 assert.match(code,/key=\{h\.household_id\}/);
 assert.match(code,/sponsor_display_name/);
 assert.match(code,/declared_current_occupant/);
});

test('navigation and resident dashboard surface evidence requests',()=>{
 const shell=read('src/components/shell.tsx'),dash=read('src/features/resident/dashboard.tsx');
 for(const route of ['/evidence-requests','/admin/households','/admin/evidence-requests'])assert.ok(shell.includes(route));
 assert.match(dash,/residentApi\.evidenceRequests/);
 assert.match(dash,/Your family membership was activated by Flask/);
});
