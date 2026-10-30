/* eslint-disable @typescript-eslint/no-require-imports */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const read = file => fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
const shell = read('src/components/shell.tsx');
const types = read('src/lib/operations-types.ts');
const backendTickets = read('../backend/app/modules/operations/maintenance.py');
const features = ['facilities', 'my-bookings', 'events', 'maintenance', 'development'].map(name => read(`src/features/operations/${name}.tsx`)).join('\n');
const admin = ['admin-facilities', 'admin-events', 'admin-maintenance', 'admin-development'].map(name => read(`src/features/operations/${name}.tsx`)).join('\n');

test('Module 3 navigation is gated on Flask-issued permissions', () => {
  assert.match(shell, /can\('society\.facilities\.book'\)\?RESIDENT_BOOKINGS/);
  assert.match(shell, /RESIDENT_BOOKINGS:NavItem\[\]=\[\['\/facilities'/);
  assert.match(shell, /can\('society\.operations\.manage'\)\?ADMIN_SERVICES/);
  assert.match(shell, /ADMIN_SERVICES:NavItem\[\]=\[\['\/admin\/facilities'/);
  assert.match(admin, /permissions\.includes\('society\.operations\.manage'\)/);
  assert.doesNotMatch(features, /operationsAdminApi/);
});

test('resident screens never send a booking or ticket status', () => {
  assert.doesNotMatch(features, /status:\s*['"](CONFIRMED|APPROVED|COMPLETED)/);
  assert.match(features, /operationsApi\.book\(/);
  assert.match(read('src/features/operations/ticket-detail.tsx'), /'CONFIRM'|'REOPEN'/);
});

test('frontend ticket transitions match the Flask ADMIN_TRANSITIONS table', () => {
  const start = backendTickets.indexOf('ADMIN_TRANSITIONS = {');
  const block = backendTickets.slice(start, backendTickets.indexOf('\n}', start));
  const backend = {};
  for (const [, from, to] of block.matchAll(/TicketStatus\.(\w+): \{([^}]*)/g)) backend[from] = [...to.matchAll(/TicketStatus\.(\w+)/g)].map(m => m[1]);
  const frontend = {};
  const line = types.match(/NEXT_TICKET_STATUS[^=]*=\{(.*)\};/)[1];
  for (const [, from, to] of line.matchAll(/(\w+):\[([^\]]*)\]/g)) frontend[from] = [...to.matchAll(/'(\w+)'/g)].map(m => m[1]);
  assert.deepEqual(frontend, backend);
});

test('wall-clock time is read when data loads, not during render', () => {
  for (const name of ['events', 'my-bookings']) {
    const source = read(`src/features/operations/${name}.tsx`);
    assert.match(source, /loadedAt: Date\.now\(\)/);
    assert.equal(source.match(/Date\.now\(\)/g).length, 1);
  }
});

test('photos are fetched privately through Flask, never by public URL', () => {
  const photos = read('src/features/operations/photos.tsx');
  assert.match(photos, /privateOperationPhoto\(/);
  assert.match(photos, /URL\.revokeObjectURL/);
  assert.match(photos, /accept="image\/png,image\/jpeg"/);
  assert.doesNotMatch(photos, /src=\{`\/api|href=\{`\/api/);
  assert.match(read('src/lib/api.ts'), /\/api\/operations\/photos\/\$\{encodeURIComponent\(id\)\}\/file/);
});

test('volunteering and booking caps are surfaced to residents', () => {
  const events = read('src/features/operations/events.tsx');
  assert.match(events, /operationsApi\.volunteer\(/);
  assert.match(events, /event\.updates/);
  assert.match(read('src/features/operations/facilities.tsx'), /max_upcoming_per_resident/);
});