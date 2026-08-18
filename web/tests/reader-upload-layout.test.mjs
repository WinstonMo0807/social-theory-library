import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("reader toolbar allocates the optional printed-page control without overflow", async () => {
  const css = await readFile(new URL("../app/globals.css", import.meta.url), "utf8");
  const source = await readFile(new URL("../components/reader-shell.tsx", import.meta.url), "utf8");
  assert.match(source, /className="reader-printed-page"/);
  assert.match(css, /\.page-control\s*\{[\s\S]*grid-template-columns: 24px 40px minmax\(42px, 1fr\) 38px minmax\(0, 1fr\) 24px/);
  const statusBlock = css.slice(css.indexOf(".reader-processing-status {"), css.indexOf(".reader-processing-status strong"));
  assert.match(statusBlock, /position: relative/);
  assert.doesNotMatch(statusBlock, /position: sticky/);
});

test("upload drop zone supports keyboard selection and drag depth", async () => {
  const source = await readFile(new URL("../components/admin-upload.tsx", import.meta.url), "utf8");
  assert.match(source, /dragDepth/);
  assert.match(source, /onDragEnter/);
  assert.match(source, /onDrop/);
  assert.match(source, /event\.key !== "Enter"/);
  assert.match(source, /event\.key !== " "/);
});
