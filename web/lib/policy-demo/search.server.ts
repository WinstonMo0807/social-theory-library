import { candidateHits, lexicalSearch, type Filters, type SearchResult } from "./search";

/** Borrow STL's existing /rerank model service, with a separate public policy corpus. */
export async function searchPolicies(input: unknown): Promise<SearchResult> {
  if (!input || typeof input !== "object") throw new Error("请求格式无效。");
  const body = input as Record<string, unknown>;
  if (typeof body.query !== "string" || body.query.trim().length < 2 || body.query.length > 500) throw new Error("请输入2—500字的问题。");
  const raw = body.filters as Partial<Filters> | undefined;
  const filters: Filters = { region: raw?.region || "全部地区", kind: raw?.kind || "全部类型", from: raw?.from || "", to: raw?.to || "" };
  if (!["全部地区", "全国", "上海", "绍兴", "浙江"].includes(filters.region)
    || !["全部类型", "法律", "部门规章", "行政规范性文件"].includes(filters.kind)
    || [filters.from, filters.to].some(date => typeof date !== "string" || date && !/^\d{4}-\d{2}-\d{2}$/.test(date))
    || filters.from && filters.to && filters.from > filters.to) throw new Error("请检查地区、文件类型和日期范围。");
  const result = lexicalSearch(body.query.trim(), typeof body.previous === "string" ? body.previous.slice(0, 500) : "", filters);
  const endpoint = process.env.POLICY_DEMO_INFERENCE_URL;
  if (!endpoint) return { ...result, notice: "语义服务未接入；当前结果来自样本关键词与同义词检索。" };
  const url = new URL(endpoint);
  if (!(["127.0.0.1", "localhost", "discovery-inference"].includes(url.hostname)) || url.protocol !== "http:" || url.username || url.password || url.pathname !== "/" || url.search || url.hash) throw new Error("检索模型地址配置不符合本地服务约定。");
  const candidates = candidateHits(result.context, result.filters);
  if (!candidates.length) return result;
  try {
    const response = await fetch(new URL("/rerank", url), {
      method: "POST", headers: { "content-type": "application/json" }, redirect: "error",
      signal: AbortSignal.timeout(45000),
      body: JSON.stringify({ query: result.context, documents: candidates.map(hit => `${hit.policy.title}\n${hit.passage.locator}\n${hit.passage.text}`), top_n: candidates.length }),
    });
    if (!response.ok) throw new Error(`model_http_${response.status}`);
    const data = await response.json();
    if (!data.model || !data.revision || !data.artifact_id || !Array.isArray(data.results) || data.results.length !== candidates.length) throw new Error("model_identity_or_shape");
    const seen = new Set<number>();
    for (const row of data.results) {
      if (!Number.isInteger(row.index) || row.index < 0 || row.index >= candidates.length || seen.has(row.index) || !Number.isFinite(row.relevance_score)) throw new Error("model_invalid_ranking");
      seen.add(row.index);
    }
    // Do not claim calibrated relevance from an uncalibrated model score.
    return { ...result, hits: data.results.map((row: { index: number; relevance_score: number }) => ({ ...candidates[row.index], score: row.relevance_score })).filter((hit: { passage: { id: string } }) => result.hits.some(local => local.passage.id === hit.passage.id)).slice(0, 8), engine: "semantic", model: data.model, notice: "已通过 STL 观点检索的本地模型重排；原文来自独立政策样本。" };
  } catch {
    return { ...result, notice: "STL 语义服务本次未返回可用结果；以下保留关键词检索结果，可重试。" };
  }
}
