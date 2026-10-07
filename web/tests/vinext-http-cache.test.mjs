import assert from "node:assert/strict";
import { createHash, webcrypto } from "node:crypto";
import { mkdtemp, mkdir, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("HTTP LAN RSC backport is idempotent and server accepts both native and official legacy keys", async () => {
  const temporary = await mkdtemp(join(tmpdir(), "stl-vinext-http-"));
  const installed = new URL("../node_modules/vinext/dist/", import.meta.url);
  const original = '\tconst digest = await globalThis.crypto.subtle.digest("SHA-256", textEncoder.encode(input));';
  const patched = '\tconst subtle = globalThis.crypto?.subtle;\n\tif (!subtle) return fnv1a64(input);\n\tconst digest = await subtle.digest("SHA-256", textEncoder.encode(input));';
  const targetRoot = join(temporary, "node_modules/vinext/dist");
  const cryptoDescriptor = Object.getOwnPropertyDescriptor(globalThis, "crypto");
  const useCrypto = value => Object.defineProperty(globalThis, "crypto", { value, configurable: true });
  try {
    await mkdir(join(temporary, "scripts"), { recursive: true });
    await writeFile(join(temporary, "package.json"), '{"type":"module"}');
    await writeFile(join(temporary, "scripts/patch-vinext-static-paths.mjs"), await readFile(new URL("../scripts/patch-vinext-static-paths.mjs", import.meta.url)));
    for (const file of ["server/static-file-cache.js", "entries/app-rsc-entry.js", "server/app-rsc-cache-busting.js", "server/headers.js", "server/app-rsc-render-mode.js", "utils/hash.js"]) {
      const target = join(targetRoot, file);
      await mkdir(join(target, ".."), { recursive: true });
      let source = await readFile(new URL(file, installed), "utf8");
      if (file === "server/app-rsc-cache-busting.js") source = source.replace(patched, original);
      await writeFile(target, source);
    }
    const execute = () => spawnSync(process.execPath, [join(temporary, "scripts/patch-vinext-static-paths.mjs")], { encoding: "utf8" });
    const first = execute();
    assert.equal(first.status, 0, first.stderr);
    assert.match(first.stdout, /Corrected: RSC cache keys/);
    const path = join(targetRoot, "server/app-rsc-cache-busting.js");
    const after = await readFile(path, "utf8");
    const second = execute();
    assert.equal(second.status, 0, second.stderr);
    assert.match(second.stdout, /Already corrected: RSC cache keys/);
    assert.equal(await readFile(path, "utf8"), after);
    const rsc = await import(pathToFileURL(path).href);
    const { fnv1a64 } = await import(pathToFileURL(join(targetRoot, "utils/hash.js")).href);
    const fields = ["Next-Router-Prefetch", "Next-Router-Segment-Prefetch", "Next-Router-State-Tree", "Next-Url", "X-Vinext-Interception-Context", "X-Vinext-Mounted-Slots", "X-Vinext-Rsc-Render-Mode"];
    const cases = [new Headers(), new Headers({ "Next-Router-Prefetch": "1" }), new Headers({ "Next-Url": "/admin/library?q=%E9%9F%A6%E4%BC%AF", "X-Vinext-Interception-Context": "slot-a", "X-Vinext-Mounted-Slots": "[\"main\"]" }), new Headers({ "X-Vinext-Rsc-Render-Mode": "refresh" })];
    for (const headers of cases) {
      useCrypto(webcrypto);
      const secure = await rsc.computeRscCacheBustingSearchParam(headers);
      const values = fields.map(field => headers.get(field));
      // Invalid/normal render mode is normalized to null by the upstream contract.
      const mode = await import(pathToFileURL(join(targetRoot, "server/app-rsc-render-mode.js")).href);
      const renderMode = mode.parseAppRscRenderMode(values.at(-1));
      values[values.length - 1] = renderMode === "navigation" ? null : renderMode;
      const input = values.every(value => value === null) ? null : values.map(value => value ?? "0").join(",");
      assert.equal(secure, input === null ? "" : createHash("sha256").update(input).digest().subarray(0, 12).toString("base64url"));
      for (const unavailable of [undefined, {}]) {
        useCrypto(unavailable);
        const legacy = await rsc.computeRscCacheBustingSearchParam(headers);
        assert.equal(legacy, input === null ? "" : fnv1a64(input));
        const clientPath = await rsc.createRscRequestUrl("/admin/library?view=editions&q=%E9%9F%A6%E4%BC%AF#books", headers);
        assert.match(clientPath, /^\/admin\/library\.rsc\?view=editions&q=%E9%9F%A6%E4%BC%AF&_rsc/);
        useCrypto(webcrypto);
        assert.equal(await rsc.resolveInvalidRscCacheBustingRequest({ isRscRequest: true, request: new Request(`http://library.test${clientPath}`, { headers }) }), null);
      }
      const secureUrl = new URL("http://library.test/admin/library.rsc?view=editions");
      rsc.setRscCacheBustingSearchParam(secureUrl, secure);
      assert.equal(await rsc.resolveInvalidRscCacheBustingRequest({ isRscRequest: true, request: new Request(secureUrl, { headers }) }), null);
      secureUrl.searchParams.set("_rsc", "invalid-key");
      const redirect = await rsc.resolveInvalidRscCacheBustingRequest({ isRscRequest: true, request: new Request(secureUrl, { headers }) });
      assert.equal(redirect.status, 307);
      assert.equal(new URL(redirect.headers.get("location"), secureUrl).searchParams.get("_rsc"), secure);
    }
    useCrypto({ subtle: { digest() { throw new Error("real digest failure"); } } });
    await assert.rejects(rsc.computeRscCacheBustingSearchParam(cases[1]), /real digest failure/);
    await writeFile(path, after.replace(patched, "changed upstream digest implementation"));
    const drifted = execute();
    assert.notEqual(drifted.status, 0);
    assert.match(drifted.stderr, /Review changed upstream implementation/);
  } finally {
    if (cryptoDescriptor) Object.defineProperty(globalThis, "crypto", cryptoDescriptor);
    else delete globalThis.crypto;
    // Only the test-owned mkdtemp directory; installed/shared dependencies are untouched.
    await rm(temporary, { recursive: true, force: true });
  }
});
