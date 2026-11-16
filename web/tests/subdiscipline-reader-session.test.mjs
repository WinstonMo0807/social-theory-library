import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import ts from 'typescript';

class ServerApiError extends Error { constructor(status) { super(); this.status = status; } }
function loader(response, cookiePresent = true) {
  const calls = [], exports = {};
  const source = readFileSync(new URL('../lib/api/taxonomy.server.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(code, { exports, URLSearchParams, process: { env: {} }, require(name) {
    if (name === '../public-data-adapters') return { adaptApiWork: value => value };
    if (name === './pagination') return {};
    if (name === 'next/headers') return { cookies: async () => ({ get: () => cookiePresent ? { value: 'synthetic-session' } : undefined }) };
    if (name === './server-request') return { ServerApiError, allowDemoFallback: false,
      serverRequest: async (path, options) => {
        const call = { path, session: Boolean(options?.forwardSession) };
        calls.push(call);
        return response(call, calls.length);
      } };
    throw new Error(name);
  } });
  return { calls, load: exports.loadSubdiscipline, PageError: exports.SubdisciplineWorksPageError };
}

test('core literature uses the viewer session and preserves the requested page', async () => {
  const { load, calls } = loader(call => ({ works: [], core_works: [{ reader_href: call.session ? '/reader/registered' : null }] }));
  const result = await load('族群/认同', 2);
  assert.equal(result.core_works[0].reader_href, '/reader/registered');
  assert.equal(calls[0].session, true);
  assert.equal(calls[0].path, '/catalog/subdisciplines/%E6%97%8F%E7%BE%A4%2F%E8%AE%A4%E5%90%8C/?works_page=2');
  assert.equal(result.readerSessionPending, undefined);
});

test('an expired cookie retains anonymous metadata and requests one post-recovery refresh', async () => {
  const { load, calls } = loader(call => {
    if (call.session) throw new ServerApiError(401);
    return { works: [], core_works: [{ reader_href: null }] };
  });
  const result = await load('ethnicity');
  assert.deepEqual(calls.map(c => c.session), [true, false]);
  assert.equal(result.core_works[0].reader_href, null);
  assert.equal(result.readerSessionPending, true);
});

test('a browser that omitted an expired cookie can refresh metadata after session recovery', async () => {
  const { load, calls } = loader(() => ({ works: [], core_works: [{ reader_href: null }] }), false);
  const result = await load('ethnicity');
  assert.equal(result.readerSessionPending, true);
  assert.equal(calls.length, 1);
});

test('missing pages recheck the entity with the same session; outages still surface', async () => {
  const page = loader(call => {
    if (call.path.includes('?')) throw new ServerApiError(404);
    return { works: [] };
  });
  await assert.rejects(page.load('ethnicity', 99), e => e instanceof page.PageError && e.reason === 'out_of_range');
  assert.deepEqual(page.calls.map(c => c.session), [true, true]);
  const outage = loader(() => { throw new ServerApiError(503); });
  await assert.rejects(outage.load('ethnicity'), e => e.status === 503);
  assert.equal(outage.calls.length, 1);
});
