"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, RefreshCw } from "lucide-react";
import type { FormEvent } from "react";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { publicationDescription, publicationPresentation, queueWorkbenchHref, sourceLabels, type WorkflowQueuePage } from "@/lib/api/admin-collections";
import { adminListHref, adminPageNumber, withAdminReturn } from "@/lib/admin-route-context";
import { PageHeader, StatusBadge } from "./admin-ui";
import { Pagination } from "./ui/pagination";
import styles from "./admin/library/admin-collection.module.css";

const categories: Record<string, string> = { all: "全部待办", continue: "继续处理", attention: "待人工确认", exception: "需要先解决", publication_ready: "准备发布" };
const legacyCategories: Record<string, string> = { needs_review: "attention", failed: "exception", ready: "continue" };

export function ReviewQueue() {
  const search = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const category = search.get("category") || legacyCategories[search.get("status") || ""] || "all";
  const source = search.get("source") || "";
  const query = search.get("q") || search.get("search") || "";
  const pageNumber = adminPageNumber(search.get("page"));
  const params = new URLSearchParams({ category, page: String(pageNumber) });
  if (source) params.set("source", source);
  if (query) params.set("q", query);
  const result = useApiResource<WorkflowQueuePage>(`/catalog/admin/workflows/queue/?${params}`, getServerSessionCredential());
  const page = result.data;
  const returnTo = `${pathname}${search.size ? `?${search}` : ""}`;
  const change = (updates: Record<string, string | number | null>) => router.push(adminListHref(pathname, search.toString(), { page: 1, status: null, search: null, ...updates }));
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    change({ q: String(new FormData(event.currentTarget).get("q") || "").trim() });
  }
  return <div className="admin-page review-queue-page">
    <PageHeader eyebrow="待办与上架" title="待办与复核" description="上传、手工书目、维护修改、文件异常与公开结果在同一队列。筛选在全量记录上执行，每一项保留来源和当前出版版本。" actions={<><Link className="button secondary" href="/admin/cataloging/new">新建书目</Link><Link className="button" href="/admin/uploads">上传文件</Link></>} />
    <form className={styles.toolbar} onSubmit={submit}>
      <label>题名或来源文件<input key={query} name="q" type="search" defaultValue={query} placeholder="搜索全部待办" /></label>
      <label>待办类型<select value={category} onChange={(event) => change({ category: event.target.value })}>{Object.entries(categories).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>来源<select value={source} onChange={(event) => change({ source: event.target.value })}><option value="">全部来源</option>{Object.entries(sourceLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <button type="submit" className="button">搜索</button><button type="button" className="button secondary" onClick={result.retry}><RefreshCw size={15} />刷新待办</button>
    </form>
    <p className={styles.count} role="status">{page ? `当前条件共 ${page.count} 项，第 ${page.page} 页显示 ${page.results.length} 项。较早的待办排在前面，已设置优先级的项目优先。` : result.error ? "待办数量未能读取。" : "正在读取完整待办数量…"}</p>
    {page?.counts ? <p className={styles.scope}>当前来源与搜索范围：继续处理 {page.counts.continue}；待人工确认 {page.counts.attention}；阻断事项 {page.counts.exception}；可检查发布 {page.counts.publication_ready}。同一项目可能需要多类操作，分类数不相加。</p> : null}
    {result.error ? <div className={styles.error} role="alert">{result.error}<button type="button" onClick={result.retry}>重新读取待办</button></div> : null}
    {result.loading ? <p role="status">正在读取当前页…</p> : null}
    <section className={styles.rows} aria-label="待办记录">
      {page?.results.map((item) => {
        const publication = publicationPresentation(item.publication);
        const destination = queueWorkbenchHref(item);
        return <article className={styles.row} key={item.id} data-record-id={item.id}>
          <div className={styles.cell}><small>作品与来源</small><strong>{item.title || item.source_filename || "未命名来源记录"}</strong><small>{sourceLabels[item.source_type] || "来源待核实"}{item.source_filename ? ` · ${item.source_filename}` : ""}</small><span>{item.edition_id ? "已建立书目" : "还没有建立书目，请先处理文件"}</span></div>
          <div className={styles.cell}><small>公开结果</small><StatusBadge {...publication} /><span>{publicationDescription(item.publication)}</span></div>
          <div className={styles.cell}><small>当前操作</small><strong>{item.current_step_label || "核对当前记录"}</strong><span>待确认 {item.unresolved_count} 项</span></div>
          <div className={styles.cell}><small>需要做什么</small><span>{item.blockers_count} 项需要先处理</span><span>{item.warnings_count} 项建议</span><time>{new Date(item.updated_at).toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong" })}</time></div>
          <div className={styles.cell}>{destination ? <Link href={withAdminReturn(destination, returnTo)}>继续处理 <ArrowRight size={14} /></Link> : <span role="status">操作位置待核实，请刷新或检查来源记录。</span>}</div>
        </article>;
      })}
      {page && !page.results.length ? <p className="admin-list-state">当前条件下没有待办。可调整筛选，不代表其他来源没有异常。</p> : null}
    </section>
    {page ? <Pagination className={styles.pagination} label="待办分页" page={page.page} totalPages={page.total_pages} previousHref={adminListHref(pathname, search.toString(), { page: Math.max(1, page.page - 1) })} nextHref={adminListHref(pathname, search.toString(), { page: Math.min(page.total_pages, page.page + 1) })} /> : null}
  </div>;
}
