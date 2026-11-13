import test from 'node:test';
import assert from 'node:assert/strict';
import { defaultScholarPortraitVariant } from '../lib/default-scholar-portrait.ts';

test('regular, curated, encoded and trailing-slash scholar URLs keep the same background', () => {
  for (const slug of ['max-weber', '庄孔韶', 'Émile-Durkheim', '名含%']) {
    const expected = defaultScholarPortraitVariant(slug);
    for (const identity of [`/scholars/${slug}`, `/scholars/${encodeURIComponent(slug)}/`, `/scholars/${slug}?from=home#portrait`]) {
      assert.equal(defaultScholarPortraitVariant(identity), expected);
    }
    assert.equal(defaultScholarPortraitVariant(slug.normalize('NFD')), expected);
  }
});

test('all four approved backgrounds are used and assignment is independent of rendering order', () => {
  const names = Array.from({length: 200}, (_, i) => `scholar-${i}`);
  const first = new Map(names.map(name => [name, defaultScholarPortraitVariant(name)]));
  assert.deepEqual([...new Set(first.values())].sort(), [0, 1, 2, 3]);
  for (const name of names.toReversed()) assert.equal(defaultScholarPortraitVariant(name), first.get(name));
});
