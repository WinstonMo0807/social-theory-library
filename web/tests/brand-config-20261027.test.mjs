import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import ts from "typescript";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { defaultSiteConfig } from "../lib/site-config.ts";

const require = createRequire(import.meta.url);
const source = readFileSync(new URL("../components/brand-image.tsx", import.meta.url), "utf8");
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const exports = {};
new Function("require", "exports", code)(name => name === "@/lib/site-config" ? { defaultSiteConfig } : require(name), exports);

test("default PDF artwork stays intact; edited brand wording renders as escaped vector text", () => {
  const render = config => renderToStaticMarkup(createElement(exports.BrandImage, { config, src: "/brand/reference.svg", width: 236, height: 51 }));
  assert.match(render(defaultSiteConfig), /<img[^>]+src="\/brand\/reference.svg"/);
  const changed = render({ ...defaultSiteConfig, site_name: "研究 & 阅读 <测试>", wordmark_lines: ["OPEN", "READING"] });
  assert.match(changed, /<svg/);
  assert.match(changed, /OPEN READING<\/text>/);
  assert.match(changed, /研究 &amp; 阅读 &lt;测试&gt;<\/text>/);
  assert.doesNotMatch(changed, /SOCIAL THEORY LIBRARY<\/text>/);
});
