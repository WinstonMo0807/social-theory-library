import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("public Work adapts CuratedClaim envelopes without exposing DerivedClaim", async () => {
  const [data, serverApi, adapters] = await Promise.all([
    readFile(new URL("../lib/data.ts", import.meta.url), "utf8"),
    readFile(new URL("../lib/server-api.ts", import.meta.url), "utf8"),
    readFile(new URL("../lib/public-data-adapters.ts", import.meta.url), "utf8"),
  ]);

  assert.match(data, /export type EvidenceEnvelope/);
  assert.match(data, /reader_url: string/);
  assert.match(data, /pdf_url: string/);
  assert.match(data, /core_viewpoint: CuratedWorkClaim\[\]/);
  assert.match(serverApi, /curated_claims\?:/);
  assert.match(adapters, /curatedClaims: value\.curated_claims/);
  assert.doesNotMatch(serverApi, /derived_claims/);
});

test("Work renders only non-empty curated groups and links evidence to its Reader page", async () => {
  const [view, styles] = await Promise.all([
    readFile(new URL("../components/work-detail-view.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/editorial-v2.css", import.meta.url), "utf8"),
  ]);

  assert.match(view, /title: "核心观点"/);
  assert.match(view, /title: "主要批评"/);
  assert.match(view, /title: "主要回应"/);
  assert.match(view, /group\.claims\.length \? \(/);
  assert.match(view, /<summary>查看依据/);
  assert.match(view, /href=\{evidence\.reader_url\}/);
  assert.match(view, /预览中不打开公开 Reader/);
  assert.match(styles, /\.work-curated-claim-list/);
  assert.match(styles, /var\(--stl2-paper-strong\)/);
  assert.match(styles, /var\(--stl2-line\)/);
});
