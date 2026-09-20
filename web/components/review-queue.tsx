"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, RefreshCw } from "lucide-react";
import type { FormEvent } from "react";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { publicationPresentation, queueWorkbenchHref, sourceLabels, type WorkflowQueuePage } from "@/lib/api/admin-collections";
import { adminListHref, adminPageNumber, withAdminReturn } from "@/lib/admin-route-context";
import { PageHeader, StatusBadge } from "./admin-ui";
import { Pagination } from "./ui/pagination";
import { CurationDraftQueue } from "./admin/curation/curation-draft-queue";
import styles from "./admin/library/admin-collection.module.css";

const categories: Record<string, string> = { all: "全部待办", continue: "继续处理", attention: "待人工确认", exception: "需要先解决", publication_ready: "准备发布" };
const legacyCategories: Record<string, string> = { needs_review: "attention", failed: "exception", ready: "continue" };
const orderings: Record<string, string> = { priority: "当前工作优先", "-updated_at": "最近更新在前", updated_at: "较早更新在前" };

export function ReviewQueue() {
  const search = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const curation = search.get("workspace") === "curation";
  const category = search.get("category") || legacyCategories[search.get("status") || ""] || "all";
  const source = search.get("source") || "";
  const query = search.get("q") || search.get("search") || "";
  const ordering = search.get("ordering") || "priority";
  const pageNumber = adminPageNumber(search.get("page"));
  const params = new URLSearchParams({ category, ordering, page: String(pageNumber) });
  if (source) params.set("source", source);
  if (query) params.set("q", query);
  const result = useApiResource<WorkflowQueuePage>(curation ? "" : `/catalog/admin/workflows/queue/?${params}`, getServerSessionCredential());
  const page = result.data;
  const returnTo = `${pathname}${search.size ? `?${search}` : ""}`;
  const change = (updates: Record<string, string | number | null>) => router.push(adminListHref(pathname, search.toString(), { page: 1, status: null, search: null, ...updates }));
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    change({ q: String(new FormData(event.currentTarget).get("q") || "").trim() });
  }
  return <div className="admin-page review-queue-page">
    <PageHeader eyebrow="管理后台" title="待办与复核" description="继续处理馆藏待办与知识、网站和推荐草稿，保存后再明确发布。" actions={<Link className="button" href="/admin/uploads">上传文件</Link>} />
    <nav className="v307-admin-tabs" aria-label="待办工作区"><Link aria-current={!curation ? "page" : undefined} href={adminListHref(pathname, search.toString(), { workspace: null, ordering: null, page: 1 })}>馆藏待办</Link><Link aria-current={curation ? "page" : undefined} href={adminListHref(pathname, search.toString(), { workspace: "curation", ordering: "-updated_at", page: 1 })}>策展草稿</Link></nav>
    {curation ? <CurationDraftQueue /> : <>
    <nav className="admin-v307-review-counts" aria-label="待办筛选">{Object.entries(categories).map(([key,label])=><button type="button" className={category===key?"active":""} key={key} onClick={()=>change({category:key})}><span>{label}</span><strong>{page?.counts[key as keyof WorkflowQueuePage["counts"]]??"—"}</strong></button>)}</nav>
    <form className={styles.toolbar} onSubmit={submit}>
      <label>题名或来源文件<input key={query} name="q" type="search" defaultValue={query} placeholder="搜索全部待办" /></label>
      <label>待办类型<select value={category} onChange={(event) => change({ category: event.target.value })}>{Object.entries(categories).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>来源<select value={source} onChange={(event) => change({ source: event.target.value })}><option value="">全部来源</option>{Object.entries(sourceLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>排序<select value={ordering} onChange={(event) => change({ ordering: event.target.value })}>{Object.entries(orderings).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
      <button type="submit" className="button">搜索</button><button type="button" className="button secondary" onClick={result.retry}><RefreshCw size={15} />刷新待办</button>
    </form>
    <p className={styles.count} role="status">{page ? `当前条件共 ${page.count} 项，第 ${page.page} 页显示 ${page.results.length} 项。${ordering === "priority" ? "较早的待办排在前面，已设置优先级的项目优先。" : ordering === "-updated_at" ? "按全部匹配待办的更新时间从新到旧排序。" : "按全部匹配待办的更新时间从旧到新排序。"}` : result.error ? "待办数量未能读取。" : "正在读取完整待办数量…"}</p>
    {result.error ? <div className={styles.error} role="alert">{result.error}<button type="button" onClick={result.retry}>重新读取待办</button></div> : null}
    {result.loading ? <p role="status">正在读取当前页…</p> : null}
    <section className="admin-v307-review-table" aria-label="待办记录">
      <header><span>书目信息</span><span>公开状态</span><span>当前工作</span><span>更新时间</span><span>操作</span></header>
      {page?.results.map((item) => {
        const publication = publicationPresentation(item.publication);
        const destination = queueWorkbenchHref(item);
        return <article key={item.id} data-record-id={item.id}>
          <div><strong>{item.title || item.source_filename || "未命名来源记录"}</strong><small>{sourceLabels[item.source_type] || "来源待核实"}{item.source_filename ? ` · ${item.source_filename}` : ""}</small>{item.recommendation_sources?.map(source => <Link key={source.id} href={source.url}>来自推荐 · {source.title}</Link>)}</div>
          <div><StatusBadge {...publication} /></div>
          <div><strong>{item.current_step_label || "核对当前记录"}</strong><small>{item.blockers_count ? `${item.blockers_count} 项需要处理` : `${item.unresolved_count} 项待确认`}</small></div>
          <div><time>{new Date(item.updated_at).toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong" })}</time></div>
          <div>{destination ? <Link className="button" href={withAdminReturn(destination, returnTo,item.current_step)}>继续处理 <ArrowRight size={14} /></Link> : <span role="status">操作位置待核实，请刷新。</span>}</div>
        </article>;
      })}
      {page && !page.results.length ? <p className="admin-list-state">当前条件下没有待办。可调整筛选，不代表其他来源没有异常。</p> : null}
    </section>
    {page ? <Pagination className={styles.pagination} label="待办分页" page={page.page} totalPages={page.total_pages} previousHref={adminListHref(pathname, search.toString(), { page: Math.max(1, page.page - 1) })} nextHref={adminListHref(pathname, search.toString(), { page: Math.min(page.total_pages, page.page + 1) })} /> : null}
    </>}
  </div>;
}
