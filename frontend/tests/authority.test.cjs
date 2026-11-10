/* eslint-disable @typescript-eslint/no-require-imports */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

// Normalise CRLF so the checks behave the same on Windows checkouts (git autocrlf).
const read = file => fs.readFileSync(path.join(__dirname, '..', file), 'utf8').replace(/\r\n/g, '\n');
const types = read('src/lib/authority-types.ts');
const api = read('src/lib/authority-api.ts');
const shell = read('src/components/shell.tsx');
const issueDetail = read('src/features/civic/issue-detail.tsx');
const backendModels = read('../backend/app/modules/authority/models.py');
const backendService = read('../backend/app/modules/authority/service.py');

function backendEnum(name) {
  const block = backendModels.match(new RegExp(`class ${name}\\(str, Enum\\):([\\s\\S]*?)\\n\\n\\n`));
  assert.ok(block, `${name} not found in models.py`);
  return [...block[1].matchAll(/^\s+([A-Z_]+) = "/gm)].map(match => match[1]);
}
function backendSet(name) {
  const block = backendService.match(new RegExp(`^${name} = frozenset\\(\\{([^}]*)\\}\\)`, 'm'));
  assert.ok(block, `${name} not found in service.py`);
  return [...block[1].matchAll(/C\.([A-Z_]+)/g)].map(match => match[1]).sort();
}
const tsList = name => [...types.match(new RegExp(`export const ${name}(?::CaseStatus\\[\\])?=\\[([^\\]]*)\\]`))[1].matchAll(/'([A-Z_]+)'/g)].map(match => match[1]);
const tsUnion = name => [...types.match(new RegExp(`export type ${name}=([^;]*);`))[1].matchAll(/'([A-Z_]+)'/g)].map(match => match[1]);

test('case statuses match the backend enum in order', () => {
  assert.deepEqual(tsList('CASE_STATUSES'), backendEnum('CaseStatus'));
});

test('verdict, evidence type and closure basis unions match the backend', () => {
  assert.deepEqual(tsUnion('Verdict').sort(), backendEnum('Verdict').sort());
  assert.deepEqual(tsUnion('EvidenceType').sort(), backendEnum('EvidenceType').sort());
  assert.deepEqual(tsUnion('ClosureBasis').sort(), backendEnum('ClosureBasis').sort());
});

test('UI action gates mirror the backend lifecycle sets', () => {
  assert.deepEqual(tsList('WORKABLE').sort(), backendSet('WORKABLE'));
  assert.deepEqual(tsList('TRANSFERABLE').sort(), backendSet('TRANSFERABLE'));
  assert.deepEqual(tsList('OPEN_STATUSES').sort(), backendSet('OPEN_STATUSES'));
});

test('every Module 6 screen shows the simulated-authority banner', () => {
  for (const file of ['officer-workspace', 'case-workspace', 'case-tracker', 'admin-authority', 'analytics']) {
    assert.match(read(`src/features/authority/${file}.tsx`), /<SimulationBanner\/>/, `${file} must render SimulationBanner`);
  }
  assert.match(types, /not real government bodies/);
});

test('the API client only calls relative Flask routes and checks file signatures', () => {
  const routes = [...api.matchAll(/`(\/api\/[^`]*)`|'(\/api\/[^']*)'/g)].map(match => match[1] ?? match[2]);
  assert.ok(routes.length > 15);
  for (const route of routes) assert.match(route, /^\/api\/(authority|civic|admin\/analytics)\//);
  assert.match(api, /startsWith\('\/api\/authority\/'\)/);
  assert.match(api, /0x89/);
});

test('navigation and the civic issue page are wired to Module 6', () => {
  assert.match(shell, /'\/admin\/authority'/);
  assert.match(shell, /'\/admin\/analytics'/);
  assert.match(shell, /officer\?\[\['\/authority'/);
  assert.match(issueDetail, /<CaseTracker issueId=\{id\}/);
  assert.doesNotMatch(issueDetail, /JSON\.stringify\(issue\.authoritative_status\)/);
});
