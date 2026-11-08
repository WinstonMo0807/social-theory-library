import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

// Execute the real handler with a small browser adapter, without loading PDF/private state.
const source = await readFile(new URL("../components/reader-shell.tsx", import.meta.url), "utf8");
const handler = source.match(/async function toggleFullscreen\(\) \{[\s\S]*?\n  \}/)?.[0];
assert.ok(handler, "reader fullscreen handler exists");
const makeHandler = new Function("fullscreen", "shellRef", "document", "setFullscreen", "setCopyStatus", "setCopyStatusState", `return (${handler});`);

test("fullscreen preserves a usable reader when native entry is missing or rejected", async () => {
  for (const requestFullscreen of [undefined, async () => {}, async () => { throw new Error("not allowed"); }]) {
    let focused = false;
    const enter = makeHandler(false, { current: { requestFullscreen } }, {}, value => { focused = value; }, assert.fail, assert.fail);
    await enter();
    assert.equal(focused, true);
  }
});

test("exit restores the page, and a failed native exit keeps an actionable state", async () => {
  const shell = {};
  for (const native of [false, true]) {
    let focused = true, exited = false;
    const leave = makeHandler(true, { current: shell }, { fullscreenElement: native ? shell : null, exitFullscreen: async () => { exited = true; } }, value => { focused = value; }, assert.fail, assert.fail);
    await leave();
    assert.equal(focused, false);
    assert.equal(exited, native);
  }
  let focused = true, notice = "", status = "";
  const leave = makeHandler(true, { current: shell }, { fullscreenElement: shell, exitFullscreen: async () => { throw new Error("blocked"); } }, value => { focused = value; }, value => { notice = value; }, value => { status = value; });
  await leave();
  assert.equal(focused, true);
  assert.match(notice, /Esc/);
  assert.equal(status, "error");
});
