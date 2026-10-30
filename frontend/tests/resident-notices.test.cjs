/* eslint-disable @typescript-eslint/no-require-imports */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../src/features/notices/resident-notices.tsx'), 'utf8');
const manage = fs.readFileSync(path.join(__dirname, '../src/features/notices/manage-notices.tsx'), 'utf8');

test('resident list drops expired notices on the client clock without archiving them', () => {
  assert.match(source, /export function residentNoticeCurrent/);
  assert.match(source, /notice\.status !== 'PUBLISHED'/);
  assert.match(source, /visible_to_residents === false/);
  assert.match(source, /expiry > now/);
  assert.match(source, /residentNoticeCurrent\(notice, now\)/);
  assert.doesNotMatch(source, /archive\(/);
});

test('replacement is offered only for a published notice', () => {
  assert.match(manage, /current\?\.status === 'PUBLISHED' && <Button variant="secondary"/);
  assert.match(manage, /noticeApi\.replace/);
  assert.doesNotMatch(manage, /current\?\.published_at && <Button/);
});
