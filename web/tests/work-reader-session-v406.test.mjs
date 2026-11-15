import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import ts from 'typescript';

test('work detail forwards the viewer session while public catalog loaders stay anonymous', async () => {
  const calls = [];
  const exports = {};
  const source = readFileSync(new URL('../lib/api/catalog.server.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  vm.runInNewContext(code, { exports, require(name) {
    if (name === 'react') return { cache: fn => fn };
    if (name === '../data') return {};
    if (name === '../public-data-adapters') return { adaptApiWork: value => value };
    if (name === './server-request') return { allowDemoFallback: false, serverRequest: async (path, options) => {
      calls.push({ path, session: Boolean(options?.forwardSession) });
      return path.includes('?') ? { results: [] } : { readerHref: options?.forwardSession ? '/reader/registered-file' : undefined };
    } };
    throw new Error(name);
  } });
  assert.equal((await exports.loadWork('书/目', true)).readerHref, '/reader/registered-file');
  assert.equal(calls[0].path, '/catalog/works/%E4%B9%A6%2F%E7%9B%AE/');
  assert.equal((await exports.loadWork('书/目')).readerHref, undefined);
  await exports.loadWorks();
  assert.deepEqual(calls.map(row => row.session), [true, false, false]);
  const page = readFileSync(new URL('../app/works/[slug]/page.tsx', import.meta.url), 'utf8');
  assert.equal(page.match(/loadWork\(slug, true\)/g)?.length, 2);
});

test('expired work sessions retain public metadata without revealing registered files', async () => {
  const calls = [];
  const exports = {};
  class ServerApiError extends Error { constructor(status) { super(); this.status = status; } }
  const source = readFileSync(new URL('../lib/api/catalog.server.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  vm.runInNewContext(code, { exports, require(name) {
    if (name === 'react') return { cache: fn => fn };
    if (name === '../data') return {};
    if (name === '../public-data-adapters') return { adaptApiWork: value => value };
    if (name === './server-request') return { allowDemoFallback: false, ServerApiError,
      serverRequest: async (path, options) => {
        calls.push(Boolean(options?.forwardSession));
        if (path.includes('unavailable')) throw new ServerApiError(503);
        if (options?.forwardSession) throw new ServerApiError(401);
        return { title: 'Public title', readable_asset: null };
      } };
    throw new Error(name);
  } });
  const result = await exports.loadWork('expired', true);
  assert.equal(result.title, 'Public title');
  assert.equal(result.readable_asset, null);
  assert.deepEqual(calls, [true, false]);
  await assert.rejects(exports.loadWork('unavailable', true), error => error.status === 503);
});
