/* eslint-disable @typescript-eslint/no-require-imports */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../src/features/community/community-activity.tsx'), 'utf8');
const nav = fs.readFileSync(path.join(__dirname, '../src/components/shell.tsx'), 'utf8');

test('community activity is a Society Admin review with no voting or dispute data', () => {
  assert.match(nav, /can\('society\.notices\.manage'\)\?ADMIN_COMMUNITY/);
  for (const section of ['discussions', 'suggestions', 'polls', 'proposals']) {
    assert.match(nav, new RegExp(`'/admin/${section}'`));
    assert.match(fs.readFileSync(path.join(__dirname, `../src/app/admin/${section}/page.tsx`), 'utf8'), new RegExp(`<Protected admin><CommunityActivity only="${section}"/>`));
  }
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

test('Society Admin moderation actions are limited to hiding discussions and deciding proposals', () => {
  const endpoints = fs.readFileSync(path.join(__dirname, '../src/lib/endpoints.ts'), 'utf8');
  assert.match(source, /communityActivityApi\.hideDiscussion\(discussion\.id, reason\)/);
  assert.match(source, /communityActivityApi\.restoreDiscussion\(discussion\.id\)/);
  assert.match(source, /disabled=\{reason\.trim\(\)\.length < 3\}/);
  assert.match(source, /communityActivityApi\.decideProposal\(proposal\.id, decision, note\)/);
  assert.match(source, /proposal\.status !== 'SUBMITTED'/);
  assert.match(endpoints, /\/api\/admin\/community\/discussions\/\$\{pathId\(id\)\}\/hide`,\{method:'POST',body:\{reason\}\}/);
  assert.match(endpoints, /\/api\/admin\/community\/proposals\/\$\{pathId\(id\)\}\/decision`,\{method:'POST',body:\{decision,note\}\}/);
  assert.doesNotMatch(source, /suggestionApi|pollApi|tally:/);
});

test('admin disputes page is Society Admin only and mirrors Flask transitions', () => {
  const page = fs.readFileSync(path.join(__dirname, '../src/features/disputes/admin-disputes.tsx'), 'utf8');
  const route = fs.readFileSync(path.join(__dirname, '../src/app/admin/disputes/page.tsx'), 'utf8');
  assert.match(route, /<Protected admin><AdminDisputes\/>/);
  assert.match(nav, /'\/admin\/disputes','Disputes'/);
  assert.match(page, /permissions\.includes\('society\.notices\.manage'\)/);
  assert.match(page, /dispute\.status === 'SUBMITTED' && <Button.*?move\('IN_REVIEW'\)\}>Start review/);
  assert.match(page, /dispute\.status !== 'RESOLVED' && <Button.*?disabled=\{!response\.trim\(\)\}.*?move\('RESOLVED'\)\}>Mark resolved/);
  assert.match(page, /dispute\.status === 'RESOLVED' && <Button.*?move\('IN_REVIEW'\)\}>Reopen/);
  assert.doesNotMatch(page, /created_by_user_id|disputeApi\./);
});

test('residents see admin decisions and dispute responses', () => {
  const proposal = fs.readFileSync(path.join(__dirname, '../src/features/proposals/proposal-detail.tsx'), 'utf8');
  const dispute = fs.readFileSync(path.join(__dirname, '../src/features/disputes/dispute-detail.tsx'), 'utf8');
  assert.match(proposal, /proposal\.decision_note/);
  assert.match(proposal, /Voting is not open/);
  assert.match(dispute, /dispute\.admin_response/);
  assert.match(dispute, /Visible only to you and the Society Admin/);
});
