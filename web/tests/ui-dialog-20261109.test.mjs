import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import ts from "typescript";
import { confirmAction, confirmLinkNavigation, getDialogRequest, requestReason, settleDialog, showNotice, subscribeDialog } from "../lib/ui-dialog.ts";

test("confirmation waits, cancellation does not write, and repeat clicks cannot queue writes", async () => {
  const previousDocument = globalThis.document, previousWindow = globalThis.window;
  const opener = { isConnected: true };
  globalThis.document = { activeElement: opener };
  globalThis.window = { location: { href: "https://library.test/editor" } };
  const unsubscribe = subscribeDialog(() => {});
  try {
    let writes = 0;
    const perform = async () => { if (await confirmAction("确认关联？")) writes++; };
    const first = perform();
    assert.equal(writes, 0);
    await perform();
    assert.equal(writes, 0);
    settleDialog(false); await first;
    assert.equal(writes, 0);
    const second = perform();
    settleDialog(true); await second;
    assert.equal(writes, 1);
    const obsolete = perform();
    opener.isConnected = false;
    settleDialog(true); await obsolete;
    assert.equal(writes, 1);
    opener.isConnected = true;
    const leftPage = perform();
    window.location.href = "https://library.test/other";
    settleDialog(true); await leftPage;
    assert.equal(writes, 1);
    const reason = requestReason("请填写恢复原因");
    assert.equal(getDialogRequest().kind, "reason");
    settleDialog("核对原版本后恢复");
    assert.equal(await reason, "核对原版本后恢复");
    const cancelledReason = requestReason("请填写恢复原因");
    settleDialog(); assert.equal(await cancelledReason, null);
    const notice = showNotice("先核对原请求");
    assert.equal(getDialogRequest().kind, "notice");
    settleDialog(true); await notice;
  } finally {
    settleDialog(); unsubscribe();
    globalThis.document = previousDocument; globalThis.window = previousWindow;
  }
  assert.equal(await confirmAction("没有挂载弹窗时不能批准操作"), false);
});

test("navigation is cancelled synchronously and resumes only after approval", async () => {
  let prevented = false, stopped = false, decide, destination;
  const event = { preventDefault() { prevented = true; }, stopPropagation() { stopped = true; } };
  const guard = () => new Promise(resolve => { decide = resolve; });
  const pending = confirmLinkNavigation(event, { href: "/home" }, guard, href => { destination = href; });
  assert.equal(prevented, true); assert.equal(stopped, true); assert.equal(destination, undefined);
  decide(false); await pending; assert.equal(destination, undefined);
  const approved = confirmLinkNavigation(event, { href: "/home" }, guard, href => { destination = href; });
  decide(true); await approved; assert.equal(destination, "/home");
});

test("application source has no browser alert, confirm or prompt calls", () => {
  const failures = [];
  function scan(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const file = join(dir, entry.name);
      if (entry.isDirectory()) { scan(file); continue; }
      if (!/\.[jt]sx?$/.test(file)) continue;
      const source = ts.createSourceFile(file, readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true);
      function visit(node) {
        if (ts.isCallExpression(node)) {
          const target = node.expression;
          let bare = ts.isIdentifier(target) && /^(alert|confirm|prompt)$/.test(target.text);
          if (bare) {
            const program = ts.createProgram([file], { noResolve: true, jsx: ts.JsxEmit.Preserve });
            const checked = program.getSourceFile(file);
            const checker = program.getTypeChecker();
            function find(node) {
              if (ts.isIdentifier(node) && node.getStart(checked) === target.getStart(source)) {
                const symbol = checker.getSymbolAtLocation(node);
                if (symbol?.declarations?.some(declaration => !declaration.getSourceFile().isDeclarationFile)) bare = false;
              }
              ts.forEachChild(node, find);
            }
            find(checked);
          }
          const qualified = ts.isPropertyAccessExpression(target) && /^(window|globalThis)$/.test(target.expression.getText(source)) && /^(alert|confirm|prompt)$/.test(target.name.text);
          if (bare || qualified) failures.push(`${file}:${source.getLineAndCharacterOfPosition(node.pos).line + 1}`);
        }
        ts.forEachChild(node, visit);
      }
      visit(source);
    }
  }
  for (const dir of ["app", "components", "lib"]) scan(dir);
  assert.deepEqual(failures, []);
});
