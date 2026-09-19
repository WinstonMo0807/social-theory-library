"use client";

import { AlertCircle, ArrowRight, ExternalLink, RefreshCw } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { apiBlob, getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { publicationDescription, publicationPresentation, publicationPublicHref, queueWorkbenchHref, queueWorkspaceApi, selectedQueueItem, sourceLabels, type WorkflowQueueItem, type WorkflowQueuePage } from "@/lib/api/admin-collections";
import { adminListHref, adminPageNumber, withAdminReturn } from "@/lib/admin-route-context";
import { asArray, asRecord, asString } from "./admin/workflow/workflow-types";
import { PublicationDiff, type PublicationPreparation } from "./admin/workflow/publication-diff";
import { CatalogHealth } from "./admin/workflow/catalog-health";
import { PageHeader, StatusBadge } from "./admin-ui";
import { Pagination } from "./ui/pagination";
import styles from "./admin/library/admin-collection.module.css";

const publicFilters: Record<string, string> = { all: "全部公开状态", unpublished: "尚未公开", publishing: "发布处理中", published: "已公开版本", withdrawn: "已撤回" };

function PdfPreview({ path, title }: { path: string; title: string }) {
  const [result, setResult] = useState<{ path: string; url: string; error: string } | null>(null);
  useEffect(() => {
    if (!path) return;
    let alive = true;
    let url = "";
    void apiBlob(path, getServerSessionCredential()).then((blob) => {
      if (!alive) return;
      url = URL.createObjectURL(blob);
      setResult({ path, url, error: "" });
    }, (reason) => {
      if (alive) setResult({ path, url: "", error: reason instanceof Error ? reason.message : "PDF预览读取失败。" });
    });
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [path]);
  if (!path) return <p>当前没有PDF预览。纯书目可继续核对书目信息；有文件的版本请在共同工作页查看校验与处理结果。</p>;
  const current = result?.path === path ? result : null;
  if (current?.error) return <p role="alert">PDF预览暂不可用：{current.error}。可重新选择本项或打开当前版本安全重试。</p>;
  return current?.url ? <iframe className={styles.previewFrame} title={`PDF预览：${title}`} src={current.url} /> : <p role="status">正在读取当前版本PDF…</p>;
}

function PublicationDetails({ item, returnTo }: { item: WorkflowQueueItem; returnTo: string }) {
  const result = useApiResource<Record<string, unknown>>(queueWorkspaceApi(item), getServerSessionCredential(), item.id);
  const payload = result.data;
  const context = asRecord(payload?.context);
  const data = asRecord(payload?.data);
  const validIdentity = payload && (
    item.edition_id
      ? context.edition_id === item.edition_id && context.work_id === item.work_id
      : context.item_id === item.item_id
  );
  const destination = queueWorkbenchHref(item);
  if (result.error) return <div className={styles.error} role="alert">当前版本预览读取失败：{result.error}<button onClick={result.retry} type="button">重试当前版本预览</button></div>;
  if (result.loading) return <p role="status">正在读取选定对象的保存内容和公开影响…</p>;
  if (!validIdentity) return <p className={styles.error} role="alert">返回内容与指定作品或出版版本不一致，已停止显示预览。请重新打开原记录，不会显示其他馆藏。</p>;
  const work = asRecord(data.work);
  const bibliography = asRecord(data.bibliography);
  const contributors = asArray(asRecord(data.contributors).items);
  const classification = asRecord(data.classification);
  const knowledge = asRecord(data.knowledge);
  const labels = (values: unknown) => asArray(values).map((value) => { const row = asRecord(value); return asString(row.display_name || row.name || row.label); }).filter(Boolean).join("、") || "尚未关联";
  const publication = publicationPresentation(item.publication);
  const publicHref = publicationPublicHref(item.publication);
  return <section className={styles.preview} aria-label="当前版本公开预览">
    <header><div><h2>{asString(context.title || work.title, item.title)}</h2><p>{sourceLabels[item.source_type] || item.source_type} · 当前出版版本{asString(bibliography.version_label) ? `：${asString(bibliography.version_label)}` : ""}</p></div><StatusBadge {...publication} /></header>
    <p className={styles.scope}>{item.publication?.detail} 此处读取已保存内容。编辑、候选复核、文件处理与明确发布在同一共同工作页完成，保存后仍保留旧公开版本直到新修订生效。</p>
    <div className={styles.actions}>{destination ? <Link className="button" href={withAdminReturn(destination, returnTo, "publication")}>继续复核与发布 <ArrowRight size={14} /></Link> : null}
      {item.edition_id ? <Link className="button secondary" href={withAdminReturn(`/admin/preview/works/${encodeURIComponent(item.edition_id)}`, returnTo)} target="_blank">真实公开样式预览 <ExternalLink size={14} /></Link> : null}
      {publicHref ? <Link className="button secondary" href={publicHref} target="_blank">核验当前公开结果 <ExternalLink size={14} /></Link> : null}
      <button className="button secondary" onClick={result.retry} type="button">刷新此版本结果</button>
    </div>
    {payload?.health ? <CatalogHealth value={payload.health as Record<string, string>} /> : null}
    <dl className={styles.impact} aria-label="书目信息与公开影响">
      <div><dt>责任者及原职责</dt><dd>{contributors.map((value) => { const row = asRecord(value); const role = ({ author: "作者", translator: "译者", editor: "编者" } as Record<string, string>)[asString(row.role)] || asString(row.role); return `${asString(row.display_name)}（${role}）`; }).join("、") || "待确认"}</dd></div>
      <div><dt>出版信息</dt><dd>{[bibliography.publisher, bibliography.publication_year, bibliography.publication_place, bibliography.version_label].filter(Boolean).map(String).join(" · ") || "尚未填写"}</dd></div>
      <div><dt>学科页面关联</dt><dd>{labels([...asArray(classification.primary_disciplines), ...asArray(classification.related_disciplines)])}</dd></div>
      <div><dt>子学科页面关联</dt><dd>{labels(classification.subdisciplines)}</dd></div>
      <div><dt>理论与概念页面关联</dt><dd>{labels(knowledge.nodes)}</dd></div>
      <div><dt>主题页面关联</dt><dd>{labels(knowledge.topics)}</dd></div>
    </dl>
    <p className={styles.scope}>以上是本次已保存的关联范围，不代表尚未确认或未发布的关联已在前台展示。公开位置以正式修订和关联对象当前资格为准。</p>
    {item.edition_id ? <PreparedPublication editionId={item.edition_id} /> : <p>文件来源尚未建立出版版本，暂不能执行发布预检。来源任务仍保留在待办。</p>}
    <details open><summary>当前阅读文件预览</summary><PdfPreview key={`${item.id}:${item.updated_at}`} path={asString(context.pdf_preview_url)} title={item.title} /></details>
  </section>;
}

function PreparedPublication({ editionId }: { editionId: string }) {
  const result = useApiResource<PublicationPreparation>(`/catalog/admin/editions/${encodeURIComponent(editionId)}/publication/prepare/`, getServerSessionCredential());
  if (result.error) return <p role="alert">发布差异暂时不可读：{result.error}<button type="button" onClick={result.retry}>重试差异预检</button></p>;
  return result.data ? <PublicationDiff value={result.data} /> : <p role="status">正在计算已保存草稿与当前公开内容的差异…</p>;
}

export function PublicationDesk() {
  const search = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const filter = search.get("publication") || (search.get("filter") === "attention" ? "unpublished" : search.get("filter")) || "all";
  const source = search.get("source") || "";
  const query = search.get("q") || "";
  const selectedId = search.get("selection") || "";
  const params = new URLSearchParams({ scope: "publication", category: "all", page: String(adminPageNumber(search.get("page"))) });
  if (filter !== "all") params.set("publication", filter);
  if (source) params.set("source", source);
  if (query) params.set("q", query);
  const result = useApiResource<WorkflowQueuePage>(`/catalog/admin/workflows/queue/?${params}`, getServerSessionCredential());
  const page = result.data;
  const selected = selectedQueueItem(page?.results || [], selectedId);
  const returnTo = `${pathname}${search.size ? `?${search}` : ""}`;
  const change = (values: Record<string, string | number | null>) => router.push(adminListHref(pathname, search.toString(), { page: 1, filter: null, ...values }, true));
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    change({ q: String(new FormData(event.currentTarget).get("q") || "").trim() });
  }
  return <div className="admin-page publication-desk-page">
    <PageHeader eyebrow="待办与上架" title="发布管理" description="查看哪些文献还未公开、哪些正在更新。选择文献后，可以预览并继续发布。" />
    <form className={styles.toolbar} onSubmit={submit}>
      <label>题名或来源<input key={query} name="q" type="search" defaultValue={query} placeholder="搜索全部出版版本" /></label>
      <label>公开状态<select value={filter} onChange={(event) => change({ publication: event.target.value })}>{Object.entries(publicFilters).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label>来源<select value={source} onChange={(event) => change({ source: event.target.value })}><option value="">全部来源</option>{Object.entries(sourceLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <button className="button" type="submit">搜索</button><button className="button secondary" onClick={result.retry} type="button"><RefreshCw size={15} />刷新发布结果</button>
    </form>
    <p className={styles.count} role="status">{page ? `当前完整筛选共 ${page.count} 项，第 ${page.page} 页显示 ${page.results.length} 项。先筛选再分页，包含非上传来源。` : result.error ? "发布记录数量未能读取。" : "正在读取全部来源的发布记录…"}</p>
    {result.error ? <div className={styles.error} role="alert"><AlertCircle size={16} />{result.error}<button type="button" onClick={result.retry}>重试发布列表</button></div> : null}
    {result.loading ? <p role="status">正在读取当前页…</p> : null}
    <section className={styles.rows} aria-label="馆藏发布列表">{page?.results.map((item) => {
      const destination = queueWorkbenchHref(item);
      return <article className={styles.row} key={item.id} data-record-id={item.id}>
        <div className={styles.cell}><small>作品与来源</small><strong>{item.title || item.source_filename || "未命名来源"}</strong><span>{sourceLabels[item.source_type] || "来源待核实"}</span><small>{item.edition_id ? "具体出版版本" : "尚未建立版本的来源任务"}</small></div>
        <div className={styles.cell}><small>是否公开</small><StatusBadge {...publicationPresentation(item.publication)} /><span>{publicationDescription(item.publication)}</span></div>
        <div className={styles.cell}><small>当前建议</small><span>{item.current_step_label}</span><span>{item.blockers_count} 项阻断 · {item.warnings_count} 项建议</span></div>
        <div className={styles.cell}><small>最后更新</small><time>{new Date(item.updated_at).toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong" })}</time></div>
        <div className={styles.cell}><Link aria-current={selectedId === item.id ? "true" : undefined} href={adminListHref(pathname, search.toString(), { selection: item.id })}>预览与影响</Link>{destination ? <Link href={withAdminReturn(destination, returnTo, "publication")}>继续复核与发布 <ArrowRight size={14} /></Link> : <span>工作位置待核实</span>}</div>
      </article>;
    })}</section>
    {page && !page.results.length ? <p className="admin-list-state">当前筛选下没有记录。可选择全部公开状态或其他来源。</p> : null}
    {page ? <Pagination className={styles.pagination} label="发布列表分页" page={page.page} totalPages={page.total_pages} previousHref={adminListHref(pathname, search.toString(), { page: Math.max(1, page.page - 1) }, true)} nextHref={adminListHref(pathname, search.toString(), { page: Math.min(page.total_pages, page.page + 1) }, true)} /> : null}
    {page && selectedId && !selected ? <p className={styles.error} role="alert">指定记录不在当前筛选或当前页中，未显示其他作品。请恢复原筛选和页码，或明确重新选择记录。</p> : null}
    {selected ? <PublicationDetails key={selected.id} item={selected} returnTo={returnTo} /> : page && !selectedId ? <p className={styles.scope}>请选择要查看的文献。</p> : null}
  </div>;
}
