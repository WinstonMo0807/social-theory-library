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

test("style extraction stays parseable and unrelated cascade semantics remain unchanged during the 59-reference redesign", () => {
  const source = readStyleSource(globalStylesPath, { exclude: [overlaysPath] });
  // The 3.0.5 monolith-equivalence hash described a formatting-only split.
  // The authorized 3.0.9.1 reference families change these admin surfaces and their shared
  // public previews (cards, topic overview and home). Keep this explicit: all other extracted
  // files, including Reader styles and the base/layout cascade, must match bb81c73 exactly.
  const redesigned=new Set([
    "components/book-card.css", "components/confirm-dialog.css", "components/scholar-card.css",
    "features/admin/collections-v2.css", "features/admin/design-v2.css",
    "features/admin/evidence-curation.css", "features/admin/fixed-page-editor.css",
    "features/admin/knowledge-reference.css", "features/admin/operations-v2.css",
    "features/admin/processing-and-curation.css", "features/admin/processing-reference.css",
    "features/admin/recommendations-design-v2.css", "features/admin/relation-timeline-reference.css",
    "features/admin/site-content-reference.css", "features/admin/site-system-reference.css",
    "features/admin/storage-backups.css", "features/admin/taxonomy-reference.css",
    "features/admin/theory-reference.css", "features/admin/topic-reference.css",
    "features/admin/workspace-v307.css", "features/home/home-v307.css",
    "features/knowledge/detail-pages.css", "knowledge-v307.css", "tokens/design.css",
  ]);
  const whole=styleSemanticSnapshot(source,{resolveTokens:true});
  assert.ok(whole.rules>0 && whole.declarations>0);
  for(const {file} of baseline.sections){
    const after=readFileSync(resolve(webRoot,"styles",file),"utf8");
    postcss.parse(after, {from:file});
    if(redesigned.has(file)) continue;
    const before=execFileSync("git",["show",`bb81c73:web/styles/${file}`],{cwd:webRoot,encoding:"utf8"});
    assert.deepEqual(styleSemanticSnapshot(after),styleSemanticSnapshot(before),file);
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
