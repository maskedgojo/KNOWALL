/* eslint-disable @typescript-eslint/no-require-imports -- Node's built-in CommonJS tests */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
const code=fs.readFileSync(path.join(__dirname,'../src/lib/ocr-view.ts'),'utf8');
const compiled=ts.transpileModule(code,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const mod={exports:{}};
new Function('module','exports',compiled)(mod,mod.exports);
const {latestOcr,ocrSummary}=mod.exports;
const saved={results:[{id:'result-1',status:'COMPLETED',created_at:'2026-10-23T13:29:50+05:30',completed_at:'2026-10-23T13:32:29+05:30',comparison_results:{resident_name:{entered:'Kushaagra Singh',extracted:'Rahul Sharma',status:'MISMATCH'},tower:{entered:'A',extracted:'B',status:'MISMATCH'},flat_number:{entered:'903',extracted:'402',status:'MISMATCH'},category:{entered:'OWNER',extracted:'OWNER',status:'MATCH'}},warnings:['Manual review required']}]};
test('builds a human-readable comparison for the exact saved result shape',()=>{
  const view=latestOcr(saved);
  assert.equal(view.status,'COMPLETED');
  assert.deepEqual(ocrSummary(view),{matched:1,mismatched:3,unconfirmed:0});
  assert.deepEqual(view.comparisons.map(x=>x.label),['Resident name','Tower','Flat number','Resident category']);
  assert.equal(view.comparisons[0].extracted,'Rahul Sharma');
  assert.deepEqual(view.warnings,['Manual review required']);
});
test('no fabricated results when backend history is empty',()=>{assert.equal(latestOcr({results:[]}),null);});
test('most recent failed run takes priority over earlier completed OCR',()=>{
  const view=latestOcr({results:[saved.results[0],{id:'result-2',created_at:'2026-10-23T14:00:00+05:30',status:'FAILED',error_message:'Model unavailable'}]});
  assert.equal(view.id,'result-2');assert.equal(view.status,'FAILED');assert.deepEqual(ocrSummary(view),{matched:0,mismatched:0,unconfirmed:0});
});
test('unknown status is not treated as a match',()=>{
  const view=latestOcr({results:[{status:'COMPLETED',comparison_results:{tower:{entered:'A',extracted:'A',status:'UNVERIFIED'}}}]});
  assert.equal(view.comparisons[0].status,'UNKNOWN');
  assert.equal(ocrSummary(view).unconfirmed,1);
});
test('admin latest OCR object accepts external warning array',()=>{
  const view=latestOcr({status:'COMPLETED',comparison_results:{category:{entered:'OWNER',extracted:'OWNER',status:'MATCH'}}},['Additional check']);
  assert.equal(ocrSummary(view).matched,1);
  assert.deepEqual(view.warnings,['Additional check']);
});
