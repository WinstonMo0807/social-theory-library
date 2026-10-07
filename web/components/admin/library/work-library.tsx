"use client";
import { RecycleControl } from "@/components/admin/recycle-control";
import Link from "next/link";
import { BookOpen, Download, Search } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { documentLabels, pdfValidationPresentation, publicationDescription, publicationPresentation, publicationPublicHref, type CollectionPage, type WorkLibraryRow } from "@/lib/api/admin-collections";
import { adminListHref, adminPageNumber, safeAdminHref, withAdminReturn } from "@/lib/admin-route-context";
import { PageHeader, StatusBadge } from "@/components/admin-ui";
import { Pagination } from "@/components/ui/pagination";
import { SelectedWorkPreview, SavedEditionCover } from "@/components/admin/preview/selected-work-preview";
import { CatalogHealth } from "@/components/admin/workflow/catalog-health";
import { EditionDefaultsControl } from "./edition-defaults-control";
import styles from "./admin-collection.module.css";

const statusLabels: Record<string, string> = { ready: "已就绪", complete: "已完成", attention: "需处理", draft: "未完善", processing: "处理中", blocked: "已阻断", pending: "待处理", failed: "失败", paused: "已暂停", not_applicable: "不适用", unknown: "待核实" };
const kindLabels: Record<string, string> = { original: "上传原件", normalized: "阅读文件", ocr_pdf: "可搜索的扫描文件", extracted_text: "提取的文字" };

export function WorkLibrary({ initialQuery = "", initialView = "all" }: { initialQuery?: string; initialView?: string }) {
  const search = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const query = search.get("q") ?? initialQuery;
  const view = search.get("view") ?? initialView;
  const documentType = search.get("document_type") || "";
  const publicationState = search.get("publication_state") ?? ({published:"published",draft:"unpublished",withdrawn:"withdrawn"} as Record<string,string>)[view] ?? "";
  const progress = search.get("progress") ?? (["attention","quality"].includes(view) ? "attention" : "");
  const ordering = search.get("ordering") || "-updated_at";
  const params = new URLSearchParams({ page: String(adminPageNumber(search.get("page"))), ordering });
  if (query) params.set("q", query);
  if (view === "editions") params.set("view", view);
  if (publicationState) params.set("publication_state", publicationState);
  if (progress) params.set("progress", progress);
  if (documentType) params.set("document_type", documentType);
  if (search.get("work_id")) params.set("work_id", search.get("work_id")!);
  const resource = useApiResource<CollectionPage<WorkLibraryRow>>(`/catalog/admin/library/works/?${params}`, getServerSessionCredential());
  const page = resource.data;
  const [selectedId, setSelectedId] = useState("");
  const selected = selectedId ? page?.results.find(row => row.id === selectedId) : page?.results[0];
  const returnTo = `${pathname}${search.size ? `?${search}` : ""}`;
  const change = (values: Record<string, string | number | null>) => router.push(adminListHref(pathname, search.toString(), { page: 1, ...values }));
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    change({ q: String(new FormData(event.currentTarget).get("q") || "").trim() });
  }
  if (view === "editions") return <div className="admin-page edition-reference">
    <PageHeader title={selected?.title || "出版版本"} description={selected?.contributors?.join("、") || "选择作品及出版版本，核对待修问题。"}/>
    {!search.get("work_id") ? <form className="reference-search" onSubmit={submit}><input name="q" defaultValue={query} placeholder="搜索作品及出版版本" aria-label="搜索版本"/><button type="submit">搜索</button></form> : null}
    {resource.error ? <p role="alert">{resource.error}<button type="button" onClick={resource.retry}>重试</button></p> : null}
    <div className="edition-reference-columns"><section className="admin-panel edition-reference-list"><header><h2>出版版本 {page?.count ?? "—"} 个</h2><button type="button" className="button secondary" disabled title="当前无独立新增出版版本接口">＋ 新增版本</button></header>
      {resource.loading ? <p role="status">正在读取版本…</p> : null}{page?.results.map(row=><button type="button" className="edition-reference-card" key={row.id} aria-pressed={row.id===selected?.id} onClick={()=>setSelectedId(row.id)}><SavedEditionCover editionId={row.edition_id || row.id} coverUrl={row.cover_url ?? ""} title={row.title}/><span><small>{row.publication?.catalog_revision_active ? row.publication?.listed_publicly ? "当前公开主版本" : "已公开版本" : "尚未公开"}</small><strong>{row.title}</strong><span>{row.publisher || "—"}　{row.publication_year || ""}</span><span>{row.language || "—"}</span><span>{row.current_reader_asset ? pdfValidationPresentation(row.current_reader_asset.validation_status).label : "—"}</span></span></button>)}
      {page ? <Pagination label="出版版本分页" page={page.page} totalPages={page.total_pages} previousHref={adminListHref(pathname,search.toString(),{page:Math.max(1,page.page-1)})} nextHref={adminListHref(pathname,search.toString(),{page:Math.min(page.total_pages,page.page+1)})}/> : null}
      {search.get("work_id") ? <details><summary>阅读与下载默认版本</summary><EditionDefaultsControl workId={search.get("work_id")!}/></details> : null}
    </section><section className="admin-panel edition-reference-issues"><h2>所选版本的待修问题</h2>{selected ? <><p>{selected.publisher || "—"}　{selected.publication_year || ""}　{selected.language}</p><p>保存记录返回 {(selected.issues?.length || 0)+(selected.warnings?.length || 0)} 项问题</p>{[...(selected.issues || []),...(selected.warnings || [])].map((issue,index)=><article key={`${issue.code}:${index}`}><div><h3>{issue.message}</h3>{issue.field ? <small>核对当前版本的对应内容</small> : null}</div>{selected.workbench_url ? <Link className="button secondary" href={withAdminReturn(safeAdminHref(selected.workbench_url),returnTo,issue.step || (issue.field==="file" ? "file" : issue.field==="publisher" || issue.field==="publication_year" ? "bibliography" : "work"))}>去处理</Link> : null}</article>)}<details><summary>文件与处理状态</summary><CatalogHealth value={selected.health}/>{selected.assets?.map(asset=><p key={asset.id}>{asset.original_filename || kindLabels[asset.kind]} · 第{asset.version}版 · {asset.is_current ? "当前文件" : "历史文件"}</p>)}</details></> : <p>请先选择出版版本。</p>}</section>
    <SelectedWorkPreview heading="读者会看到什么" key={selected?.id || "empty"} editionId={selected?.edition_id || selected?.id} title={selected?.title} publicHref={publicationPublicHref(selected?.publication)} editHref={selected?.workbench_url ? withAdminReturn(safeAdminHref(selected.workbench_url),returnTo) : ""}/></div>
  </div>;
  return <div className="admin-reference-split library-reference"><div className="admin-page work-library-page admin-reference-list">
    <PageHeader title={view === "quality" ? "需要检查的馆藏" : "馆藏列表"} description="查找并维护馆藏" />
    <form className={styles.toolbar} onSubmit={submit}>
      <label className="reference-search-label"><span className="sr-only">搜索题名、责任者、ISBN或DOI</span><input key={query} name="q" type="search" defaultValue={query} placeholder="搜索书名、作者或关键词" /></label>
      <label>文献类型<select value={documentType} onChange={(event) => change({ document_type: event.target.value })}><option value="">全部类型</option>{Object.entries(documentLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label>公开状态<select value={publicationState} onChange={event=>change({publication_state:event.target.value,progress,view:"all"})}><option value="">全部</option><option value="published">已公开</option><option value="unpublished">尚未公开</option><option value="withdrawn">已撤回</option></select></label>
      <label>整理进度<select value={progress} onChange={event=>change({progress:event.target.value,publication_state:publicationState,view:"all"})}><option value="">全部</option><option value="attention">需要处理</option><option value="processing">处理中</option><option value="ready">准备发布</option></select></label>
      <button type="submit" className="button">搜索</button><details className="reference-list-filters"><summary>排序</summary><label>排序<select value={ordering} onChange={(event) => change({ ordering: event.target.value })}><option value="-updated_at">最近更新在前</option><option value="updated_at">较早更新在前</option><option value="title">题名升序</option><option value="-title">题名降序</option></select></label></details>
    </form>
    {search.get("work_id") ? <p className={styles.scope}>当前仅显示所选作品的出版版本。<Link href={adminListHref(pathname, search.toString(), { work_id: null, page: 1 })}>查看全部作品的版本</Link></p> : null}
    {view === "editions" && search.get("work_id") ? <EditionDefaultsControl workId={search.get("work_id")!} /> : null}
    <p className={styles.count} role="status">{page ? `共 ${page.count} 项${view === "editions" ? "出版版本" : "作品"}，本页 ${page.results.length} 项。` : resource.error ? "馆藏数量读取失败。" : "正在读取馆藏数量…"}</p>
    {resource.error ? <div className={styles.error} role="alert">{resource.error}<button type="button" onClick={resource.retry}>重新读取馆藏</button></div> : null}
    {resource.loading ? <p role="status">正在读取当前页…</p> : null}
    <section className={`${styles.rows} work-library-results`} aria-label={view === "editions" ? "出版版本列表" : "馆藏作品列表"}>

      {page?.results.map((work) => {
        const publication = publicationPresentation(work.publication);
        const publicHref = publicationPublicHref(work.publication);
        const destination = safeAdminHref(work.workbench_url, "");
        const workId = work.work_id || (work.row_type === "work" ? work.id : "");
        const versionsHref = adminListHref(pathname, search.toString(), { view: "editions", work_id: workId, page: 1 });
        return <article className={`${styles.row} work-library-row ${selected?.id === work.id ? "selected" : ""}`} key={work.id} data-record-id={work.id} data-row-type={work.row_type}>
          <div className="reference-book-heading"><SavedEditionCover editionId={work.edition_id || work.primary_edition?.id} coverUrl={work.cover_url ?? ""} title={work.title}/><div><button type="button" className="reference-select-title" aria-pressed={selected?.id === work.id} onClick={() => setSelectedId(work.id)}>{work.title || "未命名作品"}</button><small>{work.contributors?.join("、") || "—"}</small><small>{[work.publisher,work.publication_year ? `${work.publication_year}版` : work.primary_edition?.version_label].filter(Boolean).join("　") || "—"}</small><div className="reference-book-status"><StatusBadge {...publication}/>{work.availability?.capabilities.filter(cap=>cap.key==="pdf" || cap.key==="text").map(cap=><span key={cap.key} data-state={cap.status} title={cap.detail}>{cap.key==="pdf" ? cap.public_ready ? "PDF 可读" : cap.status==="ready" ? "PDF 待发布" : cap.status==="not_applicable" ? "仅书目" : cap.status==="failed" ? "PDF 校验失败" : cap.status==="pending" ? "PDF 待处理" : "PDF 待核实" : cap.status==="ready" ? "全文已整理" : cap.status==="partial" ? "全文部分完成" : cap.status==="paused" ? "全文已暂停" : cap.status==="failed" ? "全文处理失败" : cap.status==="not_applicable" ? "" : cap.status==="pending" ? "全文待整理" : "全文待核实"}</span>)}</div></div></div>
          <div className="reference-reader-actions"><strong>读者目前能做什么</strong>{[{key:"pdf",label:"在线阅读",Icon:BookOpen},{key:"download",label:"下载 PDF",Icon:Download},{key:"fulltext",label:"搜索书内内容",Icon:Search}].map(({key,label,Icon})=>{const cap=work.reader_capabilities ? work.reader_capabilities[key] : work.availability?.capabilities.find(row=>row.key===(key==="download" ? "pdf" : key));return <span key={label} aria-disabled={!publicHref || !cap?.public_ready} title={cap?.detail || "当前状态待核实"}><Icon size={14}/>{label}</span>;})}</div>
          <div className="reference-library-actions">{destination ? <Link className="button secondary" href={withAdminReturn(destination,returnTo,"work")}>编辑</Link> : null}<details className="reference-row-menu"><summary aria-label={`更多操作：${work.title}`}>•••</summary><div><p>{documentLabels[work.document_type] || work.document_type} · {work.language || "—"}</p><p>{publicationDescription(work.publication)}</p><Link href={versionsHref}>出版版本（{work.edition_count ?? 0}）</Link>{publicHref ? <Link href={publicHref} target="_blank">查看读者页面</Link> : null}{destination ? <Link href={withAdminReturn(destination,returnTo,"file")}>文件与阅读</Link> : <p>尚无可编辑出版版本。</p>}<p>文件：{statusLabels[work.asset_state || ""] || "—"}<br/>知识：{statusLabels[work.knowledge_status || ""] || "—"}<br/>策展：{statusLabels[work.curation_status || ""] || "—"}</p><time>{new Date(work.updated_at).toLocaleString("zh-CN", {timeZone:"Asia/Hong_Kong"})}</time>{work.health ? <details><summary>馆藏质量与处理原因</summary><CatalogHealth value={work.health}/></details> : null}<RecycleControl kind={work.row_type==="edition" ? "edition" : "work"} id={work.id} name={work.title || "未命名作品"} onDeleted={resource.retry}/></div></details></div>
        </article>;
      })}
      {page && !page.results.length ? <p className="admin-list-state">没有符合当前筛选的记录。可调整筛选，或从上传与推荐计划继续。</p> : null}
    </section>
    {page ? <Pagination className={styles.pagination} label="馆藏分页" page={page.page} totalPages={page.total_pages} previousHref={adminListHref(pathname, search.toString(), { page: Math.max(1, page.page - 1) })} nextHref={adminListHref(pathname, search.toString(), { page: Math.min(page.total_pages, page.page + 1) })} /> : null}
  </div><SelectedWorkPreview heading="读者会看到什么" key={selected?.id || "empty"} editionId={selected?.edition_id || selected?.primary_edition?.id || (selected?.row_type === "edition" ? selected.id : null)} title={selected?.title} publicHref={publicationPublicHref(selected?.publication)} editHref={selected?.workbench_url ? withAdminReturn(safeAdminHref(selected.workbench_url), returnTo) : ""}/></div>;
}
