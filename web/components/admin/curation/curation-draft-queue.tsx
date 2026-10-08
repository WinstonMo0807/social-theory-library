"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { RefreshCw, Monitor, Smartphone, Maximize2, ArrowLeft } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { adminListHref, adminPageNumber, safeAdminHref, withAdminReturn } from "@/lib/admin-route-context";
import { Pagination } from "@/components/ui/pagination";
import type { RecommendationIssue } from "@/lib/api/recommendation-issues.types";
import { PreviewSurface, type KnowledgePreviewPayload } from "../preview/knowledge-page-preview";
import { PreviewViewport } from "./fixed-page-editor";
import { curationPreviewChanges } from "./curation-preview-changes";
import { CurationPreviewComparison } from "./curation-preview-comparison";
import comparisonStyles from "./curation-preview-comparison.module.css";
import styles from "../library/admin-collection.module.css";

type CurationDraft = {
  id: string; object_id: string; title: string; object_type: string; label: string;
  changed_fields: string[]; updated_at: string; edit_url: string; state: "draft" | "changes_pending"; can_edit: boolean;
};
const groups = {all:"全部",theories:"理论流派",scholars:"学者",topics:"主题",recommendations:"每日荐读",site:"网站内容"};
const changedLabels: Record<string,string> = {person:"个人介绍",biography:"个人介绍",introduction:"内容介绍",abstract:"内容简介",essential_works:"重要文献",works:"重要文献",curation:"内容策展",title:"标题",name:"名称",canonical_name_zh:"名称",body_blocks:"文章内容",items:"推荐书目",display_from:"发布时间",cover_url:"封面",hero_image:"页面图片",site_config:"网站内容",config:"网站内容",about_blocks:"关于书库",description:"内容介绍",timeline:"生平与时间线",core_questions:"研究问题",key_concepts:"核心概念",network:"学术关系",frequently_read_scholars:"相关人物",related_theories:"理论关联",stages:"阅读阶段"};
function changeSummary(fields:string[]){return [...new Set(fields.map(field=>changedLabels[field.split(".").at(-1)!] || changedLabels[field.split(".")[0]]).filter(Boolean))].join("、") || "—";}
type DraftPage = { counts:Record<keyof typeof groups,number>; count: number; page: number; page_size: number; total_pages: number; results: CurationDraft[] };

export function CurationDraftQueue() {
  const pathname = usePathname();
  const search = useSearchParams();
  const router = useRouter();
  const query = search.get("q") || "";
  const group = search.get("group") || "";
  const ordering = search.get("ordering") === "updated_at" ? "updated_at" : "-updated_at";
  const params = new URLSearchParams({ q: query, ordering, group, page: String(adminPageNumber(search.get("page"))) });
  const resource = useApiResource<DraftPage>(`/catalog/admin/curation-drafts/?${params}`, getServerSessionCredential());
  const page = resource.data;
  const [selectedId, setSelectedId] = useState("");
  const selected = page?.results.find(item => item.id === selectedId) ?? page?.results[0];
  const returnTo = `${pathname}?${search}`;
  const change = (values: Record<string, string | number | null>) => router.push(adminListHref(pathname, search.toString(), { page: 1, ...values }));
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    change({ q: String(new FormData(event.currentTarget).get("q") || "").trim() });
  }
  return <section className="admin-reference-split curation-reference" aria-label="策展草稿"><div className="admin-reference-list">
    <nav className="reference-draft-tabs" aria-label="草稿分类">{Object.entries(groups).map(([key,label])=><button type="button" key={key} aria-pressed={(group||"all")===key} onClick={()=>change({group:key==="all" ? null : key})}>{label} {page?.counts[key as keyof typeof groups] ?? "—"}</button>)}</nav>
    <details className="reference-list-filters" open={Boolean(query || ordering==="updated_at")}><summary>搜索与排序</summary><form className={styles.toolbar} onSubmit={submit}>
      <label>名称或标题<input key={query} name="q" type="search" defaultValue={query} placeholder="搜索全部策展草稿" /></label>
      <label>排序<select value={ordering} onChange={event => change({ ordering: event.target.value })}><option value="-updated_at">最近更新在前</option><option value="updated_at">较早更新在前</option></select></label>
      <button className="button" type="submit">搜索</button><button className="button secondary" type="button" onClick={resource.retry}><RefreshCw size={14} />刷新草稿</button>
    </form></details>
    {resource.error ? <div className={styles.error} role="alert">{resource.error}<button type="button" onClick={resource.retry}>重新读取策展草稿</button></div> : null}
    <p className={styles.count} role="status">{resource.loading ? "正在读取策展草稿…" : page ? `当前条件共 ${page.count} 项，第 ${page.page} 页显示 ${page.results.length} 项。` : "草稿数量未能读取。"}</p>
    <div className="admin-v307-review-table">
      <header><span>标题</span><span>修改了哪一块</span><span>保存时间</span><span>操作</span></header>
      {page?.results.map(item => {
        const destination = safeAdminHref(item.edit_url, "");
        return <article key={item.id} data-record-id={item.id} className={selected?.id === item.id ? "selected" : ""}><div><button type="button" className="reference-select-title" aria-pressed={selected?.id === item.id} onClick={() => setSelectedId(item.id)}>{item.title || "未命名草稿"}</button><small>{item.label || "—"}</small></div><div title={item.changed_fields?.join("、")}>{changeSummary(item.changed_fields || [])}</div><div><time>{new Date(item.updated_at).toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong" })}</time></div><div>{item.can_edit && destination ? <Link className="button" href={withAdminReturn(destination, returnTo)}>继续编辑</Link> : <span>{item.can_edit ? "编辑位置待核实" : "当前账户只读"}</span>}</div></article>;
      })}
      {page && !page.results.length ? <p className="admin-list-state">当前条件下没有策展草稿。可以调整搜索，或从学者、主题、理论、网站与推荐栏目新建。</p> : null}
    </div>
    {page ? <Pagination className={styles.pagination} label="策展草稿分页" page={page.page} totalPages={page.total_pages} previousHref={adminListHref(pathname, search.toString(), { page: Math.max(1, page.page - 1) })} nextHref={adminListHref(pathname, search.toString(), { page: Math.min(page.total_pages, page.page + 1) })} /> : null}
  </div><CurationSelectionPreview key={selected?.id || "empty"} item={selected} returnTo={returnTo}/></section>;
}

const previewTypes: Record<string, string> = { scholar_profile: "scholar", topic: "topic", knowledge_node: "theory", discipline: "discipline", subdiscipline: "subdiscipline", reading_path: "reading_path" };

export function CurationSelectionPreview({ item, returnTo, presentation }: { item?: Pick<CurationDraft, "object_type" | "object_id" | "title" | "label" | "edit_url" | "can_edit"> & Partial<Pick<CurationDraft, "changed_fields">>; returnTo: string; presentation?: "topic" }) {
  const topicReference = presentation === "topic";
  const type = item && previewTypes[item.object_type];
  const resource = useApiResource<KnowledgePreviewPayload>(type && item ? `/catalog/admin/knowledge-preview/${type}/${item.object_id}/` : "", getServerSessionCredential());
  const issue = useApiResource<RecommendationIssue>(item?.object_type==="recommendation_issue" ? `/catalog/admin/recommendation-issues/${item.object_id}/` : "",getServerSessionCredential());
  const [perspective, setPerspective] = useState<"draft" | "published">("draft");
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [moduleId, setModuleId] = useState("");
  const [previewPage, setPreviewPage] = useState("overview");
  const data = resource.data;
  const changes = useMemo(() => data ? curationPreviewChanges(data, item?.changed_fields || []) : [], [data, item?.changed_fields]);
  const selectedChange = changes.find(change => change.module_id === moduleId) || changes[0];
  const surface = data?.perspectives[perspective];
  const anchorQuery = topicReference ? `?${new URLSearchParams({page:previewPage})}` : selectedChange ? `?${new URLSearchParams({ page: selectedChange.pageId, module: selectedChange.preview_anchor || selectedChange.module_id })}` : "";
  const href = perspective === "published" ? (data?.perspectives.published.available ? data.preview_routes.published : "") || (issue.data?.public_url?.startsWith("/recommendations/") ? issue.data.public_url : "") || (item?.object_type === "site_content" ? "/about" : "") : type && item ? `/admin/preview/knowledge/${type}/${item.object_id}${anchorQuery}` : item?.object_type === "recommendation_issue" ? `/admin/recommendations/issues/${item.object_id}/preview` : item?.object_type === "site_content" ? "/admin/about/preview" : "";
  const frameHref = !type && href ? href.startsWith("/admin/") ? `${href}?embed=1` : href : "";
  const edit = item && safeAdminHref(item.edit_url, "");
  return <aside className="selected-work-preview curation-selection-preview" aria-label="选中内容的读者预览">
    <header><h2>{topicReference ? "已保存内容预览" : "选中内容的读者预览"}</h2><p>{topicReference ? "这是读者会看到的主题页面效果。" : "对比修改后的效果，确认无误后继续编辑。"}</p>{topicReference ? <Link className="topic-preview-return button secondary" href={returnTo}><ArrowLeft size={15}/>返回主题列表</Link> : null}</header>
    <div className="selected-preview-tools">{topicReference ? <strong>读者会看到什么</strong> : null}<div role="group" aria-label="预览内容">{(["draft", "published"] as const).map(value => <button type="button" key={value} aria-pressed={perspective === value} disabled={topicReference && value === "published" && !data?.perspectives.published.available} onClick={() => setPerspective(value)}>{value === "draft" ? "修改后" : "当前线上"}</button>)}</div><div role="group" aria-label="预览尺寸"><button type="button" aria-pressed={device === "desktop"} onClick={() => setDevice("desktop")}><Monitor size={15}/>电脑</button><button type="button" aria-pressed={device === "mobile"} onClick={() => setDevice("mobile")}><Smartphone size={15}/>手机</button></div>{href ? <Link href={href} target="_blank"><Maximize2 size={15}/>放大查看</Link> : null}</div>
    <div className={`selected-preview-caption ${comparisonStyles.caption}`}>{topicReference ? <label>当前预览：<select aria-label="主题预览位置" value={previewPage} onChange={event=>setPreviewPage(event.target.value)}>{[["overview","主题首页"],["questions","研究问题"],["works","入门阅读"],["scholars","代表学者"]].map(([value,label])=><option value={value} key={value}>{label}{item ? `（${item.title}）` : ""}</option>)}</select></label> : <><span>{item ? `当前查看：${item.label} › ${item.title}` : "选择待发布的页面修改"}</span>{selectedChange ? <><span>›</span>{changes.length > 1 ? <select aria-label="查看修改区域" value={selectedChange.module_id} onChange={event => setModuleId(event.target.value)}>{changes.map(change => <option value={change.module_id} key={change.module_id}>{change.display_name}</option>)}</select> : <span>{selectedChange.display_name}</span>}</> : null}{item ? <small>{perspective === "draft" ? "已保存草稿 · 尚未发布" : "当前线上内容"}</small> : null}</>}</div>
    {issue.error ? <p role="alert">{issue.error}<button type="button" onClick={issue.retry}>重新读取文章公开状态</button></p> : null}
    {resource.error ? <p role="alert">{resource.error}<button type="button" onClick={resource.retry}>重新读取预览</button></p> : null}
    <div className={`selected-preview-viewport ${device}`}>
      {type && resource.loading ? <p role="status">正在读取已保存内容…</p> : data && surface?.available ? <><PreviewViewport device={device}>{topicReference ? <div inert><PreviewSurface payload={{...data,active_perspective:perspective,perspective:surface}} pageId={previewPage}/></div> : <CurationPreviewComparison payload={data} change={selectedChange} perspective={perspective}/>}</PreviewViewport>{surface.unsupported_preview_fields?.length ? <p role="status">以下内容尚未提供预览：{surface.unsupported_preview_fields.join("、")}</p> : null}</> : frameHref ? <PreviewViewport device={device}><iframe src={frameHref} title={`${item?.title || "选中页面"}预览`} style={{ width: "100%", height: 1100, border: 0 }}/></PreviewViewport> : <p className="empty-state">—</p>}
    </div>
    {!topicReference && item?.can_edit && edit ? <footer><Link className="button" href={withAdminReturn(edit, returnTo)}>打开该页面继续编辑</Link></footer> : null}
  </aside>;
}
