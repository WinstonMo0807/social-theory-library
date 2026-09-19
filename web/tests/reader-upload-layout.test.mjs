import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { readStyleSource } from "../scripts/style-source.mjs";

test("reader toolbar allocates the optional printed-page control without overflow", async () => {
  const css = readStyleSource();
  const source = await readFile(new URL("../components/reader-shell.tsx", import.meta.url), "utf8");
  assert.match(source, /className="reader-printed-page"/);
  assert.match(css, /\.page-control\s*\{[\s\S]*grid-template-columns: 32px 46px minmax\(0, 1fr\) 32px/);
  assert.match(css, /\.page-control > button:last-child\s*\{ grid-column: 4; grid-row: 2;/);
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

test("public reader loads private records only after shared session bootstrap", async () => {
  const source = await readFile(new URL("../components/reader-shell.tsx", import.meta.url), "utf8");
  const records = await readFile(new URL("../components/reader/use-reader-records.ts", import.meta.url), "utf8");
  const progress = await readFile(new URL("../components/reader/use-reader-progress.ts", import.meta.url), "utf8");
  assert.match(source, /useSessionBootstrap\(\)/);
  assert.match(source, /readerSession\.status === "authenticated"/);
  assert.match(source, /useReaderRecords\(\{[\s\S]*readerAuthenticated/);
  assert.match(source, /useReaderProgress\(\{[\s\S]*readerAuthenticated/);
  assert.match(progress, /if \(!readerAuthenticated\) return/);
  assert.match(records, /if \(!readerAuthenticated\) \{[\s\S]*setGate\("书签"\)/);
  assert.doesNotMatch(source, /if \(!getServerSessionCredential\(\)\)/);
  assert.doesNotMatch(records, /if \(!getServerSessionCredential\(\)\)/);
});

test("public save buttons wait for one shared authenticated session", async () => {
  const layout = await readFile(new URL("../app/layout.tsx", import.meta.url), "utf8");
  const provider = await readFile(new URL("../components/public-session-provider.tsx", import.meta.url), "utf8");
  const header = await readFile(new URL("../components/site-header.tsx", import.meta.url), "utf8");
  const saveButton = await readFile(new URL("../components/save-work-button.tsx", import.meta.url), "utf8");
  const bootstrap = await readFile(new URL("../lib/use-session-bootstrap.ts", import.meta.url), "utf8");
  assert.match(layout, /<PublicSessionProvider>/);
  assert.match(provider, /useSessionBootstrap\(undefined, isPublicSessionRoute\(pathname\)\)/);
  assert.match(header, /usePublicSession\(\)/);
  assert.doesNotMatch(header, /bootstrapSession|subscribeToSessionChanges/);
  assert.match(saveButton, /if \(session\.status !== "authenticated"\) return/);
  assert.match(saveButton, /\/reading\/saved\/\?work=/);
  assert.match(bootstrap, /if \(!enabled\) return/);
});
