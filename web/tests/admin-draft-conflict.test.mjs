import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { DraftConflict } from "../components/admin/curation/draft-conflict.tsx";

test("reading a conflict comparison inside an editor form cannot submit that form", () => {
  const html = renderToStaticMarkup(React.createElement("form", { action: "/explicit-save" },
    React.createElement(DraftConflict, {
      endpoint: "/compare-only",
      local: { edit_version: "local" },
      onUseRemote() {},
      onKeepLocal() {},
    })));
  const buttons = [...html.matchAll(/<button\b([^>]*)>/g)];
  assert.equal(buttons.length, 1);
  assert.ok(html.includes("读取最新内容并比较"));
  assert.match(buttons[0][1], /\btype="button"/, "The browser must not treat the comparison control as a submit button");
});
