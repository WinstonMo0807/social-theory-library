// Server-side public API domain. Browser components use pure adapters and type-only imports.
import { works as demoWorks, scholars as demoScholars } from "../data";
import { adaptApiWork as adaptWork, adaptApiScholar as adaptScholar } from "../public-data-adapters";
import type { SearchContext } from "../search-context";
import type { ScopedSearchEnvelope, SearchFilters, SearchPayload, SemanticSearchPayload, ViewpointStance, ViewpointSearchResult, ViewpointSearchPayload } from "./search.types";
import { serverRequest, allowDemoFallback } from "./server-request";

export async function loadScopedSearch(
  context: SearchContext,
  query = "",
  options: { page?: number; limit?: number } = {},
): Promise<ScopedSearchEnvelope> {
  const parameters = new URLSearchParams({ context, envelope: "1" });
  if (query.trim()) parameters.set("q", query.trim());
  if (options.page) parameters.set("page", String(options.page));
  if (options.limit) parameters.set("limit", String(options.limit));
  try {
    return await serverRequest<ScopedSearchEnvelope>(`/catalog/search/?${parameters.toString()}`);
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return {
      implementation_version: "scoped-search-demo-fallback",
      context,
      visibility: "public",
      query,
      groups: [],
      total: 0,
      pagination: { page: options.page || 1, limit: options.limit || 24, total: 0, total_pages: 0 },
      latency_ms: 0,
    };
  }
}

export async function loadHotSearches(): Promise<string[]> {
  try {
    const payload = await serverRequest<{
      results: { query: string; search_count: number; unique_sessions: number }[];
    }>("/catalog/hot-searches/?days=30&limit=10");
    return payload.results.map((item) => item.query);
  } catch {
    return [];
  }
}

export async function loadSearch(query: string, filters: SearchFilters = {}) {
  try {
    const parameters = new URLSearchParams({ context: "global" });
    if (query) parameters.set("q", query);
    if (filters.scope) parameters.set("scope", filters.scope);
    if (filters.sort) parameters.set("sort", filters.sort);
    if (filters.page) parameters.set("page", String(filters.page));
    if (filters.pageSize) parameters.set("page_size", String(filters.pageSize));
    [
      ["document_type", filters.documentType],
      ["theory", filters.theory],
      ["topic", filters.topic],
      ["concept", filters.concept],
      ["author", filters.author],
      ["year", filters.year],
      ["language", filters.language],
      ["access", filters.access],
    ].forEach(([name, values]) => {
      (values as string[] | undefined)?.forEach((value) => parameters.append(name as string, value));
    });
    const payload = await serverRequest<SearchPayload>(
      `/catalog/search/?${parameters.toString()}`,
    );
    return {
      source: "api" as const,
      counts: payload.counts,
      works: payload.works.map(adaptWork),
      scholars: payload.scholars.map(adaptScholar),
      topics: payload.topics,
      theories: payload.theories,
      passages: payload.passages,
      facets: payload.facets,
      pagination: payload.pagination,
    };
  } catch (error) {
    if (!allowDemoFallback) throw error;
    const folded = query.toLocaleLowerCase("zh-CN");
    const filteredWorks = demoWorks.filter((work) =>
      [work.title, work.author, work.school, work.summary]
        .join(" ")
        .toLocaleLowerCase("zh-CN")
        .includes(folded),
    );
    return {
      source: "demo" as const,
      counts: {
        works: filteredWorks.length,
        books: filteredWorks.filter((work) => work.kind === "图书").length,
        articles: filteredWorks.filter((work) => work.kind === "期刊论文").length,
        theses: filteredWorks.filter((work) => work.kind === "学位论文").length,
        reports: filteredWorks.filter((work) => work.kind === "研究报告").length,
        scholars: demoScholars.length,
        topics: 0,
        theories: 0,
        passages: 1,
      },
      works: filteredWorks.length ? filteredWorks : demoWorks.slice(0, 3),
      scholars: demoScholars,
      topics: [],
      theories: [],
      passages: [],
      facets: {
        document_types: [],
        authors: [],
        years: [],
        languages: [],
        access: [],
        theories: [],
        topics: [],
        concepts: [],
      },
      pagination: {
        page: 1,
        page_size: 24,
        total: filteredWorks.length,
        total_pages: 1,
      },
    };
  }
}

export async function loadSemanticSearch(
  query: string,
  filters: SearchFilters = {},
): Promise<SemanticSearchPayload> {
  if (query.trim().length < 2) {
    return {
      query,
      engine: "keyword_fallback",
      fallback_used: false,
      notice: "输入一个词、一句话或一段文字，系统会查找观点相近的公开全文。",
      count: 0,
      work_count: 0,
      understanding: {
        type: "等待输入",
        terms: [],
        related_concepts: [],
        rewrites: [],
        rewrite_source: "",
      },
      query_rewrite_enabled: false,
      query_rewrite_active: false,
      active_rewrite: "",
      facets: {
        document_types: [],
        authors: [],
        years: [],
        languages: [],
        access: [],
        theories: [],
        topics: [],
        concepts: [],
      },
      results: [],
    };
  }
  const parameters = new URLSearchParams({ q: query.trim() });
  [
    ["document_type", filters.documentType],
    ["language", filters.language],
    ["author", filters.author],
    ["year", filters.year],
    ["theory", filters.theory],
    ["topic", filters.topic],
    ["concept", filters.concept],
    ["access", filters.access],
  ].forEach(([name, values]) => {
    (values as string[] | undefined)?.forEach((value) => parameters.append(name as string, value));
  });
  if (filters.pageSize) parameters.set("limit", String(filters.pageSize));
  if (filters.workId) parameters.set("work_id", filters.workId);
  if (filters.maxPerWork !== undefined) parameters.set("max_per_work", String(filters.maxPerWork));
  if (filters.sort) parameters.set("sort", filters.sort);
  if (filters.rewrite) parameters.set("rewrite", filters.rewrite);
  if (filters.rewriteDisabled) parameters.set("rewrite_disabled", "1");
  try {
    return await serverRequest<SemanticSearchPayload>(
      `/catalog/semantic-search/?${parameters.toString()}`,
    );
  } catch {
    return {
      query,
      engine: "unavailable",
      fallback_used: false,
      service_unavailable: true,
      fallback_reason: "api_unavailable",
      notice: "观点检索服务暂时无法连接，因此无法验证关键词或语义检索是否已经执行。原文检索、在线阅读和下载仍可继续使用。",
      count: 0,
      work_count: 0,
      understanding: {
        type: "服务暂不可用",
        terms: [],
        related_concepts: [],
        rewrites: [query],
        rewrite_source: "原始查询",
      },
      query_rewrite_enabled: false,
      query_rewrite_active: false,
      active_rewrite: "",
      facets: {
        document_types: [],
        authors: [],
        years: [],
        languages: [],
        access: [],
        theories: [],
        topics: [],
        concepts: [],
      },
      results: [],
    };
  }
}

function emptyViewpointGroups(): Record<ViewpointStance, ViewpointSearchResult[]> {
  return {
    direct: [],
    support: [],
    oppose: [],
    qualify: [],
    critique: [],
    extend: [],
    reframe: [],
  };
}

function emptyViewpointCounts(): Record<ViewpointStance, number> {
  return {
    direct: 0,
    support: 0,
    oppose: 0,
    qualify: 0,
    critique: 0,
    extend: 0,
    reframe: 0,
  };
}

function unavailableViewpointSearch(
  query: string,
  notice: string,
  serviceUnavailable = false,
): ViewpointSearchPayload {
  const groups = emptyViewpointGroups();
  return {
    query,
    query_claim: {
      proposition: query,
      subject: "",
      predicate: "",
      object: "",
      polarity: "uncertain",
      qualifiers: [],
      claim_type: "assertion",
    },
    default_mode: "baseline",
    results: [],
    groups,
    facets: {
      relations: [],
      source_types: [],
      languages: [],
      scholars: [],
      theories: [],
      topics: [],
      works: [],
      publication_year: { min: null, max: null },
    },
    count: 0,
    work_count: 0,
    stance_counts: emptyViewpointCounts(),
    engine: serviceUnavailable ? "unavailable" : "v2",
    search_version: "v2",
    fallback_used: false,
    fallback_reason: serviceUnavailable ? "api_unavailable" : "",
    notice,
    service_unavailable: serviceUnavailable,
    metadata: {
      benchmark_gate_passed: false,
      default_ranking: "semantic_v2_baseline",
      claim_ranking_status: "shadow",
      evidence_span_validation_required: true,
      cosine_similarity_used_for_stance: false,
    },
  };
}

export async function loadViewpointSearch(
  query: string,
  filters: SearchFilters = {},
): Promise<ViewpointSearchPayload> {
  if (query.trim().length < 2) {
    return unavailableViewpointSearch(
      query,
      "输入一个完整的社会科学命题，系统会按直接、支持、相斥、限定和批评整理馆藏原文。",
    );
  }
  const parameters = new URLSearchParams({ q: query.trim() });
  [
    ["document_type", filters.documentType],
    ["language", filters.language],
    ["author", filters.author],
    ["scholar", filters.scholar],
    ["relation", filters.relation],
    ["source_type", filters.sourceType],
    ["year", filters.year],
    ["theory", filters.theory],
    ["topic", filters.topic],
    ["concept", filters.concept],
    ["access", filters.access],
  ].forEach(([name, values]) => {
    (values as string[] | undefined)?.forEach((value) => parameters.append(name as string, value));
  });
  if (filters.yearMin !== undefined) parameters.set("year_min", String(filters.yearMin));
  if (filters.yearMax !== undefined) parameters.set("year_max", String(filters.yearMax));
  if (filters.pageSize) parameters.set("limit", String(filters.pageSize));
  if (filters.workId) parameters.set("work_id", filters.workId);
  if (filters.maxPerWork !== undefined) parameters.set("max_per_work", String(filters.maxPerWork));
  if (filters.sort) parameters.set("sort", filters.sort);
  try {
    return await serverRequest<ViewpointSearchPayload>(
      `/catalog/viewpoint-search/?${parameters.toString()}`,
    );
  } catch {
    return unavailableViewpointSearch(
      query,
      "观点检索暂时无法连接，系统没有生成替代结果。原文检索和在线阅读仍可继续使用。",
      true,
    );
  }
}
