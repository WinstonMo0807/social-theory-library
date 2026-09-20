"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { RefreshCw } from "lucide-react";
import type { FormEvent } from "react";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { adminListHref, adminPageNumber, safeAdminHref, withAdminReturn } from "@/lib/admin-route-context";
import { Pagination } from "@/components/ui/pagination";
import { StatusBadge } from "@/components/admin-ui";
import styles from "../library/admin-collection.module.css";

type CurationDraft = {
  id: string; object_id: string; title: string; object_type: string; label: string;
  updated_at: string; edit_url: string; state: "draft" | "changes_pending"; can_edit: boolean;
};
type DraftPage = { count: number; page: number; page_size: number; total_pages: number; results: CurationDraft[] };

export function CurationDraftQueue() {
  const pathname = usePathname();
  const search = useSearchParams();
  const router = useRouter();
  const query = search.get("q") || "";
  const ordering = search.get("ordering") === "updated_at" ? "updated_at" : "-updated_at";
  const params = new URLSearchParams({ q: query, ordering, page: String(adminPageNumber(search.get("page"))) });
  const resource = useApiResource<DraftPage>(`/catalog/admin/curation-drafts/?${params}`, getServerSessionCredential());
  const page = resource.data;
  const returnTo = `${pathname}?${search}`;
  const change = (values: Record<string, string | number | null>) => router.push(adminListHref(pathname, search.toString(), { page: 1, ...values }));
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    change({ q: String(new FormData(event.currentTarget).get("q") || "").trim() });
  }
  return <section aria-label="策展草稿">
    <p className="admin-help">继续整理学者、主题、理论、阅读路径、网站和推荐草稿。每个对象只列一次，保存与公开发布分别完成。</p>
    <form className={styles.toolbar} onSubmit={submit}>
      <label>名称或标题<input key={query} name="q" type="search" defaultValue={query} placeholder="搜索全部策展草稿" /></label>
      <label>排序<select value={ordering} onChange={event => change({ ordering: event.target.value })}><option value="-updated_at">最近更新在前</option><option value="updated_at">较早更新在前</option></select></label>
      <button className="button" type="submit">搜索</button><button className="button secondary" type="button" onClick={resource.retry}><RefreshCw size={14} />刷新草稿</button>
    </form>
    {resource.error ? <div className={styles.error} role="alert">{resource.error}<button type="button" onClick={resource.retry}>重新读取策展草稿</button></div> : null}
    <p className={styles.count} role="status">{resource.loading ? "正在读取策展草稿…" : page ? `当前条件共 ${page.count} 项，第 ${page.page} 页显示 ${page.results.length} 项。` : "草稿数量未能读取。"}</p>
    <div className="admin-v307-review-table">
      <header><span>草稿对象</span><span>内容类型</span><span>草稿状态</span><span>更新时间</span><span>操作</span></header>
      {page?.results.map(item => {
        const destination = safeAdminHref(item.edit_url, "");
        return <article key={item.id} data-record-id={item.id}><div><strong>{item.title || "未命名草稿"}</strong></div><div>{item.label || item.object_type}</div><div><StatusBadge label={item.state === "changes_pending" ? "有待发布修改" : "尚未发布"} tone="neutral" /></div><div><time>{new Date(item.updated_at).toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong" })}</time></div><div>{item.can_edit && destination ? <Link className="button" href={withAdminReturn(destination, returnTo)}>继续编辑</Link> : <span>{item.can_edit ? "编辑位置待核实" : "当前账户只读"}</span>}</div></article>;
      })}
      {page && !page.results.length ? <p className="admin-list-state">当前条件下没有策展草稿。可以调整搜索，或从学者、主题、理论、网站与推荐栏目新建。</p> : null}
    </div>
    {page ? <Pagination className={styles.pagination} label="策展草稿分页" page={page.page} totalPages={page.total_pages} previousHref={adminListHref(pathname, search.toString(), { page: Math.max(1, page.page - 1) })} nextHref={adminListHref(pathname, search.toString(), { page: Math.min(page.total_pages, page.page + 1) })} /> : null}
  </section>;
}
