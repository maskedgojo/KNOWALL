/* eslint-disable @typescript-eslint/no-require-imports */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../src/features/community/community-activity.tsx'), 'utf8');
const nav = fs.readFileSync(path.join(__dirname, '../src/components/shell.tsx'), 'utf8');

test('community activity is a read-only Society Admin review', () => {
  assert.match(nav, /\/admin\/community-activity','Community Activity'/);
  assert.match(source, /society\.notices\.manage/);
  assert.match(source, /communityActivityApi\.discussions/);
  assert.match(source, /communityActivityApi\.discussion/);
  assert.match(source, /Read comments/);
  assert.match(source, /Results stay hidden until this poll closes/);
  assert.match(source, /Voting is not open/);
  assert.match(source, /communityActivityApi\.suggestions\(\)/);
  assert.match(source, /communityActivityApi\.polls\(\)/);
  assert.match(source, /communityActivityApi\.proposals\(\)/);
  assert.match(source, /EmptyState title="No discussions"/);
  assert.match(source, /EmptyState title="No suggestions"/);
  assert.match(source, /EmptyState title="No informal polls"/);
  assert.match(source, /EmptyState title="No proposals"/);
  assert.match(source, /ErrorState error=\{discussions\.error\} onRetry=\{discussions\.refresh\}/);
  assert.match(source, /ErrorState error=\{suggestions\.error\} onRetry=\{suggestions\.refresh\}/);
  assert.match(source, /ErrorState error=\{polls\.error\} onRetry=\{polls\.refresh\}/);
  assert.match(source, /ErrorState error=\{proposals\.error\} onRetry=\{proposals\.refresh\}/);
  assert.match(source, /Private disputes are not shown/);
  assert.doesNotMatch(source, /disputeApi|created_by_user_id|my_option_id|method:'POST'|onSubmit|vote\(/);
});
