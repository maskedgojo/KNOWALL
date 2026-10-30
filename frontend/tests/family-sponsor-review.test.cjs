/* eslint-disable @typescript-eslint/no-require-imports */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const read=f=>fs.readFileSync(path.join(root,f),'utf8');
test('family sponsor is read only from admin application detail, never a guessed name',()=>{
  const helpers=read('src/lib/family-review.ts');
  assert.match(helpers,/sponsor_context/);
  assert.match(helpers,/sponsor_membership_id/);
  assert.match(helpers,/household_id/);
  assert.match(helpers,/eligible_to_sponsor/);
  assert.doesNotMatch(helpers,/adminApi\.memberships/);
});
test('admin review distinguishes family sponsor from resident and checks approval prerequisites',()=>{
  const review=read('src/features/admin/review.tsx');
  assert.match(review,/familyApplication/);
  assert.match(review,/FamilySponsorPanel/);
  assert.match(review,/familyReviewed/);
  assert.match(review,/sponsorReady/);
});
test('OCR comparison remains unchanged; sponsor match is an advisory second comparison',()=>{
  const evidence=read('src/features/admin/review-evidence.tsx');
  assert.match(evidence,/OcrFindings data=\{history\.value\}/);
  assert.match(evidence,/namesComparable/);
  assert.match(evidence,/does not prove the applicant/);
  assert.doesNotMatch(evidence,/residentApi\.ocr\(id\)/);
});

const ts=require('typescript');
function loadSponsorHelpers(){
  const src=read('src/lib/family-review.ts');
  const js=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const mod={exports:{}};
  new Function('module','exports','require',js)(mod,mod.exports,require);
  return mod.exports;
}
const {sponsorFromApplicationDetail,sponsorReviewStatus,namesComparable}=loadSponsorHelpers();
const detail={
  application:{category:'FAMILY_MEMBER',sponsor_membership_id:'mem-owner-1',household_id:'household-1',flat:{id:'flat-102'}},
  sponsor_context:{membership_id:'mem-owner-1',display_name:'Rahul Sharma',category:'OWNER',membership_status:'ACTIVE',household_id:'household-1',household_label:'Owner household',flat_id:'flat-102',eligible_to_sponsor:true,valid_from:'2026-01-01',valid_until:null}
};
test('real sponsor context is resolved only when it matches the application binding',()=>{
  const sponsor=sponsorFromApplicationDetail(detail);
  assert.equal(sponsor.display_name,'Rahul Sharma');
  assert.equal(sponsorReviewStatus(sponsor),'ELIGIBLE');
});
test('same flat but DIFFERENT household never supplies a sponsor identity',()=>{
  const changed={...detail,sponsor_context:{...detail.sponsor_context,household_id:'tenant-household'}};
  assert.equal(sponsorFromApplicationDetail(changed),null);
});
test('different sponsor membership ID is not accepted',()=>{
  assert.equal(sponsorFromApplicationDetail({...detail,sponsor_context:{...detail.sponsor_context,membership_id:'other'}}),null);
});
test('suspended sponsor can be shown but cannot be treated as eligible',()=>{
  const ctx=sponsorFromApplicationDetail({...detail,sponsor_context:{...detail.sponsor_context,membership_status:'SUSPENDED',eligible_to_sponsor:false}});
  assert.equal(ctx.display_name,'Rahul Sharma');
  assert.equal(sponsorReviewStatus(ctx),'INELIGIBLE');
});
test('name comparison is strict and advisory (no fuzzy guessing)',()=>{
  assert.equal(namesComparable('  RAHUL   SHARMA  ','Rahul Sharma'),true);
  assert.equal(namesComparable('Rahul S.','Rahul Sharma'),false);
  assert.equal(namesComparable('','Rahul Sharma'),false);
});
