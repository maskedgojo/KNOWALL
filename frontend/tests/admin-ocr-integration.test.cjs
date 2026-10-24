/* eslint-disable @typescript-eslint/no-require-imports -- Node test runner uses CommonJS */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const read=(f)=>fs.readFileSync(path.join(root,f),'utf8');
const spec=JSON.parse(read('contracts/openapi.json'));

test('admin OCR review uses documented read-only document history API',()=>{
  assert.ok(spec.paths['/api/documents/{document_id}/ocr'].get);
  const evidence=read('src/features/admin/review-evidence.tsx');
  const endpoints=read('src/lib/endpoints.ts');
  assert.match(evidence,/residentApi\.ocrHistory\(id\)/);
  assert.match(endpoints,/ocrHistory:\(id:string\)=>api<unknown>\(`\/api\/documents\/\$\{pathId\(id\)\}\/ocr`\)/);
  assert.doesNotMatch(evidence,/residentApi\.ocr\(id\)/);
});

test('admin screen actually includes an OCR panel per uploaded evidence, not only embedded fields',()=>{
  const review=read('src/features/admin/review.tsx');
  assert.match(review,/docs\.map\(doc=><AdminEvidence/);
  assert.match(review,/docsReady/);
  assert.match(review,/acknowledge_ocr_warnings:ack/);
  const evidence=read('src/features/admin/review-evidence.tsx');
  assert.match(evidence,/<OcrFindings data=\{history\.value\}/);
  assert.match(evidence,/<PrivatePreview id=\{id\}/);
  assert.doesNotMatch(evidence,/JSON\.stringify/);
});
