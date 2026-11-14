import assert from 'node:assert/strict';
import {readdir,readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {brotliDecompressSync,gunzipSync} from 'node:zlib';
const client=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../dist/client');
const serverManifest=JSON.parse(await readFile(path.join(client,'../server/.vite/manifest.json'),'utf8'));
const main=[...new Set(Object.values(serverManifest).filter(entry=>entry.isEntry).flatMap(entry=>entry.css??[]))];
assert.equal(main.length,1,'Expected one shared stylesheet; review the budget after a bundler change.');
const css=await readFile(path.join(client,main[0])),compressed=await readFile(path.join(client,main[0]+'.br'));
assert.ok(css.length<=1_270_000,`Shared CSS grew to ${css.length} bytes; check route ownership.`);
assert.ok(compressed.length<=160_000,`Shared Brotli CSS grew to ${compressed.length} bytes.`);
let verified=0;
async function verify(directory){
 for(const entry of await readdir(directory,{withFileTypes:true})){
  const file=path.join(directory,entry.name);
  if(entry.isDirectory()){await verify(file);continue;}
  if(!/\.(br|gz)$/.test(file))continue;
  assert.ok(!/runtime-config\.js\.(br|gz)$/.test(file),'Runtime config must never use a stale compressed variant.');
  const encoded=await readFile(file),original=await readFile(file.replace(/\.(br|gz)$/,''));
  assert.deepEqual(file.endsWith('.br')?brotliDecompressSync(encoded):gunzipSync(encoded),original,file);
  verified++;
 }
}
await verify(client);
console.log(JSON.stringify({sharedCss:css.length,brotliCss:compressed.length,verifiedVariants:verified,budgets:'passed'}));
