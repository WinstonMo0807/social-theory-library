"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, RefreshCw, Search } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { EmptyState, PageHeader, StatusBadge, type StatusTone } from "@/components/admin-ui";
import { asArray, asRecord, asString } from "../workflow/workflow-types";

type WorkRow = {
  id: string;
  title: string;
  document_type: string;
  language: string;
  contributors: string[];
  edition_count: number;
  primary_edition: string;
  publication_state: string;
  asset_state: string;
  knowledge_status: string;
  curation_status: string;
  updated_at: string;
};

type WorkPage = { count: number; next?: string | null; previous?: string | null; results: WorkRow[] };

const documentLabels: Record<string, string> = {
  book: "图书",
  journal_article: "期刊论文",
  thesis: "学位论文",
  report: "研究报告",
};

const toneByStatus: Record<string, StatusTone> = {
  published: "success",
  complete: "success",
  ready: "success",
  attention: "warning",
  draft: "neutral",
  processing: "info",
  blocked: "danger",
  withdrawn: "warning",
};

const statusLabels: Record<string, string> = {
  published: "已发布",
  ready: "已就绪",
  complete: "已完成",
  attention: "需处理",
  draft: "草稿",
  processing: "处理中",
  blocked: "已阻止",
  withdrawn: "已下架",
  pending: "待处理",
  failed: "失败",
};

function normalizeRow(value: unknown): WorkRow | null {
  const row = asRecord(value);
  const id = asString(row.id);
  if (!id) return null;
  const primaryEdition = asRecord(row.primary_edition);
  const contributors = asArray(row.contributors ?? row.author_names).map((entry) => {
    const person = asRecord(entry);
    return asString(person.display_name ?? person.name ?? entry);
  }).filter(Boolean);
  return {
    id,
    title: asString(row.title, "未命名作品"),
    document_type: asString(row.document_type, "book"),
    language: asString(row.language, "—"),
    contributors,
    edition_count: Number(row.edition_count ?? 0),
    primary_edition: asString(primaryEdition.label ?? primaryEdition.version_label ?? row.primary_edition_label, "未指定"),
    publication_state: asString(row.publication_state, "draft"),
    asset_state: asString(row.asset_state, "pending"),
    knowledge_status: asString(row.knowledge_status, "pending"),
    curation_status: asString(row.curation_status, "pending"),
    updated_at: asString(row.updated_at),
  };
}

export function WorkLibrary({ initialQuery = "", initialView = "all" }: { initialQuery?: string; initialView?: string }) {
  const [query, setQuery] = useState(initialQuery);
  const [submittedQuery, setSubmittedQuery] = useState(initialQuery);
  const [view, setView] = useState(initialView);
  const [page, setPage] = useState<WorkPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  const load = useCallback(async () => {
    const token = getServerSessionCredential();
    if (!token) return;
    setLoading(true);
    const params = new URLSearchParams();
    if (submittedQuery.trim()) params.set("q", submittedQuery.trim());
    if (view && view !== "all") params.set("view", view);
    try {
      const payload = await apiRequest<{ count?: number; next?: string | null; previous?: string | null; results?: unknown[] }>(`/catalog/admin/library/works/?${params.toString()}`, {}, token);
      const results = (payload.results ?? []).flatMap((entry) => {
        const normalized = normalizeRow(entry);
        return normalized ? [normalized] : [];
      });
      setPage({ count: Number(payload.count ?? results.length), next: payload.next, previous: payload.previous, results });
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "正式馆藏读取失败。");
    } finally {
      setLoading(false);
    }
  }, [submittedQuery, view]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load, revision]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const normalized = query.trim();
    setSubmittedQuery(normalized);
    const url = new URL(window.location.href);
    if (normalized) url.searchParams.set("q", normalized); else url.searchParams.delete("q");
    if (view !== "all") url.searchParams.set("view", view); else url.searchParams.delete("view");
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  }

  return (
    <div className="admin-page work-library-page">
      <PageHeader eyebrow="馆藏" title="作品与版本" description="以 Work 为正式馆藏身份。版本、文件和上传历史从作品详情继续查看。" actions={<Link className="button" href="/admin/uploads">上传与批次</Link>} />
      <form className="admin-list-toolbar" onSubmit={submit}>
        <label><Search size={15} /><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索题名、责任者、ISBN 或 DOI" /></label>
        <label><span className="sr-only">馆藏视图</span><select value={view} onChange={(event) => { setView(event.target.value); setSubmittedQuery(query.trim()); }}><option value="all">全部作品</option><option value="editions">版本与文件</option><option value="quality">馆藏质量</option><option value="attention">需要处理</option><option value="published">已发布</option><option value="draft">草稿</option><option value="withdrawn">已下架</option></select></label>
        <button type="submit">搜索</button><button type="button" onClick={() => setRevision((value) => value + 1)}><RefreshCw size={14} />刷新</button>
      </form>
      {error ? <p className="admin-list-state review-error" role="alert">{error}</p> : null}
      {loading ? <p className="admin-list-state">正在读取作品馆藏……</p> : null}
      {!loading && !error && !page?.results.length ? <EmptyState title="没有匹配的作品" description="上传形成 Work 后会显示在这里。" icon={<BookOpen size={21} />} /> : null}
      {page?.results.length ? <section className="work-library-table admin-panel"><header><span>作品</span><span>版本</span><span>发布</span><span>文件</span><span>知识</span><span>策展</span><span>更新时间</span><span>操作</span></header>{page.results.map((work) => <article key={work.id}><div><strong>{work.title}</strong><small>{documentLabels[work.document_type] ?? work.document_type} · {work.language} · {work.contributors.join("、") || "责任者待确认"}</small></div><span><strong>{work.edition_count}</strong><small>{work.primary_edition}</small></span><StatusBadge label={statusLabels[work.publication_state] ?? work.publication_state} tone={toneByStatus[work.publication_state] ?? "neutral"} /><StatusBadge label={statusLabels[work.asset_state] ?? work.asset_state} tone={toneByStatus[work.asset_state] ?? "neutral"} /><StatusBadge label={statusLabels[work.knowledge_status] ?? work.knowledge_status} tone={toneByStatus[work.knowledge_status] ?? "neutral"} /><StatusBadge label={statusLabels[work.curation_status] ?? work.curation_status} tone={toneByStatus[work.curation_status] ?? "neutral"} /><time>{work.updated_at ? new Date(work.updated_at).toLocaleString("zh-CN") : "—"}</time><Link href={`/admin/library/works/${work.id}#work`}>打开作品 <ArrowRight size={13} /></Link></article>)}<footer>共 {page.count} 项作品。上传历史不会取代 Work 身份。</footer></section> : null}
    </div>
  );
}
