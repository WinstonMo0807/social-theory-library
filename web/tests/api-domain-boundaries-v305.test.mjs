import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import ts from "typescript";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = (name) => ts.createSourceFile(name, readFileSync(path.join(root, name), "utf8"), ts.ScriptTarget.Latest, true);

test("server-api remains only a compatibility export surface and application consumers use exact domains", () => {
  assert.ok(source("lib/server-api.ts").statements.every(ts.isExportDeclaration));

  function check(directory) {
    for (const entry of readdirSync(path.join(root, directory), { withFileTypes: true })) {
      const name = `${directory}/${entry.name}`;
      if (entry.isDirectory()) {
        if (name !== "lib/api/generated") check(name);
        continue;
      }
      if (!/\.tsx?$/.test(name) || name === "lib/server-api.ts") continue;
      const parsed = source(name);
      const client = parsed.statements.some(node => ts.isExpressionStatement(node)
        && ts.isStringLiteral(node.expression) && node.expression.text === "use client");
      for (const node of parsed.statements) {
        if (!ts.isImportDeclaration(node)) continue;
        assert.ok(!node.moduleSpecifier.text.endsWith("server-api"), `${name} imports the compatibility surface`);
        if (client) assert.ok(!/\.server$|server-request$/.test(node.moduleSpecifier.text), `${name} imports a server-only domain`);
      }
    }
  }
  for (const directory of ["app", "components", "lib"]) check(directory);
});

test("Reader client work adapters and domain presentation types have no server request dependency", () => {
  for (const name of ["components/reader-center.tsx", "components/reader-book-notes.tsx"]) {
    const imports = source(name).statements.filter(ts.isImportDeclaration);
    const adapter = imports.find(node => node.moduleSpecifier.text === "@/lib/public-data-adapters");
    assert.ok(adapter, `${name} must use the pure work adapter`);
    assert.ok(adapter.importClause.namedBindings.elements.some(item => item.propertyName?.text === "adaptApiWork" && item.name.text === "adaptWork"));
    assert.ok(imports.every(node => !/\.server$|server-request$/.test(node.moduleSpecifier.text)), `${name} imports server transport`);
  }
  const pureModules = ["lib/public-data-adapters.ts", "lib/api/public-catalog.ts", ...readdirSync(path.join(root, "lib/api"))
    .filter(name => name.endsWith(".types.ts")).map(name => `lib/api/${name}`)];
  for (const name of pureModules) {
    for (const node of source(name).statements) {
      if (!ts.isImportDeclaration(node)) continue;
      assert.ok(node.importClause.isTypeOnly, `${name} has a runtime import`);
      assert.ok(!/server-api$|\.server$|server-request$/.test(node.moduleSpecifier.text), `${name} references server transport`);
    }
  }
});

test("split catalog requests retain private headers, no-store, encoded IDs and 404 versus service failure behavior", async (t) => {
  const previousEnvironment = Object.fromEntries(["ALLOW_DEMO_FALLBACK", "INTERNAL_API_URL", "INTERNAL_API_TOKEN"]
    .map(key => [key, process.env[key]]));
  t.after(() => {
    for (const [key, value] of Object.entries(previousEnvironment)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  });
  process.env.ALLOW_DEMO_FALLBACK = "false";
  process.env.INTERNAL_API_URL = "http://catalog-test.invalid/api/";
  process.env.INTERNAL_API_TOKEN = "api-domain-test-token";
  const { loadWork, loadWorks } = await import("../lib/api/catalog.server.ts");
  const { ServerApiError } = await import("../lib/api/server-request.ts");
  const previousFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = previousFetch; });
  let request;
  globalThis.fetch = async (url, init) => {
    request = { url, init };
    return new Response(JSON.stringify({ results: [] }), { status: 200 });
  };
  assert.deepEqual(await loadWorks(), []);
  assert.equal(request.url, "http://catalog-test.invalid/api/catalog/works/?ordering=-editions__first_published_at");
  assert.equal(request.init.cache, "no-store");
  assert.equal(request.init.headers["x-forwarded-proto"], "https");
  assert.equal(request.init.headers["x-internal-api-token"], "api-domain-test-token");
  globalThis.fetch = async (url) => {
    request.url = url;
    return new Response("missing", { status: 404 });
  };
  assert.equal(await loadWork("书/目"), null);
  assert.equal(request.url, "http://catalog-test.invalid/api/catalog/works/%E4%B9%A6%2F%E7%9B%AE/");
  globalThis.fetch = async () => new Response("unavailable", { status: 503 });
  await assert.rejects(() => loadWork("existing"), error => error instanceof ServerApiError && error.status === 503);
  globalThis.fetch = async () => { throw new TypeError("network unavailable"); };
  await assert.rejects(() => loadWorks(), /network unavailable/);
});
