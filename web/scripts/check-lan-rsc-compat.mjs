import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { lanRscCompat } from './lan-rsc-compat.mjs';

const path = new URL('../node_modules/vinext/dist/server/app-rsc-cache-busting.js', import.meta.url);
const source = await readFile(path, 'utf8');
const adapter = lanRscCompat();
assert.equal(adapter.transform(source, '/unrelated.js'), undefined);
assert.throws(() => adapter.transform('changed', path.pathname), /protocol changed/);
const patched = adapter.transform(source, path.pathname).code.replace(/from "(\.[^"]+)"/g,
  (_, relative) => `from "${new URL(relative, path).href}"`);
const protocol = await import(`data:text/javascript;base64,${Buffer.from(patched).toString('base64')}`);
const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
const headers = new Headers({ 'X-Vinext-Mounted-Slots': '{"main":true}' });
try {
  Object.defineProperty(globalThis, 'crypto', { value: {}, configurable: true });
  const url = await protocol.createRscRequestUrl('/admin/knowledge?page=demo', headers);
  assert.match(url, /_rsc=.+/);
  // Restore the server's secure hashing and confirm it accepts this LAN client.
  Object.defineProperty(globalThis, 'crypto', descriptor);
  assert.equal(await protocol.resolveInvalidRscCacheBustingRequest({
    isRscRequest: true, request: new Request(`http://localhost${url}`, { headers }),
  }), null);
} finally {
  Object.defineProperty(globalThis, 'crypto', descriptor);
}
console.log('LAN RSC navigation uses the existing server-accepted protocol.');
