/* eslint-disable @typescript-eslint/no-require-imports */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../src/features/governance/governance-history.tsx'), 'utf8');

test('governance history shows safe summaries and does not render raw audit payloads', () => {
  assert.match(source, /governanceApi\.history/);
  assert.match(source, /event\.summary/);
  assert.match(source, /event\.event_type/);
  assert.match(source, /event\.occurred_at/);
  assert.match(source, /event\.resource_path/);
  assert.match(source, /Private disputes and individual poll responses are not listed/);
  assert.doesNotMatch(source, /details|actor_user_id|token|email/);
});
