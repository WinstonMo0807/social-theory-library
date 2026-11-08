import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
import test from "node:test";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const require = createRequire(import.meta.url);
const root = fileURLToPath(new URL("../", import.meta.url));
const css = new Proxy({}, { get: (_, name) => name });
let pathname = "/", liveActionRenders = 0;
const detailCalls = [];
function load(relative, overrides = {}) {
  const source = readFileSync(path.join(root, relative), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  const exports = {};
  new Function("require", "exports", code)(name => {
    if (Object.hasOwn(overrides, name)) return overrides[name];
    if (name.endsWith(".css")) return { __esModule: true, default: css };
    if (name === "next/navigation") return { usePathname: () => pathname, useSearchParams: () => new URLSearchParams() };
    return require(name);
  }, exports);
  return exports;
}
const { RouteTransition } = load("components/route-transition.tsx");
const { KnowledgeNodePublicView } = load("components/public/knowledge-node-public-view.tsx", {
  "./theory-detail-public-view": { TheoryDetailPublicView: props => { detailCalls.push(props); return React.createElement("article", { "data-shared-detail": props.node.id }, props.actions); } },
  "./knowledge-node-actions": { KnowledgeNodeActions: () => { liveActionRenders++; return React.createElement("button", null, "live"); } },
});

function routes(directory = path.join(root, "app")) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => entry.isDirectory()
    ? routes(path.join(directory, entry.name))
    : entry.name === "page.tsx" ? ["/" + path.relative(path.join(root, "app"), directory).split(path.sep).join("/")] : []);
}
test("every registered page, including new secondary routes, inherits STL 4 presentation", () => {
  const registered = routes();
  assert.ok(registered.length >= 150);
  for (const route of [...registered, "/theories/nodes/new-entry/evidence", "/future-secondary-page"]) {
    pathname = route.replace(/\[[^\]]+\]/g, "record");
    const html = renderToStaticMarkup(React.createElement(RouteTransition, null, "content"));
    assert.match(html, /data-ui-scope="stl4"/, route);
    assert.doesNotMatch(html, /editorial-v2|explore-frozen/, route);
  }
});

test("protected previews render the same detail data without mounting live account actions", () => {
  const node = { id: "test-node", slug: "test-node" }, timeline = [{ id: "event" }], allPaths = [{ id: "path" }];
  for (const section of ["overview", "concepts", "evidence", "works", "relations", "propositions", "paths"]) {
    liveActionRenders = 0;
    const props = { node, timeline, allPaths, section, footer: "footer", pagination: "pagination" };
    const preview = renderToStaticMarkup(React.createElement(KnowledgeNodePublicView, { ...props, preview: true }));
    const captured = detailCalls.at(-1);
    assert.equal(liveActionRenders, 0);
    assert.equal(captured.node, node); assert.equal(captured.timeline, timeline); assert.equal(captured.paths, allPaths);
    assert.equal(captured.section, section); assert.equal(captured.pagination, "pagination");
    assert.equal((preview.match(/disabled=""/g) || []).length, 3);
    assert.match(preview, /data-shared-detail="test-node"/);
    const published = renderToStaticMarkup(React.createElement(KnowledgeNodePublicView, props));
    assert.equal(liveActionRenders, 1); assert.match(published, /data-shared-detail="test-node"/);
  }
});

const { TheoryBanner } = load("components/theory-system-ui.tsx", {
  "next/link": { __esModule: true, default: ({ children, ...props }) => React.createElement("a", props, children) },
  "./media-placement": { MediaPlacement: ({ uses, fallback, children }) => uses?.length === 0 ? fallback : children },
  "./responsive-media-image": { ResponsiveMediaImage: ({ src, alt }) => React.createElement("img", { src, alt }) },
  "@/components/collection-link": { CollectionLink: () => null },
});
test("missing and non-rendition artwork display correctly without the obsolete geometry", () => {
  const render = props => renderToStaticMarkup(React.createElement(TheoryBanner, props));
  assert.match(render({}), /generated-20261030\/reading.webp/);
  const supplied = render({ image: "/owned-photo.jpg" });
  assert.match(supplied, /<img[^>]+src="\/owned-photo.jpg"/);
  assert.doesNotMatch(supplied, /architectural-image|arch-plane/);
  const restricted = render({ image: "/owned-photo.jpg", media: { display_uses: [], renditions: [] }, fallbackImage: "/decoration.webp" });
  assert.match(restricted, /decoration.webp/); assert.doesNotMatch(restricted, /owned-photo.jpg/);
});

const { PreviewViewport } = load("components/admin/curation/fixed-page-editor.tsx");
test("embedded editing preview receives the public presentation inside its isolated document", () => {
  const html = renderToStaticMarkup(React.createElement(PreviewViewport, null, "preview"));
  const srcDoc = html.match(/srcDoc="([^"]+)"/)?.[1];
  assert.ok(srcDoc);
  assert.match(srcDoc, /&lt;main id=&quot;main-content&quot;&gt;/);
  assert.match(srcDoc, /data-ui-scope=&quot;stl4&quot;/);
  assert.match(srcDoc, /data-type-mode=&quot;expressive&quot;/);
  assert.doesNotMatch(srcDoc, /editorial-v2|explore-frozen/);
});
