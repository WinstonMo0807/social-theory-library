import assert from "node:assert/strict";
import { test } from "node:test";
import { lexicalSearch, emptyFilters } from "../lib/policy-demo/search";
import { searchPolicies } from "../lib/policy-demo/search.server";

test("policy evidence stays in the requested scope and never fills missing evidence", async () => {
  const first = lexicalSearch("平台劳动者的权益", "", emptyFilters);
  assert(first.hits.length > 0);
  const local = lexicalSearch("只看上海的规定", first.context, emptyFilters);
  assert(local.hits.length > 0);
  assert(local.hits.every(hit => hit.policy.region === "上海"));
  const expanded = lexicalSearch("比较中央和地方的政策责任", local.context, local.filters);
  assert.equal(expanded.filters.region, "全部地区");
  assert.match(expanded.context, /平台劳动者/);
  assert.equal(lexicalSearch("恒星核聚变", "", emptyFilters).hits.length, 0);
  assert.equal(lexicalSearch("平台劳动", "", { ...emptyFilters, from: "2030-01-01" }).hits.length, 0);
  assert.equal(lexicalSearch("人社部发〔2021〕56号", "", emptyFilters).hits[0].policy.id, "mohrss-2021-56");
  await assert.rejects(searchPolicies({ query: "政策", filters: { from: "2026-01-01", to: "2021-01-01" } }));
});
