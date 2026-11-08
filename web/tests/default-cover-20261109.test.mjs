import assert from 'node:assert/strict';
import test from 'node:test';
import { defaultCoverTitle, defaultCoverVariant } from '../lib/default-cover.ts';

test('cover assignment is stable across SSR, routes and Unicode normalization, with all six choices reachable', () => {
  const titles = Array.from({length: 600},(_,i)=>`社会理论文献 ${i}`);
  const buckets = Array(6).fill(0);
  for (const title of titles) { const v = defaultCoverVariant(title); assert.equal(v,defaultCoverVariant(title)); buckets[v]++; }
  assert.ok(buckets.every(n=>n>50 && n<150),String(buckets));
  assert.equal(defaultCoverVariant('é'),defaultCoverVariant('e\u0301'));
  assert.equal(defaultCoverTitle('  规训与惩罚  '),'规训与惩罚');
  assert.equal(defaultCoverTitle(''), '未题名资料');
  const long = 'The Structure of Social Action and Modern Social Theory '.repeat(8);
  assert.ok(defaultCoverTitle(long).length <= 120);
  assert.ok(defaultCoverTitle(long).endsWith('…'));
  assert.equal(defaultCoverTitle('Surveiller et punir'), 'Surveiller et punir');
});
