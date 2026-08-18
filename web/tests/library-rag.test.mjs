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
    "../app/scholars/[slug]/page.tsx",
    "../app/theories/nodes/[slug]/page.tsx",
    "../app/topics/[slug]/page.tsx",
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


test("Admin settings expose capability profiles but never a secret value input", async () => {
  const source = await readFile(
    new URL("../components/admin-sections.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /\/reading\/admin\/ai-runtime-profiles\//);
  assert.match(source, /\/reading\/admin\/ai-runtime-profiles\/test\//);
  assert.match(source, /metadata_extraction: "元数据提取"/);
  assert.match(source, /library_qa: "书库问答默认服务（可选）"/);
  assert.match(source, /field_enrichment_optional: "联网补全可选判断"/);
  assert.match(source, /密钥和实际 endpoint 只由服务器环境提供/);
  const section = source.slice(
    source.indexOf('<form className="admin-panel ai-runtime-settings"'),
    source.indexOf('<form className="admin-panel semantic-runtime-settings"'),
  );
  assert.doesNotMatch(section, /<input[^>]*(?:api.?key|secret|credential)/i);
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
