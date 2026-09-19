import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import test from "node:test";
import postcss from "postcss";
import { globalStylesPath, readStyleSource, styleSemanticSnapshot } from "../scripts/style-source.mjs";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const baseline = JSON.parse(readFileSync(new URL("./fixtures/global-styles-baseline.json", import.meta.url), "utf8"));
const overlaysPath = resolve(webRoot, "styles/components/overlays.css");

test("global styles are explicit, responsibility-named imports in the original cascade order", () => {
  const root = postcss.parse(readFileSync(globalStylesPath, "utf8"));
  const nodes = root.nodes.filter((node) => node.type !== "comment");
  assert.ok(nodes.every((node) => node.type === "atrule" && node.name === "import"));
  assert.deepEqual(nodes.map((node) => node.params), [
    '"tailwindcss"',
    '"../styles/tokens/design.css"',
    ...baseline.sections.map(({ file }) => `"../styles/${file}"`),
    '"../styles/components/overlays.css"',
  ]);
  for (const group of ["tokens", "base", "layout", "components", "features"]) {
    assert.ok(baseline.sections.some(({ file }) => file.startsWith(`${group}/`)), group);
  }
  for (const { file } of baseline.sections) {
    assert.doesNotMatch(file, /legacy|patch|chunk|part-\d/i);
    const source = readFileSync(resolve(webRoot, "styles", file), "utf8");
    assert.ok(source.split("\n").length < 1000, `${file} must remain a bounded responsibility`);
  }
});

test("style extraction stays parseable and unrelated cascade semantics remain unchanged during authorized layout repairs", () => {
  const source = readStyleSource(globalStylesPath, { exclude: [overlaysPath] });
  // The 3.0.5 monolith-equivalence hash described a formatting-only split.
  // 3.0.6 intentionally fixes these actual reader, detail and admin layouts. All other extracted
  // files must still match their pre-repair semantics, not a refreshed hash.
  // Admin sidebar scrolling is verified with all groups expanded and every
  // control keyboard-focused in admin-usability-v306.spec.ts at five widths.
  const repaired=new Set(["layout/admin-shell.css","features/admin/theory-system.css","features/knowledge/detail-pages.css","features/knowledge/theory-system.css","features/reader/chrome.css","features/reader/document.css","features/reader/responsive.css","features/reader/selection-and-records.css"]);
  const whole=styleSemanticSnapshot(source,{resolveTokens:true});
  assert.ok(whole.rules>0 && whole.declarations>0);
  for(const {file} of baseline.sections){
    const before=execFileSync("git",["show",`aa97727:web/styles/${file}`],{cwd:webRoot,encoding:"utf8"});
    const after=readFileSync(resolve(webRoot,"styles",file),"utf8");
    if(file === "features/admin/relation-preview-and-publication.css") {
      // A31 real-browser long-content geometry now covers the timeline preview.
      // Only its layout and the two relation child-sizing rules may change;
      // publication/processing rules sharing this file still match the baseline.
      const unaffected = (css) => {
        const root = postcss.parse(css);
        root.walkRules((rule) => {
          if (rule.selector.includes(".timeline-draft-preview") || rule.selector === ".admin-relation-preview-body > *,\n.relation-preview-spokes > div > *") rule.remove();
        });
        root.walkAtRules((rule) => { if (rule.nodes && !rule.nodes.length) rule.remove(); });
        return styleSemanticSnapshot(root.toString());
      };
      assert.deepEqual(unaffected(after), unaffected(before), file);
      continue;
    }
    if(!repaired.has(file)) assert.deepEqual(styleSemanticSnapshot(after),styleSemanticSnapshot(before),file);
  }
});

test("shared tokens cover all design families and are consumed by existing foundations", () => {
  const tokens = readFileSync(resolve(webRoot, "styles/tokens/design.css"), "utf8");
  for (const group of ["typography", "spacing", "container", "surface", "ink", "border", "accent", "radius", "shadow", "motion", "z-index"]) {
    assert.ok(tokens.includes(`/* ${group} */`), group);
  }
  const foundation = baseline.sections.filter(({ file }) => /^(tokens|base|layout|components)\//.test(file))
    .map(({ file }) => readFileSync(resolve(webRoot, "styles", file), "utf8")).join("\n");
  assert.ok((foundation.match(/var\(--stl-/g) ?? []).length >= baseline.tokenSubstitutions);
  assert.match(foundation, /--paper: var\(--stl-surface-paper\)/);
  assert.match(foundation, /--admin-control-height: var\(--stl-control-height\)/);
});

test("new overlay foundations are scoped and keep closed native dialogs hidden", () => {
  const source = readFileSync(overlaysPath, "utf8");
  const root = postcss.parse(source);
  root.walkRules((rule) => assert.ok(rule.selector.startsWith(".ui-"), rule.selector));
  assert.match(source, /\.ui-drawer:not\(\[open\]\)\s*\{\s*display: none/);
  assert.match(source, /\.ui-tooltip-content\[hidden\]\s*\{\s*display: none/);
  assert.match(source, /\.ui-drawer\.site-menu-layer::backdrop\s*\{\s*background: transparent/);
});
