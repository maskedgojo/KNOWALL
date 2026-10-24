/* eslint-disable @typescript-eslint/no-require-imports -- CommonJS Node built-in test runner */
const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const spec=JSON.parse(fs.readFileSync(path.join(__dirname,'../contracts/openapi.json'),'utf8'));
test('uploaded OpenAPI includes new Module 1 enhancement endpoints',()=>{
 const expected={'/api/me/family-tree':'get','/api/me/profile':'patch','/api/admin/memberships/{membership_id}/occupancy':'patch','/api/admin/memberships/{membership_id}/relationship':'patch','/api/auth/verify-email':'post','/api/auth/password/reset':'post'};
 for(const [route,method] of Object.entries(expected))assert.ok(spec.paths[route]?.[method],`${method} ${route} missing`);
});
test('flask session and CSRF are the only auth schemes',()=>{
 assert.ok(spec.components.securitySchemes.SessionCookie);
 assert.ok(spec.components.securitySchemes.CsrfHeader);
 assert.equal(Object.keys(spec.components.securitySchemes).length,2);
});
test('new profile and occupancy nullable unknown are represented accurately',()=>{
 const schemas=spec.components.schemas;
 assert.equal(schemas.Membership.properties.is_current_occupant.nullable,true);
 assert.equal(schemas.Application.properties.declared_current_occupant.nullable,true);
 assert.ok(schemas.User.properties.occupation);
 assert.ok(schemas.User.properties.date_of_birth);
});
