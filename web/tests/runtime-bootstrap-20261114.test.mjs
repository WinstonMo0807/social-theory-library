import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import ts from 'typescript';
const read=path=>readFileSync(new URL(path,import.meta.url),'utf8');
const code=ts.transpileModule(read('../lib/runtime-api-bootstrap.ts'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
const exports={};new Function('exports',code)(exports);
test('inline bootstrap preserves same-origin, LAN and custom API configuration without exposing script markup',()=>{
 assert.equal(exports.runtimeApiBootstrap(undefined),null);
 for(const apiBase of ['', '/api','http://127.0.0.1:8105/api','https://books.winstonmo.com/api','</script><script>alert(1)</script>','x\u2028y\u2029z']){
  const script=exports.runtimeApiBootstrap(apiBase),scope={window:{}};
  assert.ok(!script.includes('<'));runInNewContext(script,scope);
  assert.equal(scope.window.__SOCIAL_THEORY_LIBRARY_CONFIG__.apiBase,apiBase);
  assert.ok(Object.isFrozen(scope.window.__SOCIAL_THEORY_LIBRARY_CONFIG__));
 }
});
test('container validates the URL before exporting the inline value and preserves the compatibility file',()=>{
 const entry=read('../docker-entrypoint.sh');
 assert.ok(entry.indexOf('exit 1')<entry.indexOf('export STL_BROWSER_API_BASE'));
 assert.match(entry,/export STL_BROWSER_API_BASE="\$api_base"/);
 assert.match(entry,/runtime-config\.js/);
 const layout=read('../app/layout.tsx');assert.match(layout,/runtimeApiBootstrap\(process\.env\.STL_BROWSER_API_BASE\)/);
 assert.match(layout,/runtimeBootstrap === null \? <Script src="\/runtime-config\.js"/);
});
