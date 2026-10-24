/* eslint-disable @typescript-eslint/no-require-imports -- Node's built-in CommonJS tests */
const {test,beforeEach,afterEach}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
const source=fs.readFileSync(path.join(__dirname,'../src/lib/api.ts'),'utf8');
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const mod={exports:{}};new Function('module','exports','require',js)(mod,mod.exports,require);
const {privateFile}=mod.exports;
const oldFetch=global.fetch,oldUrl=URL.createObjectURL;
let calls=[];let createdBlob;
beforeEach(()=>{calls=[];URL.createObjectURL=blob=>{createdBlob=blob;return 'blob:http://localhost:3000/test-preview'};});
afterEach(()=>{global.fetch=oldFetch;URL.createObjectURL=oldUrl;createdBlob=undefined;});
function respond(bytes){global.fetch=async (url,options)=>{calls.push({url,options});return new Response(new Blob([new Uint8Array(bytes)],{type:'application/octet-stream'}),{status:200,headers:{'content-disposition':'attachment; filename="private"'}});};}
test('private PNG attachment opens as safe inline PNG blob',async()=>{
 respond([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a,0x00]);
 const result=await privateFile('safe-id');
 assert.equal(result.type,'image/png');assert.equal(createdBlob.type,'image/png');
 assert.equal(calls[0].url,'/api/documents/safe-id/file');assert.equal(calls[0].options.credentials,'same-origin');
 assert.equal(calls[0].options.cache,'no-store');
});
test('private PDF attachment is recognized without trusting octet-stream',async()=>{
 respond([0x25,0x50,0x44,0x46,0x2d,0x31,0x2e,0x37]);
 const result=await privateFile('pdf-id');assert.equal(result.type,'application/pdf');assert.equal(createdBlob.type,'application/pdf');
});
test('an HTML-like attachment cannot be rendered as trusted inline media',async()=>{
 respond([0x3c,0x68,0x74,0x6d,0x6c,0x3e]);
 const result=await privateFile('unknown');assert.equal(result.type,'application/octet-stream');
});
