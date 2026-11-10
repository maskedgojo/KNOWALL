/* eslint-disable @typescript-eslint/no-require-imports */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const read = file => fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
const shell = read('src/components/shell.tsx');
const types = read('src/lib/civic-types.ts');
const api = read('src/lib/civic-api.ts');
const backendModels = read('../backend/app/modules/civic/models.py');
const backendService = read('../backend/app/modules/civic/service.py');

function loadTs(file) {
  const output = ts.transpileModule(read(file), {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020}});
  const module_ = {exports: {}};
  new Function('module', 'exports', output.outputText)(module_, module_.exports);
  return module_.exports;
}
const geo = loadTs('src/lib/civic-geo.ts');

function backendEnum(name) {
  const block = backendModels.match(new RegExp(`class ${name}\\(str, Enum\\):([\\s\\S]*?)\\n\\n\\n`));
  assert.ok(block, `${name} not found in models.py`);
  return [...block[1].matchAll(/^\s+([A-Z_]+) = "/gm)].map(match => match[1]);
}
const tsArray = name => [...types.match(new RegExp(`export const ${name}=\\[([^\\]]*)\\]`))[1].matchAll(/'([A-Z_]+)'/g)].map(match => match[1]);
const tsUnion = name => [...types.match(new RegExp(`export type ${name}=([^;]*);`))[1].matchAll(/'([A-Z_]+)'/g)].map(match => match[1]);
const tsStates = name => [...types.match(new RegExp(`export const ${name}:CivicState\\[\\]=\\[([^\\]]*)\\]`))[1].matchAll(/'([A-Z_]+)'/g)].map(match => match[1]);

test('map projection round-trips and keeps the coverage edge on the border', () => {
  const area = {center_lat: 20.2961, center_lon: 85.8245, radius_m: 2500};
  const middle = geo.project(area, area.center_lat, area.center_lon);
  assert.deepEqual([middle.x, middle.y], [200, 200]);
  const point = geo.project(area, 20.2985, 85.8270);
  const back = geo.unproject(area, point.x, point.y);
  assert.ok(Math.abs(back.lat - 20.2985) < 1e-6 && Math.abs(back.lon - 85.8270) < 1e-6);
  const north = geo.project(area, area.center_lat + 2500 / 111320, area.center_lon);
  assert.ok(Math.abs(north.y) < 0.01, 'a point exactly one radius north touches the top edge');
});

test('coverage check matches the server idea of "inside"', () => {
  const area = {center_lat: 20.2961, center_lon: 85.8245, radius_m: 2500};
  assert.equal(geo.insideCoverage(area, 20.2964, 85.8248), true);
  assert.equal(geo.insideCoverage(area, 28.6139, 77.2090), false);
  assert.ok(Math.abs(geo.distanceM(0, 0, 0, 1) - 111195) < 200);
});

test('frontend enums mirror the Flask models', () => {
  assert.deepEqual(tsArray('CIVIC_CATEGORIES'), backendEnum('IssueCategory'));
  assert.deepEqual(tsArray('CIVIC_SEVERITIES'), backendEnum('IssueSeverity'));
  assert.deepEqual(tsUnion('CivicState'), backendEnum('IssueState'));
  assert.deepEqual(tsUnion('ConcernType'), backendEnum('ConcernType'));
  assert.deepEqual(tsUnion('ReportDisposition'), backendEnum('ReportDisposition'));
});

test('state groups match the Flask lifecycle constants', () => {
  const backendSet = name => [...backendService.match(new RegExp(`${name} = frozenset\\(\\{([^}]*)\\}\\)`))[1].matchAll(/S\.([A-Z_]+)/g)].map(match => match[1]).sort();
  assert.deepEqual(tsStates('SUPPORTABLE').sort(), backendSet('SUPPORTABLE_STATES'));
  assert.deepEqual(tsStates('REPORTER_EDITABLE').sort(), backendSet('REPORTER_EDITABLE'));
  assert.deepEqual(tsStates('REPORTER_WITHDRAWABLE').sort(), backendSet('REPORTER_WITHDRAWABLE'));
  assert.deepEqual(tsStates('EVIDENCE_EDITABLE').sort(), backendSet('EVIDENCE_EDITABLE'));
});

test('every Flask civic route has a client call', () => {
  const dir = path.join(__dirname, '..', '..', 'backend', 'app', 'modules', 'civic');
  const backend = new Set();
  for (const file of fs.readdirSync(dir).filter(name => name.endsWith('.py'))) {
    for (const match of fs.readFileSync(path.join(dir, file), 'utf8').matchAll(/@\w+_bp\.(\w+)\("(\/api\/civic\/[^"]+)"/g)) {
      backend.add(`${match[1].toUpperCase()} ${match[2].replace(/<uuid:\w+>/g, ':id')}`);
    }
  }
  assert.ok(backend.size >= 20, 'expected the civic routes to be discovered');
  const client = new Set();
  for (const match of api.matchAll(/=>api<[^`'"]*>\(\s*(?:`([^`]*)`|'([^']*)')([^)]*)\)/g)) {
    const urlPath = (match[1] ?? match[2]).replace(/\$\{pathId\([^}]+\)\}/g, ':id').replace(/\$\{query\(.*\)\}/g, '').split('?')[0];
    const method = (match[3].match(/method:'(\w+)'/) || [, 'GET'])[1];
    client.add(`${method} ${urlPath}`);
  }
  client.add('GET /api/civic/evidence/:id/file'); // fetched as a blob by civicEvidenceFile
  assert.match(api, /\/evidence`,\{method:'POST',body:form\}/); // multipart upload has a block body
  client.add('POST /api/civic/issues/:id/evidence');
  for (const route of backend) assert.ok(client.has(route), `no client call for ${route}`);
});

test('resident screens never use the coordinator API', () => {
  for (const name of ['issue-list', 'report-wizard', 'issue-detail', 'parts']) {
    assert.doesNotMatch(read(`src/features/civic/${name}.tsx`), /civicAdminApi/);
  }
  assert.match(read('src/features/civic/admin-civic.tsx'), /civicAdminApi\.route\(/);
  assert.match(read('src/app/admin/civic/page.tsx'), /<Protected admin>/);
});

test('navigation is gated on Flask-issued permissions', () => {
  assert.match(shell, /civic\.issues\.create'\)\?\[\['\/civic'/);
  assert.match(shell, /identity\.admin\.manage'\)\?\[\['\/admin\/civic'/);
});

test('residents never send lifecycle states or routing payloads', () => {
  const resident = ['issue-list', 'report-wizard', 'issue-detail'].map(name => read(`src/features/civic/${name}.tsx`)).join('\n');
  assert.doesNotMatch(resident, /state:\s*['"](VALIDATED|READY_FOR_ROUTING|MERGED)/);
  assert.match(read('src/features/civic/report-wizard.tsx'), /save_as_draft: true/);
});

test('photos are fetched through Flask and sniffed before display', () => {
  assert.match(api, /\/api\/civic\/evidence\//);
  assert.match(api, /0x89[\s\S]*0xff/);
  assert.doesNotMatch(read('src/features/civic/parts.tsx'), /src=\{`\/api/);
});
