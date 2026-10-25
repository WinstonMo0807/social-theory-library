import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


test("Ask Library reuses cookie-first auth and does not clear sessions on service failures", async () => {
  const source = await readFile(
    new URL("../components/explore-ask-client.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /useSessionBootstrap\(\)/);
  assert.match(source, /getServerSessionCredential\(\)/);
  assert.doesNotMatch(source, /getStoredAccessToken|clearStoredSession|logoutCurrentSession/);
  assert.match(source, /reason\.status === 401[\s\S]*retrySession\(\)/);
  assert.match(source, /reason\.status === 403[\s\S]*setState\("forbidden"\)/);
  assert.match(source, /response\.status === 429/);
  assert.match(source, /登录状态未受影响/);
});


test("Reader and public entity pages use one scoped Ask link contract", async () => {
  const [shared, reader, scholar, theory, topic, explore] = await Promise.all([
    "../components/ask-library-link.tsx",
    "../components/reader-shell.tsx",
    "../components/public/scholar-public-view.tsx",
    "../components/public/knowledge-node-public-view.tsx",
    "../components/public/topic-public-view.tsx",
    "../app/explore/page.tsx",
  ].map((path) => readFile(new URL(path, import.meta.url), "utf8")));

  assert.match(shared, /mode: "ask", context/);
  assert.match(shared, /params\.append\("id", id\)/);
  assert.match(shared, /params\.set\("asset_id", assetId\)/);
  assert.match(reader, /<AskLibraryLink[\s\S]*context="works"[\s\S]*assetId=\{work\.id\}/);
  assert.match(scholar, /context="scholars" ids=\{\[scholar\.id\]\}/);
  assert.match(theory, /context="theories" ids=\{\[node\.id\]\}/);
  assert.match(topic, /context="topics" ids=\{\[topic\.id\]\}/);
  assert.match(explore, /"global", "works", "scholars", "disciplines", "subdisciplines", "theories", "topics", "reading_paths"/);
  assert.match(explore, /asset_id: firstParam\(params\.asset_id\)/);
});


test("Admin settings share a private, versioned model editor", async () => {
  const [settings, source] = await Promise.all([
    "../components/admin-sections.tsx", "../components/admin/ai-runtime-editor.tsx",
  ].map(path => readFile(new URL(path, import.meta.url), "utf8")));
  assert.match(settings, /<AIRuntimeEditor/);
  assert.match(source, /expected_version/);
  assert.match(source, /X-Editor-Owner/);
  assert.match(source, /can_edit_sensitive_aliases/);
  assert.match(source, /type="password"/);
  assert.match(source, /secret:""/);
  assert.doesNotMatch(source, /ai-runtime-profiles\/test/);
  assert.doesNotMatch(source, /sessionStorage\.setItem\([^;]*(?:secret|JSON\.stringify)/);
});


test("Ask UI keeps evidence metadata separate from streamed answer text", async () => {
  const source = await readFile(
    new URL("../components/explore-ask-client.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /streamEvent === "delta"/);
  assert.match(source, /streamEvent === "sources"/);
  assert.match(source, /Array\.isArray\(payload\.evidence\)/);
  assert.match(source, /source\.reader_url \? <Link href=\{source\.reader_url\}>查看原文/);
  assert.match(source, /source\.passage_language/);
  assert.match(source, /馆藏证据不足，未使用模型常识补答/);
});

test("registered readers can configure a personal model connection without browser key persistence", async () => {
  const source = await readFile(
    new URL("../components/explore-ask-client.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /\/reading\/library-assistant\/connection\//);
  assert.match(source, /保存并测试/);
  assert.match(source, /name="reader-ai-key"/);
  assert.match(source, /不会写入 Local Storage/);
  assert.match(source, /个人模型服务/);
});
