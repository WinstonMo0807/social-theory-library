import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import ts from 'typescript';

function mount() {
  let status = 'loading';
  let refreshes = 0;
  const ref = { current: false };
  const exports = {};
  const router = { refresh() { refreshes += 1; } };
  const source = readFileSync(new URL('../components/work-reader-session-refresh.tsx', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  vm.runInNewContext(code, { exports, require(name) {
    if (name === 'react') return { useEffect: fn => fn(), useRef: () => ref };
    if (name === 'next/navigation') return { useRouter: () => router };
    if (name === './public-session-provider') return { usePublicSession: () => ({ state: { status } }) };
    throw new Error(name);
  } });
  return (nextStatus, loginRequired = true) => {
    status = nextStatus;
    exports.WorkReaderSessionRefresh({ loginRequired });
    return refreshes;
  };
}

test('recovered access refreshes stale work data once, without a retry loop', () => {
  const render = mount();
  assert.equal(render('loading'), 0);
  assert.equal(render('unauthenticated'), 0);
  assert.equal(render('temporary_error'), 0);
  assert.equal(render('authenticated'), 1);
  // Even if the server still withholds the asset, do not keep refreshing.
  assert.equal(render('authenticated'), 1);
  assert.equal(render('authenticated', false), 1);
});

test('a readable or metadata-only edition does not trigger another server request', () => {
  const render = mount();
  assert.equal(render('authenticated', false), 0);
});
