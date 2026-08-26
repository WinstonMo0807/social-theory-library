import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("viewpoint search uses the dedicated EvidenceSpan-backed public contract", async () => {
  const [serverApi, page] = await Promise.all([
    read("../lib/server-api.ts"),
    read("../app/explore/opinions/page.tsx"),
  ]);

  assert.match(serverApi, /export type ViewpointStance/);
  assert.match(serverApi, /\/catalog\/viewpoint-search\//);
  assert.match(serverApi, /evidence_span_validation_required: boolean/);
  assert.match(serverApi, /default_ranking: "semantic_v2_baseline"/);
  assert.match(page, /loadViewpointSearch\(query, filters\)/);
  assert.match(page, /item\.evidence\.text/);
  assert.match(page, /href=\{item\.reader_url\}/);
  assert.match(page, /href=\{item\.pdf_url\}/);
  assert.match(page, /进入 Reader/);
  assert.match(page, /打开 PDF/);
  assert.doesNotMatch(page, /Math\.round\(item\.quality_score/);
});

test("viewpoint UI groups relations and keeps the benchmark-gated baseline visible", async () => {
  const [page, styles] = await Promise.all([
    read("../app/explore/opinions/page.tsx"),
    read("../app/explore/opinions/viewpoint-search.module.css"),
  ]);

  for (const relation of ["direct", "support", "oppose", "qualify", "critique", "extend", "reframe"]) {
    assert.match(page, new RegExp(`key: "${relation}"`));
  }
  assert.match(page, /Semantic V2 基准排序/);
  assert.match(page, /Claim Engine/);
  assert.match(page, /影子评估中/);
  assert.match(page, /语义相近不自动等于支持/);
  assert.doesNotMatch(page, /聊天|发送消息|assistant-message/);
  assert.match(styles, /\.evidenceCard\[data-stance="oppose"\]/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
});

test("viewpoint filters round-trip canonical IDs and bounded public fields in the URL", async () => {
  const [serverApi, page, styles] = await Promise.all([
    read("../lib/server-api.ts"),
    read("../app/explore/opinions/page.tsx"),
    read("../app/explore/opinions/viewpoint-search.module.css"),
  ]);

  for (const parameter of ["relation", "source_type", "scholar", "theory", "topic", "language", "year_min", "year_max", "work"]) {
    assert.match(page, new RegExp(`name=["'{]${parameter}`));
  }
  assert.match(serverApi, /\["relation", filters\.relation\]/);
  assert.match(serverApi, /\["source_type", filters\.sourceType\]/);
  assert.match(serverApi, /\["scholar", filters\.scholar\]/);
  assert.match(serverApi, /parameters\.set\("year_min"/);
  assert.match(serverApi, /parameters\.set\("year_max"/);
  assert.match(serverApi, /filters\.workId/);
  assert.match(serverApi, /type ViewpointFacetOption/);
  assert.match(serverApi, /scholars: ViewpointFacetOption\[\]/);
  assert.match(serverApi, /theories: ViewpointFacetOption\[\]/);
  assert.match(serverApi, /topics: ViewpointFacetOption\[\]/);
  assert.match(styles, /\.filters/);
});
