"use client";

import { ArrowRight, ExternalLink, FileClock, LoaderCircle, RefreshCw, Search } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { ActionButton, type ActionState } from "./action-feedback";
import { CurationFieldAssistant } from "./admin/curation/curation-field-assistant";
import { PublicationRetryControl } from "./admin/workflow/publication-retry-control";
import { normalizeEvidenceEnvelope } from "./admin/research/evidence-envelope";
import type { ClaimRow, KnowledgePayload, RevisionRow, StudioSelection } from "./knowledge-workspace-diagnostics";

const objectLabels: Record<string, string> = {
  all: "全部对象", theory: "理论传统", concept: "概念", debate: "争论", research_problem: "研究问题",
  scholar: "学者", discipline: "学科", subdiscipline: "子学科", topic: "主题", reading_path: "阅读路径", work: "作品",
};
const statusLabels: Record<string, string> = {
  pending: "待确认", draft: "草稿", published: "已发布", archived: "已撤回", withdrawn: "已撤回",
  verified: "已确认", needs_review: "需要核对", accepted: "已采用", rejected: "未采用", superseded: "已取代",
  ready: "可以发布", current: "已更新", stale: "需要重新检查", projecting: "智能内容处理中", failed: "智能处理异常",
  approved: "已确认", suggested: "待确认", active: "已生效", confirmed: "已确认",
};
const fieldLabels: Record<string, string> = {
  canonical_name_zh: "名称", canonical_name_en: "外文名", name: "名称", preferred_name: "中文名", original_name: "外文名",
  summary: "简介", definition: "定义", description: "说明", short_description: "简述", biography: "学者介绍",
  problem_statement: "核心问题", core_questions: "核心问题", basic_propositions: "基本观点", theoretical_boundary: "理论边界",
  research_dimensions: "研究维度", methods: "研究方法", formation_context: "形成背景", key_concepts: "核心概念",
  key_concerns: "主要关切", affiliations: "机构", affiliation: "机构", timeline: "学术经历", featured_quote: "代表性引文",
  quote_source: "引文来源", aliases: "别名", alias: "别名", name_variants: "别名与译名", name_variant: "别名与译名",
  birth_year: "出生年份", death_year: "逝世年份", period: "时期", primary_discipline: "所属学科", foreign_name: "外文名",
  discipline: "所属学科", subdiscipline: "子学科", parent: "上级分类", research_object: "研究对象", formation_period: "形成时期",
  research_directions: "研究方向", representative_issues: "代表议题", title: "标题", canonical_title: "规范标题", uniform_title: "规范标题",
  subtitle: "副标题", original_title: "原文标题", abstract: "简介", document_type: "资源类型", language: "语言", original_language: "原文语言",
  first_publication_date: "首次出版日期", editions: "版本", audience: "适合读者", difficulty: "阅读难度",
  estimated_reading: "预计阅读量", stages: "阅读阶段", introduction: "路径介绍", learning_goal: "学习目标", relation: "相关理论与概念",
  timeline_fact: "发展事件", timeline_interpretation: "发展说明", item: "阅读内容", core_viewpoint: "核心观点", major_criticism: "主要批评", major_response: "主要回应",
};
const valueLabels: Record<string, string> = {
  book: "图书", journal_article: "期刊论文", journal_issue: "整期期刊", thesis: "学位论文", report: "报告",
  zh: "中文", "zh-CN": "中文", en: "英文", fr: "法文", de: "德文", ja: "日文",
  beginner: "入门", intermediate: "进阶", advanced: "深入", introductory: "入门",
};

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function fieldText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "尚未填写";
  if (typeof value === "string") {
    if (/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(value)) return "已选择馆内对象，可在完整编辑中核对";
    return valueLabels[value] || value;
  }
  if (typeof value === "number") return String(value);
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value)) return value.length ? value.map(fieldText).join("、") : "尚未填写";
  const row = asRecord(value);
  // Only present bibliographic labels, never raw IDs, scores or source payloads.
  const named = row.label || row.name || row.alias || row.title || row.canonical_name_zh || row.preferred_name || row.stage_name || row.proposition;
  if (named) return fieldText(named);
  if (row.edition_statement || row.publisher || row.publication_year) return [row.edition_statement, row.publisher, row.publication_year].filter(Boolean).map(fieldText).join("，");
  if (row.start_year || row.end_year) return [row.start_year, row.end_year].filter(Boolean).map(fieldText).join("至");
  return "已保存详细内容，可在完整编辑中核对";
}

type FieldConfig = { key: string; fieldName?: string; valueKey?: string; relationKinds?: string[]; lookupLabel?: string; editorUrl?: string };

const assistantFields: Record<string, FieldConfig[]> = {
  work: [
    ...["title", "subtitle", "original_title", "abstract", "first_publication_date"].map((key) => ({ key, fieldName: key })),
    { key: "canonical_title", fieldName: "uniform_title", valueKey: "uniform_title" },
    { key: "discipline", fieldName: "discipline", relationKinds: ["work_discipline"], lookupLabel: "获取分类建议" },
    { key: "subdiscipline", fieldName: "subdiscipline", relationKinds: ["work_subdiscipline"], lookupLabel: "获取分类建议" },
  ],
  person: [
    { key: "name_variant", fieldName: "name_variant", valueKey: "name_variants" },
    { key: "affiliations", fieldName: "affiliation" },
  ],
  knowledge_node: [
    { key: "aliases", fieldName: "alias" },
    { key: "primary_discipline", fieldName: "discipline", relationKinds: ["node_discipline"], lookupLabel: "获取分类建议" },
    { key: "subdiscipline", fieldName: "subdiscipline", relationKinds: ["node_subdiscipline"], lookupLabel: "获取分类建议" },
    { key: "relation", fieldName: "relation", relationKinds: ["knowledge_relation"], lookupLabel: "推荐关联", editorUrl: "/admin/theory-relations" },
    { key: "timeline_fact", fieldName: "timeline_fact", editorUrl: "/admin/theory-timeline" },
    { key: "timeline_interpretation", fieldName: "timeline_interpretation", editorUrl: "/admin/theory-timeline" },
  ],
  topic: [{ key: "discipline", fieldName: "discipline", relationKinds: ["topic_discipline"], lookupLabel: "获取分类建议" }],
  discipline: [{ key: "foreign_name", fieldName: "foreign_name" }],
  subdiscipline: [{ key: "foreign_name", fieldName: "foreign_name" }],
  reading_path: [{ key: "stages", fieldName: "item", lookupLabel: "推荐阅读内容" }],
};
const claimFields = ["core_viewpoint", "major_criticism", "major_response"];

function ReaderEvidence({ evidence }: { evidence: unknown }) {
  const row = normalizeEvidenceEnvelope(evidence);
  return <article className="admin-evidence-envelope is-compact">
    <header><strong>{row.title}</strong>{row.stale ? <span>资料需要重新核对</span> : null}</header>
    <blockquote>{row.text}</blockquote>
    <div className="admin-evidence-locator">{row.page ? <span>第 {row.page} 页</span> : null}{row.section ? <span>{row.section}</span> : null}</div>
    <footer>{row.readerUrl ? <a href={row.readerUrl} target="_blank" rel="noreferrer">查看馆藏原文 <ExternalLink size={12} /></a> : row.sourceUrl ? <a href={row.sourceUrl} target="_blank" rel="noreferrer">查看资料 <ExternalLink size={12} /></a> : null}</footer>
  </article>;
}

function ConfirmedClaim({ claim }: { claim: ClaimRow }) {
  const evidence = Array.isArray(claim.evidence) ? claim.evidence : claim.evidence ? [claim.evidence] : [];
  return <article className="knowledge-studio-claim-card"><header><strong>{claim.title || fieldLabels[claim.kind || ""] || "馆藏观点"}</strong><span>{statusLabels[claim.status || ""] || "需要核对"}</span></header>
    <p>{claim.proposition}</p>
    {evidence.length ? <details><summary>查看依据</summary>{evidence.map((item, index) => <ReaderEvidence key={`${claim.id}:${index}`} evidence={item} />)}</details> : null}
  </article>;
}

function ObjectFields({ selection, onRefresh, publishing, publishState, onPublish }: {
  selection: StudioSelection; onRefresh: () => Promise<void>; publishing: string; publishState: ActionState; onPublish: (row: RevisionRow) => void;
}) {
  const target = selection.field_assistant_target;
  const current = { ...selection.canonical, ...selection.preview?.materialized };
  // A scholar's nested Person patch must be shown instead of stale saved values.
  if (selection.object_type === "scholar") Object.assign(current, asRecord(current.person));
  const configs = target ? assistantFields[target.object_type] || [] : [];
  const configuredKeys = new Set(configs.flatMap((row) => [row.key, row.valueKey || row.key]));
  const fields: FieldConfig[] = [
    ...Object.keys(current).filter((key) => fieldLabels[key] && !configuredKeys.has(key) && key !== "name_variants" && key !== "aliases").map((key) => ({ key })),
    ...configs,
  ];
  if (!configs.some((row) => row.key === "aliases") && current.aliases) fields.push({ key: "aliases" });
  const claims = selection.claims?.curated || [];
  const revisions = selection.revisions || [];
  const relations = selection.relations || [];
  const canEdit = !["archived", "withdrawn", "rejected"].includes(selection.status);
  const hasDraft = selection.preview?.source === "editorial_revision" || selection.status === "draft";
  const curationEditor = selection.related_editor_urls?.find((row) => row.label === "知识策展")?.url || selection.editor_url;
  const publicationEdition = selection.object_type === "work"
    ? new URLSearchParams((selection.editor_url?.split("?")[1] || "").split("#")[0]).get("edition")
    : null;
  const publicationObjectType = selection.object_type === "scholar" ? "scholar_profile" : target?.object_type;
  const fieldValue = (field: FieldConfig) => Object.hasOwn(selection.field_assistant_values || {}, field.key)
    ? selection.field_assistant_values?.[field.key] : field.relationKinds
    ? relations.filter((row) => field.relationKinds?.includes(row.kind)).map((row) => row.target)
    : current[field.valueKey || field.key] ?? current[field.key];

  return <section className="knowledge-studio-detail" aria-label={`${selection.label}字段编辑`}>
    <header className="knowledge-studio-object-header">
      <div><p>{objectLabels[selection.object_type] || "知识对象"}</p><h2>{selection.label}</h2><span className={`status-badge ${selection.status}`}>{statusLabels[selection.status] || "需要核对"}</span></div>
      <div>{selection.editor_url ? <Link className="button" href={selection.editor_url}>完整编辑 <ArrowRight size={14} /></Link> : null}
        {selection.preview_routes?.draft ? <Link className="button secondary" href={selection.preview_routes.draft} target="_blank">前台草稿预览 <ExternalLink size={14} /></Link> : null}
        {selection.preview_routes?.published ? <Link className="button secondary" href={selection.preview_routes.published} target="_blank">查看公开页面 <ExternalLink size={14} /></Link> : null}</div>
    </header>
    <p className="knowledge-studio-boundary-note">{hasDraft ? "当前显示待发布的编辑内容。" : "当前显示已保存内容。"}采用建议只保存草稿，正式发布后才更新公开知识。可以按任意顺序处理字段。</p>
    {publicationEdition || (publicationObjectType && publicationObjectType !== "work") ? <PublicationRetryControl
      key={`${selection.object_type}:${publicationEdition || selection.id}`} editionId={publicationEdition || undefined}
      objectTarget={publicationObjectType && publicationObjectType !== "work" ? { objectType: publicationObjectType, objectId: selection.id } : undefined}
      token={getServerSessionCredential()} refreshKey={JSON.stringify([selection.status, revisions])} onCompleted={onRefresh}
    /> : null}
    <nav className="knowledge-studio-section-nav" aria-label="对象内容导航"><a href="#studio-fields">资料字段</a><a href="#studio-viewpoints">观点</a><a href="#studio-relations">馆内关联</a><a href="#studio-publication">发布与记录</a></nav>

    <section className="admin-panel" id="studio-fields"><header><h3>资料字段</h3><span>在对应字段查找建议或进入完整编辑</span></header>
      <div className="knowledge-studio-list">{fields.map((field) => <article key={field.key}>
        <header><strong>{fieldLabels[field.key]}</strong><div>
          {target && field.fieldName && canEdit ? <CurationFieldAssistant label={fieldLabels[field.key]} targetType={target.object_type} targetId={target.object_id} fieldName={field.fieldName} query={selection.label} currentValue={fieldValue(field)} formContext={current} lookupLabel={field.lookupLabel || "查找建议"} onAccepted={onRefresh} /> : null}
          {selection.editor_url ? <Link className="button secondary" href={field.editorUrl || selection.editor_url}>编辑{fieldLabels[field.key]}</Link> : null}
        </div></header><p>{fieldText(fieldValue(field))}</p>
      </article>)}</div>
      {!fields.length ? <p className="admin-list-state">尚未取得字段内容，请进入完整编辑核对。</p> : null}
    </section>

    <section className="admin-panel" id="studio-viewpoints"><header><h3>观点与讨论</h3><span>核对馆藏原文后确认</span></header>
      {selection.object_type === "work" ? claimFields.map((kind) => <section key={kind} className="knowledge-studio-list">
        <header><h4>{fieldLabels[kind]}</h4>{target && canEdit ? <CurationFieldAssistant label={fieldLabels[kind]} targetType="work" targetId={target.object_id} fieldName={kind} query={selection.label} currentValue={claims.filter((row) => row.kind === kind).map((row) => row.proposition)} lookupLabel="查找建议" onAccepted={onRefresh} /> : null}</header>
        {claims.filter((row) => row.kind === kind).map((claim) => <ConfirmedClaim claim={claim} key={claim.id} />)}
        {!claims.some((row) => row.kind === kind) ? <p className="admin-list-state">尚未确认{fieldLabels[kind]}。可以查看建议，或在完整编辑中补充。</p> : null}
      </section>) : <>{claims.map((claim) => <ConfirmedClaim claim={claim} key={claim.id} />)}{!claims.length ? <p className="admin-list-state">暂无已确认的馆藏观点，可在完整编辑中核对相关作品与观点。</p> : null}</>}
      {curationEditor ? <Link className="button secondary" href={curationEditor}>编辑观点与讨论 <ArrowRight size={14} /></Link> : null}
    </section>

    <section className="admin-panel" id="studio-relations"><header><h3>馆内关联</h3><span>主题、理论、学者与作品</span></header>
      <div className="knowledge-studio-list">{relations.map((row) => <article key={`${row.kind}:${row.id}`}><div><strong>{row.target}</strong><span>{statusLabels[row.status] || "需要核对"}</span></div><p>{row.label}</p></article>)}{!relations.length ? <p className="admin-list-state">尚未建立馆内关联。可从上面的分类字段查找建议，或在完整编辑中添加。</p> : null}</div>
      <nav>{selection.editor_url ? <Link className="button secondary" href={selection.editor_url}>编辑馆内关联</Link> : null}{selection.related_editor_urls?.map((row) => <Link className="button secondary" href={row.url} key={row.url}>{row.label}<ArrowRight size={13} /></Link>)}</nav>
    </section>

    <section className="admin-panel" id="studio-publication"><header><h3><FileClock size={16} />发布与记录</h3><span>{selection.frontend_impact?.public_visibility ? "当前有公开版本" : "当前尚未公开"}</span></header>
      <p className="knowledge-studio-boundary-note">已发布内容的修改会保存在新草稿中。新内容处理完成前，原有稳定版本继续服务。</p>
      <div className="knowledge-studio-list">{revisions.map((row) => <article key={row.id}>
        <div><strong>第 {row.revision} 次编辑</strong><span>{row.has_conflict ? "内容存在冲突，请重新核对" : statusLabels[row.status] || "需要核对"}</span></div>
        <p>{Array.from(new Set(row.changed_fields.map((key) => fieldLabels[key] || fieldLabels[key.split(".").at(-1) || ""] || "关联内容"))).join("、") || "资料内容"}</p>
        {row.publish_url && !row.has_conflict && canEdit ? <ActionButton className="button" disabled={Boolean(publishing)} state={publishing === row.id ? publishState : "idle"} pendingLabel="正在提交发布" successLabel="已提交发布" onClick={() => onPublish(row)}>确认发布本次编辑</ActionButton> : null}
      </article>)}</div>
      {!revisions.length ? <p className="admin-list-state">暂无独立编辑记录。请在完整编辑中核对内容并发布。</p> : null}
      {selection.editor_url ? <Link className="button secondary" href={selection.editor_url}>检查并发布</Link> : null}
    </section>
  </section>;
}

export function KnowledgeWorkspace() {
  const [payload, setPayload] = useState<KnowledgePayload | null>(null);
  const [objectType, setObjectType] = useState("all");
  const [selected, setSelected] = useState<{ type: string; id: string } | null>(null);
  const [queryDraft, setQueryDraft] = useState("");
  const [query, setQuery] = useState("");
  const [initialized, setInitialized] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [publishing, setPublishing] = useState("");
  const [publishState, setPublishState] = useState<ActionState>("idle");
  const [refreshVersion, setRefreshVersion] = useState(0);
  const requestRef = useRef<AbortController | null>(null);
  const mounted = useRef(false);
  const selectedType = selected?.type || "";
  const selectedId = selected?.id || "";
  const contextKey = JSON.stringify([objectType, query, selectedType, selectedId, refreshVersion]);
  const contextRef = useRef(contextKey);
  contextRef.current = contextKey;

  useEffect(() => {
    mounted.current = true;
    const readLocation = () => {
      const params = new URLSearchParams(window.location.search);
      const kind = params.get("object_type") || "all";
      const id = params.get("object_id") || "";
      const validKind = Object.hasOwn(objectLabels, kind) ? kind : "all";
      setObjectType(validKind);
      setSelected(validKind !== "all" && id ? { type: validKind, id } : null);
      setPayload(null);
      setLoading(true);
      setRefreshVersion((value) => value + 1);
      setInitialized(true);
    };
    readLocation();
    window.addEventListener("popstate", readLocation);
    return () => { mounted.current = false; requestRef.current?.abort(); window.removeEventListener("popstate", readLocation); };
  }, []);

  const load = useCallback(async () => {
    if (!initialized || !mounted.current || contextRef.current !== contextKey) return;
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setLoading(true);
    try {
      const params = new URLSearchParams({ status: "pending", object_type: objectType, q: query, limit: "40" });
      if (selectedId) { params.set("selected_type", selectedType); params.set("selected_id", selectedId); }
      const next = await apiRequest<KnowledgePayload>(`/catalog/admin/knowledge-workspace/?${params}`, { signal: controller.signal }, getServerSessionCredential());
      if (!controller.signal.aborted) { setPayload(next); setMessage(""); }
    } catch (reason) {
      if (!controller.signal.aborted) setMessage(reason instanceof Error ? reason.message : "暂时无法读取知识对象，请重试。");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [initialized, objectType, query, selectedId, selectedType, contextKey]);

  useEffect(() => {
    void load();
    return () => requestRef.current?.abort();
  }, [load]);

  function choose(kind: string, id = "") {
    requestRef.current?.abort();
    setObjectType(kind);
    setSelected(id ? { type: kind, id } : null);
    setPayload(null);
    setLoading(true);
    setRefreshVersion((value) => value + 1);
    const url = new URL(window.location.href);
    url.searchParams.set("object_type", kind);
    if (id) url.searchParams.set("object_id", id); else url.searchParams.delete("object_id");
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    choose(objectType);
    setQuery(queryDraft.trim());
  }

  async function publish(row: RevisionRow) {
    if (!row.publish_url || publishing) return;
    setPublishing(row.id);
    setPublishState("pending");
    try {
      await apiRequest(row.publish_url, { method: "POST", body: "{}" }, getServerSessionCredential());
      if (!mounted.current) return;
      await load();
      setPublishState("success");
      setMessage("本次编辑已提交发布，智能内容将按变化范围更新。");
    } catch (reason) {
      if (mounted.current) { setPublishState("error"); setMessage(reason instanceof Error ? reason.message : "发布未提交成功，请重试。"); }
    } finally {
      if (mounted.current) setPublishing("");
    }
  }

  const studio = payload?.studio;
  const current = studio?.selection;
  return <div className="admin-page knowledge-studio">
    <header className="admin-page-title"><div><p>知识策展</p><h1>馆内知识</h1><span>选择对象，在具体字段核对资料、采用建议和完善关联。草稿只有正式发布后才进入公开知识。</span></div>
      <div className="admin-title-actions"><button className="button secondary" disabled={loading} type="button" onClick={() => void load()}><RefreshCw size={15} className={loading ? "spin" : ""} />刷新</button><Link className="button secondary" href={current ? `/admin/system-health/knowledge?object_type=${encodeURIComponent(current.object_type)}&object_id=${encodeURIComponent(current.id)}` : "/admin/system-health/knowledge"}>系统诊断</Link></div></header>
    <nav className="knowledge-studio-quick-links" aria-label="完整策展页面"><Link href="/admin/theories">理论与概念</Link><Link href="/admin/scholars">学者</Link><Link href="/admin/topics">主题</Link><Link href="/admin/disciplines">学科</Link><Link href="/admin/subdisciplines">子学科</Link><Link href="/admin/reading-paths">阅读路径</Link></nav>
    <form className="admin-toolbar knowledge-studio-toolbar" onSubmit={submitSearch}>
      <label><span>对象类型</span><select value={objectType} onChange={(event) => choose(event.target.value)}>{Object.entries(objectLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label className="knowledge-studio-search"><span>名称</span><div><Search size={15} /><input value={queryDraft} onChange={(event) => setQueryDraft(event.target.value)} placeholder="搜索馆内对象" /></div></label><button className="button" type="submit">搜索</button>
    </form>
    {message ? <p className="form-message" role="status">{message}</p> : null}
    {loading && !payload ? <p className="admin-list-state"><LoaderCircle size={17} className="spin" />正在读取馆内资料</p> : null}
    {studio ? <div className="knowledge-studio-layout">
      <aside className="admin-panel knowledge-studio-directory"><header><h2>馆内对象</h2><span>最多显示 {studio.filters.limit} 项</span></header><div>{studio.objects.map((row) => <button key={`${row.object_type}:${row.id}`} className={current?.id === row.id && current.object_type === row.object_type ? "active" : ""} type="button" onClick={() => choose(row.object_type, row.id)}><span>{objectLabels[row.object_type] || "知识对象"}</span><strong>{row.label}</strong><small>{row.secondary_label || statusLabels[row.status] || "需要核对"}</small><ArrowRight size={14} /></button>)}{!studio.objects.length ? <p className="admin-list-state">当前筛选下没有对象。可到上方对应策展页面新建。</p> : null}</div></aside>
      {current ? <ObjectFields key={`${current.object_type}:${current.id}`} selection={current} onRefresh={load} publishing={publishing} publishState={publishState} onPublish={(row) => void publish(row)} /> : <section className="admin-panel knowledge-studio-empty"><h2>{studio.selection_error ? "无法找到指定对象" : "请选择馆内对象"}</h2><p>{studio.selection_error ? "请检查作品入口或重新搜索，没有显示其他对象作为替代。" : "选择后可以核对资料字段和馆内关联。"}</p></section>}
    </div> : null}
  </div>;
}
