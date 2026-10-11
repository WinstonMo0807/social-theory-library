import assert from 'node:assert/strict';
import test from 'node:test';
import { publicUsageScope } from '../lib/public-usage-scope.ts';

test('public page analytics sends a category without the address or private identifiers', () => {
  assert.equal(publicUsageScope('/'), 'home');
  for (const [path, category] of [
    ['/works/holding-slug', 'works'], ['/reader/00000000-0000-4000-a000-000000000001', 'reader'],
    ['/explore/original', 'explore'], ['/scholars/person/works', 'scholars'],
    ['/theories/reading-paths/example', 'theories'], ['/theory-schools/graph', 'theory-schools'],
    ['/subdisciplines/example', 'subdisciplines'], ['/topics/example', 'topics'],
    ['/recommendations/example', 'recommendations'], ['/concepts/example', 'concepts'], ['/about', 'about'],
  ]) assert.equal(publicUsageScope(path), category);
  for (const path of ['/admin/system', '/admin/preview/works/private', '/account', '/account/notes/private', '/login', '/register', '/reset-password', '/unknown', 'https://private.invalid']) {
    assert.equal(publicUsageScope(path), null);
  }
});
