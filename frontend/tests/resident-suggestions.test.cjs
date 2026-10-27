/* eslint-disable @typescript-eslint/no-require-imports */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const list = fs.readFileSync(path.join(__dirname, '../src/features/suggestions/suggestion-list.tsx'), 'utf8');
const detail = fs.readFileSync(path.join(__dirname, '../src/features/suggestions/suggestion-detail.tsx'), 'utf8');

test('residents submit a title, description, and category and cannot change status', () => {
  assert.match(list, /suggestion-title/);
  assert.match(list, /suggestion-description/);
  assert.match(list, /suggestion-category/);
  assert.match(list, /suggestionApi\.create/);
  assert.match(list, /Badge value=\{suggestion\.status\}/);
  assert.doesNotMatch(list, /name="status"|setStatus|status:/);
  assert.match(detail, /suggestion\.status/);
  assert.match(detail, /Committee decisions are not available/);
  assert.doesNotMatch(detail, /suggestionApi\.create/);
  assert.doesNotMatch(`${list}\n${detail}`, /APPROVED|decision\(/);
});
