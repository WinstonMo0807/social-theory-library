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
  assert.match(page, /查看原文并跳转 PDF/);
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
