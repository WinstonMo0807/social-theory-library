import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

// Execute the actual server loaders with a request recorder. An anonymous
// request here used to hide registered-reader sources despite a valid session.
function loader(path, dependencies = {}) {
  const calls = [];
  const exports = {};
  const source = readFileSync(new URL(path, import.meta.url), "utf8");
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  vm.runInNewContext(code, {
    exports, URLSearchParams,
    require(name) {
      if (name === "react") return { cache: fn => fn };
      if (name.endsWith("server-request")) return {
        serverRequest: async (path, options) => {
          calls.push({ path, session: Boolean(options?.forwardSession) });
          return { id: "node-id", public_detail: {}, items: [] };
        },
        ServerApiError: class extends Error {},
      };
      if (name === "react/jsx-runtime") return { jsx: (...args) => args };
      if (name in dependencies) return dependencies[name];
      throw new Error(`Unexpected dependency: ${name}`);
    },
  });
  return { exports, calls };
}

test("theory and both attached source requests preserve the viewer session", async () => {
  const { exports, calls } = loader("../lib/api/knowledge.server.ts", {
    "./graph.server": {}, "./pagination": {},
  });
  await exports.loadKnowledgeNode("theory");
  assert.equal(calls.length, 3);
  assert.ok(calls.every(call => call.session));
});

test("reading path detail and directory preserve the viewer session", async () => {
  const { exports, calls } = loader("../lib/api/reading-paths.server.ts", {
    "./reading-paths.types": { readingPathFilters: () => ({}) },
  });
  await exports.loadPublicReadingPath("path");
  await exports.loadPublicReadingPaths({});
  assert.equal(calls.length, 2);
  assert.ok(calls.every(call => call.session));
});

test("topic sources preserve the viewer session", async () => {
  const { exports, calls } = loader("../lib/api/topics.server.ts", {
    "./topics.params": { topicQuery: () => new URLSearchParams() },
  });
  await exports.loadTopic("topic");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].session, true);
});

test("published placement sources preserve the viewer session", async () => {
  const { exports, calls } = loader("../components/public/published-placements.tsx", {
    "./placement-list": { PlacementList: () => null },
  });
  await exports.PublishedPlacements({ type: "topic", id: "topic-id" });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].session, true);
});
