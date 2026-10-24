/* eslint-disable @typescript-eslint/no-require-imports -- Node's CommonJS test runner */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');

const source=fs.readFileSync(path.join(__dirname,'../src/features/auth/validation.ts'),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const loaded={exports:{}};
new Function('module','exports','require',compiled)(loaded,loaded.exports,require);
const {validateAuthForm,normalizeAuthFieldErrors,errorSummary}=loaded.exports;
const data={display_name:'Test User',email:'test@example.com',phone:'',password:'LongEnough!2026',confirm:'LongEnough!2026'};

test('valid registration has no client validation errors',()=>{
  assert.deepEqual(validateAuthForm('register',data),{});
});

test('registration catches 8-character password before calling Flask',()=>{
  const errors=validateAuthForm('register',{...data,password:'12345678',confirm:'12345678'});
  assert.match(errors.password,/12 and 128 characters/);
});

test('registration shows confirmation mismatch at the confirmation field',()=>{
  const errors=validateAuthForm('register',{...data,confirm:'DifferentPassword'});
  assert.match(errors.confirm,/do not match/);
});

test('registration shows invalid email and name independently',()=>{
  const errors=validateAuthForm('register',{...data,display_name:'T',email:'not-an-email'});
  assert.ok(errors.display_name);
  assert.ok(errors.email);
});

test('backend field errors remain visible, including unknown fields',()=>{
  const value=normalizeAuthFieldErrors({password:'Too short.',email:'Invalid email.',policy:'Not eligible.'});
  assert.equal(value.fields.password,'Too short.');
  assert.equal(value.fields.email,'Invalid email.');
  assert.deepEqual(value.extra,['policy: Not eligible.']);
});

test('reset backend new_password error maps to visible password input',()=>{
  const value=normalizeAuthFieldErrors({new_password:'Use a different password.'});
  assert.equal(value.fields.password,'Use a different password.');
});

test('registration duplicate email message is actionable',()=>{
  assert.match(errorSummary(409,'EMAIL_ALREADY_REGISTERED','register',false),/Sign in or use Forgot password/);
});

test('ambiguous 400 without backend fields is not falsely attributed to a specific input',()=>{
  assert.match(errorSummary(400,'VALIDATION_ERROR','register',false),/did not identify a field/);
});
