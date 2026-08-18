import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

process.env.ALLOW_DEMO_FALLBACK = "false";

const {
  isSearchContext,
  scopedSearchHref,
  searchPage,
} = await import("../lib/search-context.ts");
const { loadScopedSearch } = await import("../lib/server-api.ts");


test("scoped search URLs preserve explicit context, query, filters and page", () => {
  assert.equal(
    scopedSearchHref("/topics", "topics", {
      q: "国家 与 社会",
      discipline: "sociology",
      page: 2,
    }),
    "/topics?context=topics&q=%E5%9B%BD%E5%AE%B6+%E4%B8%8E+%E7%A4%BE%E4%BC%9A&discipline=sociology&page=2",
  );
  assert.equal(searchPage("3"), 3);
  assert.equal(searchPage("invalid"), 1);
  assert.equal(isSearchContext("global"), true);
  assert.equal(isSearchContext("passages"), false);
});


test("scoped search API failures reject instead of becoming empty results", async (t) => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(
    JSON.stringify({ detail: "temporary failure" }),
    { status: 500, headers: { "Content-Type": "application/json" } },
  );
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  await assert.rejects(
    () => loadScopedSearch("scholars", "布迪厄"),
    /temporary failure|500/,
  );
});


test("major public pages declare their real search context", async () => {
  const [home, explore, scholars, topics, subdisciplines, theories, legacyTheories] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/explore/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/scholars/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/topics/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/subdisciplines/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/theories/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/theory-schools/page.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(home, /name="context" value="global"/);
  assert.match(explore, /name="context" value="global"/);
  assert.match(scholars, /name="context" value="scholars"/);
  assert.match(topics, /name="context" value="topics"/);
  assert.match(subdisciplines, /name="context" value="subdisciplines"/);
  assert.match(theories, /loadScopedSearch\("theories"/);
  assert.match(legacyTheories, /name="context" value="theories"/);
  assert.doesNotMatch(legacyTheories, /搜索理论、学者、概念或馆藏文献/);
});


test("subdiscipline and scholar directories no longer filter only the current page in memory", async () => {
  const [subdisciplines, scholarsAdmin] = await Promise.all([
    readFile(new URL("../app/subdisciplines/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/admin-sections.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(subdisciplines, /loadSubdisciplinePage/);
  assert.doesNotMatch(subdisciplines, /items\.filter/);
  assert.match(scholarsAdmin, /catalog\/admin\/scholars\/.*search=/s);
  assert.doesNotMatch(scholarsAdmin, /resource\.data\?\.results\.filter\(\(scholar\)/);
});
