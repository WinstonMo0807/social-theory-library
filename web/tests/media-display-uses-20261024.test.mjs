// Deferred acceptance; not run during development.
import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(new URL("../lib/media-usage.ts", import.meta.url), "utf8");
const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const { mediaAllows, publicShareImagePath } = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
const work = "11111111-1111-4111-8111-111111111111", edition = "22222222-2222-4222-8222-222222222222", rendition = "33333333-3333-4333-8333-333333333333";

test("a saved mobile choice is independent and old images do not opt into sharing", () => {
  assert.equal(mediaAllows(undefined, "detail"), true);
  assert.equal(mediaAllows(undefined, "share"), false);
  assert.equal(mediaAllows(["mobile"], "detail"), false);
  assert.equal(mediaAllows(["mobile"], "mobile"), true);
  assert.equal(mediaAllows([], "list"), false);
});

test("sharing preserves the explicit edition while rejecting private or substituted URLs", () => {
  const path = `/api/catalog/works/${work}/cover/?edition_id=${edition}&rendition=${rendition}`;
  assert.equal(publicShareImagePath(path), path);
  assert.equal(publicShareImagePath(`/api/catalog/people/${work}/portrait/?rendition=${rendition}`), `/api/catalog/people/${work}/portrait/?rendition=${rendition}`);
  for (const invalid of [path + `&edition_id=${work}`, path + "&admin=1", path + "#x", path.replace(edition, "invalid"),
    `https://external.invalid${path}`, `/api/catalog/admin/media/renditions/${rendition}/file/`, path.replace(/&rendition=.*/, "")]) {
    assert.equal(publicShareImagePath(invalid), null);
  }
});
