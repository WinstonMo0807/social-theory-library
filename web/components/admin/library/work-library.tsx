"use client";

import { RecycleControl } from "@/components/admin/recycle-control";
import Link from "next/link";
import { ArrowRight, RefreshCw } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { FormEvent } from "react";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { documentLabels, pdfValidationPresentation, publicationDescription, publicationPresentation, publicationPublicHref, type CollectionPage, type WorkLibraryRow } from "@/lib/api/admin-collections";
import { adminListHref, adminPageNumber, safeAdminHref, withAdminReturn } from "@/lib/admin-route-context";
import { PageHeader, StatusBadge } from "@/components/admin-ui";
import { Pagination } from "@/components/ui/pagination";
import { CatalogHealth } from "@/components/admin/workflow/catalog-health";
import styles from "./admin-collection.module.css";

const statusLabels: Record<string, string> = { ready: "已就绪", complete: "已完成", attention: "需处理", draft: "未完善", processing: "处理中", blocked: "已阻断", pending: "待处理", failed: "失败", paused: "已暂停", not_applicable: "不适用", unknown: "待核实" };
const viewLabels: Record<string, string> = { all: "全部作品", editions: "版本与文件", quality: "馆藏质量", attention: "需要处理", published: "已公开", draft: "尚未公开", withdrawn: "已撤回" };
const kindLabels: Record<string, string> = { original: "上传原件", normalized: "阅读文件", ocr_pdf: "可搜索的扫描文件", extracted_text: "提取的文字" };

export function WorkLibrary({ initialQuery = "", initialView = "all" }: { initialQuery?: string; initialView?: string }) {
  const search = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const query = search.get("q") ?? initialQuery;
  const view = search.get("view") ?? initialView;
  const documentType = search.get("document_type") || "";
  const ordering = search.get("ordering") || "-updated_at";
  const params = new URLSearchParams({ page: String(adminPageNumber(search.get("page"))), ordering });
  if (query) params.set("q", query);
  if (view !== "all") params.set("view", view);
  if (documentType) params.set("document_type", documentType);
  if (search.get("work_id")) params.set("work_id", search.get("work_id")!);
  const resource = useApiResource<CollectionPage<WorkLibraryRow>>(`/catalog/admin/library/works/?${params}`, getServerSessionCredential());
  const page = resource.data;
  const returnTo = `${pathname}${search.size ? `?${search}` : ""}`;
  const change = (values: Record<string, string | number | null>) => router.push(adminListHref(pathname, search.toString(), { page: 1, ...values }));
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    change({ q: String(new FormData(event.currentTarget).get("q") || "").trim() });
  }
  return <div className="admin-page work-library-page">
    <PageHeader eyebrow="全局搜索" title={view === "editions" ? "出版版本与文件" : view === "quality" ? "需要检查的馆藏" : "馆藏搜索"} description="查找文献，修改资料或处理文件。同一作品的不同出版版本可以分别查看。" actions={<Link className="button" href={withAdminReturn("/admin/uploads", returnTo)}>上传文件</Link>} />
    <form className={styles.toolbar} onSubmit={submit}>
      <label>题名、责任者、ISBN或DOI<input key={query} name="q" type="search" defaultValue={query} placeholder="搜索全部馆藏" /></label>
      <label>馆藏视图<select value={view} onChange={(event) => change({ view: event.target.value, work_id: null })}>{Object.entries(viewLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label>文献类型<select value={documentType} onChange={(event) => change({ document_type: event.target.value })}><option value="">全部类型</option>{Object.entries(documentLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label>排序<select value={ordering} onChange={(event) => change({ ordering: event.target.value })}><option value="-updated_at">最近更新在前</option><option value="updated_at">较早更新在前</option><option value="title">题名升序</option><option value="-title">题名降序</option></select></label>
      <button type="submit" className="button">搜索</button><button type="button" className="button secondary" onClick={resource.retry}><RefreshCw size={14} />刷新馆藏</button>
    </form>
    {search.get("work_id") ? <p className={styles.scope}>当前仅显示所选作品的出版版本。<Link href={adminListHref(pathname, search.toString(), { work_id: null, page: 1 })}>查看全部作品的版本</Link></p> : null}
    <p className={styles.count} role="status">{page ? `共 ${page.count} 项${view === "editions" ? "出版版本" : "作品"}，本页 ${page.results.length} 项。` : resource.error ? "馆藏数量读取失败。" : "正在读取馆藏数量…"}</p>
    {resource.error ? <div className={styles.error} role="alert">{resource.error}<button type="button" onClick={resource.retry}>重新读取馆藏</button></div> : null}
    {resource.loading ? <p role="status">正在读取当前页…</p> : null}
    <section className={`${styles.rows} work-library-results`} aria-label={view === "editions" ? "出版版本列表" : "馆藏作品列表"}>
      <header className="work-library-table-heading"><span>馆藏与责任者</span><span>出版版本</span><span>公开状态</span><span>处理状态与更新</span><span>操作</span></header>
      {page?.results.map((work) => {
        const publication = publicationPresentation(work.publication);
        const publicHref = publicationPublicHref(work.publication);
        const destination = safeAdminHref(work.workbench_url, "");
        const workId = work.work_id || (work.row_type === "work" ? work.id : "");
        const versionsHref = adminListHref(pathname, search.toString(), { view: "editions", work_id: workId, page: 1 });
        return <article className={`${styles.row} work-library-row`} key={work.id} data-record-id={work.id} data-row-type={work.row_type}>
          <div className={styles.cell}><small>作品</small><strong>{work.title || "未命名作品"}</strong><span>{documentLabels[work.document_type] || work.document_type} · {work.language || "语言待确认"}</span><small>{work.contributors?.join("、") || "责任者待确认"}</small></div>
          <div className={styles.cell}><small>出版版本</small><strong>{work.row_type === "edition" ? work.label || "出版信息待补" : work.primary_edition?.label || "未指定主版本"}</strong><span>{work.row_type === "edition" ? work.is_primary ? "主版本 · 用于作品列表" : "非主版本 · 保留版本身份" : `${work.edition_count ?? 0} 个版本`}</span><Link href={versionsHref}>查看此作品的全部版本</Link></div>
          <div className={styles.cell}><small>是否公开</small><StatusBadge {...publication} /><span>{publicationDescription(work.publication)}</span>{publicHref ? <Link href={publicHref} target="_blank">查看读者页面</Link> : null}</div>
          <div className={styles.cell}><small>文件、知识与策展</small><span>文件：{statusLabels[work.asset_state || ""] || "见版本文件"}</span><span>知识：{statusLabels[work.knowledge_status || ""] || "见对象详情"}</span><span>策展：{statusLabels[work.curation_status || ""] || "见对象详情"}</span><time>{new Date(work.updated_at).toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong" })}</time></div>
          <div className={styles.cell}><RecycleControl kind={work.row_type === "edition" ? "edition" : "work"} id={work.id} name={work.title || "未命名作品"} onDeleted={resource.retry} />{destination ? <><Link href={withAdminReturn(destination, returnTo, "work")}>编辑当前版本 <ArrowRight size={13} /></Link><Link href={withAdminReturn(destination, returnTo, "file")}>文件与阅读</Link></> : <span>尚无可编辑出版版本，请核对作品记录。</span>}</div>
          {work.health ? <details className={styles.details}><summary>馆藏质量与处理原因</summary><CatalogHealth value={work.health} /></details> : null}
          {work.row_type === "edition" ? <details className={styles.details}><summary>版本文件与历史（{work.assets?.length ?? 0}）</summary><p className={styles.scope}>{work.current_reader_asset ? `当前阅读文件：${work.current_reader_asset.original_filename || kindLabels[work.current_reader_asset.kind] || work.current_reader_asset.kind}，文件版本${work.current_reader_asset.version}。` : "当前没有已选阅读文件。纯书目不需要虚构PDF或OCR进度。"} 替换和补充文件从“文件与阅读”进入；原件、历史及已有阅读页标识保留。</p>
            <ul className={styles.files}>{work.assets?.map((asset) => <li key={asset.id}><strong>{asset.original_filename || kindLabels[asset.kind] || asset.kind}</strong><span>{kindLabels[asset.kind] || asset.kind} · 第{asset.version}版 · {asset.is_current ? "当前文件" : "历史文件"}</span><StatusBadge {...pdfValidationPresentation(asset.validation_status)} /><span>{asset.page_count}页 · {statusLabels[asset.status] || asset.status}</span><small>{work.current_reader_asset?.id === asset.id ? "当前阅读使用" : "未作为当前阅读文件"}</small></li>)}</ul>
            {!work.assets?.length ? <p>该出版版本没有文件。可从当前版本补充文件，不会重复新建作品。</p> : null}
          </details> : null}
        </article>;
      })}
      {page && !page.results.length ? <p className="admin-list-state">没有符合当前筛选的记录。可调整筛选，或从上传与推荐计划继续。</p> : null}
    </section>
    {page ? <Pagination className={styles.pagination} label="馆藏分页" page={page.page} totalPages={page.total_pages} previousHref={adminListHref(pathname, search.toString(), { page: Math.max(1, page.page - 1) })} nextHref={adminListHref(pathname, search.toString(), { page: Math.min(page.total_pages, page.page + 1) })} /> : null}
  </div>;
}
