/* eslint-disable @typescript-eslint/no-require-imports */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const root = path.join(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
function load(rel) {
  const compiled = ts.transpileModule(read(rel), {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText;
  const mod = {exports: {}};
  new Function('module', 'exports', 'require', compiled)(mod, mod.exports, require);
  return mod.exports;
}
const shell = read('src/components/shell.tsx');
const api = read('src/lib/locality-api.ts');
const residentFiles = ['overview', 'directory', 'place-detail', 'correction-form', 'my-corrections', 'events', 'alerts'];
const resident = residentFiles.map(name => read(`src/features/locality/${name}.tsx`)).join('\n');
const desk = ['desk', 'places', 'place-editor', 'corrections', 'events', 'alerts', 'reports'].map(name => read(`src/features/locality/manage/${name}.tsx`)).join('\n');
const shared = read('src/features/locality/shared.tsx');
const backendRoutes = ['directory', 'corrections', 'content'].map(name => read(`../backend/app/modules/locality/${name}.py`)).join('\n');

test('locality navigation is gated on Flask permissions; the desk needs locality.manage', () => {
  assert.match(shell, /can\('locality\.read'\)\?\[\.\.\.RESIDENT_LOCALITY/);
  assert.match(shell, /can\('locality\.manage'\)\?LOCALITY_DESK/);
  assert.match(shell, /can\('locality\.listings\.suggest'\)\?\[\['\/locality\/corrections'/);
  // The admin workspace links only to reading and sharing, never to the desk.
  assert.match(shell, /ADMIN_LOCALITY:NavItem\[\]=\[\['\/locality','Locality overview'.*?\['\/locality\/events','Share society events'/);
  assert.doesNotMatch(shell.match(/ADMIN_LOCALITY:NavItem\[\]=.*/)[0], /\/locality\/manage/);
});

test('section roots are not highlighted on every child route', () => {
  assert.match(shell, /\['\/admin','\/locality','\/locality\/manage'\]\.includes\(href\)/);
});

test('every desk screen is wrapped in a locality.manage gate', () => {
  for (const name of ['desk', 'places', 'place-editor', 'corrections', 'events', 'alerts', 'reports']) {
    assert.match(read(`src/features/locality/manage/${name}.tsx`), /<LocalityGate permission="locality\.manage"/, name);
  }
  assert.doesNotMatch(resident, /localityAdminApi/);
});

test('a coordinator who is not a resident lands on the desk after login', () => {
  const routes = load('src/lib/login-routing.ts');
  assert.equal(routes.destinationAfterLogin(['LOCALITY_COORDINATOR'], false), '/locality/manage');
  assert.equal(routes.destinationAfterLogin(['LOCALITY_COORDINATOR', 'RESIDENT'], false), '/dashboard');
  assert.equal(routes.destinationAfterLogin(['SOCIETY_ADMIN'], false), '/admin');
});

test('every client route exists in the Flask locality blueprint', () => {
  const paths = [...api.matchAll(/`?'?(\/api\/locality\/[a-z/${}().:A-Z_-]*)/g)].map(match => match[1]
    .replace(/\$\{pathId\([a-zA-Z]+\)\}/g, '<id>').replace(/\$\{query\(.*$/, '').replace(/[`'].*$/, ''));
  assert.ok(paths.length >= 30);
  const flask = [...backendRoutes.matchAll(/@locality_bp\.(?:get|post|patch)\("([^"]+)"\)/g)].map(match => match[1].replace(/<uuid:[a-z_]+>/g, '<id>'));
  for (const route of new Set(paths)) assert.ok(flask.includes(route), `missing Flask route for ${route}`);
});

test('resident correction form sends only whitelisted proposal fields', () => {
  const form = read('src/features/locality/correction-form.tsx');
  assert.doesNotMatch(form, /status:|reviewer|version:/);
  assert.match(form, /body\.proposed_value=/);
  assert.match(form, /A coordinator reviews every report/);
});

test('moderation decisions always carry a reason', () => {
  const corrections = read('src/features/locality/manage/corrections.tsx');
  assert.match(corrections, /decideCorrection\(c\.id,decision,reason\.trim\(\)\)/);
  assert.match(corrections, /disabled=\{reason\.trim\(\)\.length<5/);
  assert.match(read('src/features/locality/manage/common.tsx'), /disabled=\{reason\.trim\(\)\.length<minimum\}/);
  assert.match(desk, /<ReasonAction label="Archive"/);
});

test('edits send the version the coordinator opened (conflict protection)', () => {
  assert.match(read('src/features/locality/manage/place-editor.tsx'), /expected_version:place\.version/);
});

test('fictional data, staleness and sources are visible to residents', () => {
  assert.match(shared, /Every place, phone number, event and alert in this locality is fictional/);
  assert.match(shared, /has not been re-verified in over/);
  assert.match(shared, /<dt className="muted">Source<\/dt>/);
  assert.match(shared, /<dt className="muted">Last verified<\/dt>/);
  assert.match(resident, /<FictionalNotice/);
});

test('only http(s) links are rendered as clickable', () => {
  const types = load('src/lib/locality-types.ts');
  assert.equal(types.safeHref('https://example.org/x'), 'https://example.org/x');
  assert.equal(types.safeHref('javascript:alert(1)'), null);
  assert.equal(types.safeHref('data:text/html,hi'), null);
  assert.match(shared, /rel="noopener noreferrer nofollow"/);
  assert.doesNotMatch(resident + desk, /dangerouslySetInnerHTML/);
});

test('society event sharing shows no RSVP data', () => {
  const events = read('src/features/locality/events.tsx');
  assert.match(events, /can\('society\.operations\.manage'\)&&<ShareSocietyEvents\/>/);
  assert.match(events, /RSVP lists and capacity never are/);
  assert.doesNotMatch(events, /going_count|waitlist|capacity:/);
});

test('the map is a labelled schematic, not a real street map', () => {
  assert.match(shared, /Schematic map: positions show distance and direction from the society, not real streets/);
  assert.doesNotMatch(shared + resident, /tile\.openstreetmap|maps\.googleapis|leaflet/i);
  assert.match(shared, /aria-pressed=\{active\}/);
});
