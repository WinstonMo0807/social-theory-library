import assert from "node:assert/strict";
import test from "node:test";
import { projectionStatusText } from "../lib/projection-status.ts";

test("diagnostics preserve projection failures and in-progress states instead of treating lag as waiting", () => {
  const row = { type: "query_lexicon", label: "QueryLexicon", status: "current", lag: 0, last_error_code: "" };
  assert.equal(projectionStatusText(row), "检索用语：已更新");
  assert.equal(projectionStatusText({ ...row, lag: 2 }), "检索用语：等待更新");
  assert.equal(projectionStatusText({ ...row, status: "failed", lag: 2 }), "检索用语：更新失败");
  assert.equal(projectionStatusText({ ...row, status: "projecting", lag: 2 }), "检索用语：更新中");
  assert.equal(projectionStatusText({ ...row, status: "waiting_for_capability", lag: 2 }), "检索用语：等待可用执行服务");
  assert.equal(projectionStatusText({ ...row, last_error_code: "provider_error" }), "检索用语：更新失败");
  assert.equal(projectionStatusText({ ...row, status: "unrecognized" }), "检索用语：待核实");
  assert.equal(projectionStatusText({ ...row, status: "not_materialized" }), "检索用语：尚未建立");
  assert.equal(projectionStatusText({ ...row, type: "knowledge_graph", label: "知识关系" }), "知识关系：已更新");
});
