"use client";

import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  BookOpen,
  Check,
  Clock3,
  ExternalLink,
  FileText,
  GitMerge,
  History,
  ImagePlus,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import type { FormEvent, KeyboardEvent, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { EntityLifecycleActions } from "@/components/entity-lifecycle-actions";
import { ResearchEntityPicker } from "@/components/admin/research/research-entity-picker";
import type { EntityValue } from "@/components/admin/forms/workflow-fields";
import { FieldEnrichmentControl } from "@/components/field-enrichment-control";
import {
  AuthoritySuggestions,
  StringListEditor,
  StructuredRowsEditor,
} from "@/components/structured-editors";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useActionGuard } from "@/lib/use-action-guard";
import { ActionButton, AsyncStatus, type ActionState } from "@/components/action-feedback";

type Page<T> = { count: number; next?: string | null; previous?: string | null; results: T[] };

function onePickerValue(id: string, name: string): EntityValue[] {
  return id ? [{ id, name: name || "已选择实体" }] : [];
}

function manyPickerValues(ids: string[], nameFor: (id: string) => string): EntityValue[] {
  return ids.map((id) => ({ id, name: nameFor(id) || "已选择实体" }));
}

function pickerLabels(values: EntityValue[]): Record<string, string> {
  return Object.fromEntries(values.flatMap((value) => value.id ? [[value.id, value.name]] : []));
}

type Discipline = {
  id: string;
  name: string;
  foreign_name?: string;
  slug: string;
};

type NodeAlias = {
  id?: string;
  alias: string;
  language: string;
  alias_type: string;
};

type NodeDisciplineLink = {
  id?: string;
  discipline: Discipline;
  relation_type: "primary" | "related" | "transferred";
  discipline_specific_summary: string;
  sort_order: number;
  status: string;
};

type KnowledgeNode = {
  id: string;
  node_type: string;
  canonical_name_zh: string;
  canonical_name_en: string;
  slug: string;
  summary: string;
  definition: string;
  core_questions: string[];
  basic_propositions: string[];
  theoretical_boundary: string;
  start_year: number | null;
  end_year: number | null;
  period_label: string;
  parent: string | null;
  primary_discipline: string | null;
  primary_discipline_data: Discipline | null;
  status: string;
  sort_order: number;
  aliases: NodeAlias[];
  discipline_links: NodeDisciplineLink[];
  work_count: number;
  relation_count: number;
  cover_url: string;
  updated_at: string;
};

type WorkCompact = {
  id: string;
  title: string;
  document_type?: string;
  author?: string;
  slug?: string;
};

type ScholarCompact = {
  id: string;
  preferred_name: string;
  slug?: string;
};

const nodeTypeLabels: Record<string, string> = {
  theory_tradition: "理论传统",
  subdiscipline: "子学科",
  concept: "核心概念",
  debate: "理论争论",
  research_problem: "研究问题",
};

const statusLabels: Record<string, string> = {
  draft: "草稿",
  pending: "待审核",
  published: "已发布",
  rejected: "已拒绝",
  archived: "已下线",
  suggested: "候选",
  approved: "已发布",
  confirmed: "已确认",
  needs_changes: "待修改",
  deferred: "延后处理",
  insufficient_evidence: "证据不足",
};

function lines(value: string) {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

function editorLines(value: string) {
  return value === "" ? [] : value.split(/\r?\n/);
}

function asDate(value?: string | null) {
  if (!value) return "尚未记录";
  return new Date(value).toLocaleString("zh-CN", {
    hour12: false,
    timeZone: "Asia/Hong_Kong",
  });
}

function activateOnEnterOrSpace(
  event: KeyboardEvent<HTMLElement>,
  activate: () => void,
) {
  if (event.target !== event.currentTarget) return;
  if (event.key !== "Enter" && event.key !== " ") return;
  event.preventDefault();
  activate();
}

function useAdminData<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    if (!path) return;
    let active = true;
    const token = getServerSessionCredential();
    if (!token) return;
    Promise.resolve()
      .then(() => {
        if (!active) return null;
        setLoading(true);
        return apiRequest<T>(path, {}, token);
      })
      .then((payload) => {
        if (!active || !payload) return;
        setData(payload);
        setError("");
      })
      .catch((reason) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "读取失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [path, revision]);

  return { data, loading: path ? loading : false, error, refresh };
}

function AdminFrame({ eyebrow, title, description, actions, children }: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="admin-page theory-system-admin">
      <header className="admin-page-title theory-admin-title">
        <div><p>{eyebrow}</p><h1>{title}</h1><span>{description}</span></div>
        {actions ? <div className="theory-admin-title-actions">{actions}</div> : null}
      </header>
      {children}
    </div>
  );
}

function StatusBadge({ value }: { value: string }) {
  return <span className={`theory-status-badge status-${value}`}>{statusLabels[value] || value}</span>;
}

function ErrorNotice({ message, retry }: { message?: string; retry?: () => void }) {
  if (!message) return null;
  return <div className="theory-admin-error" role="alert"><span>{message}</span>{retry ? <button type="button" onClick={retry}>重试</button> : null}</div>;
}

type NodeDraft = {
  node_type: string;
  canonical_name_zh: string;
  canonical_name_en: string;
  slug: string;
  aliases: Array<{ alias: string; language: string; alias_type: string }>;
  summary: string;
  definition: string;
  core_questions: string;
  basic_propositions: string;
  theoretical_boundary: string;
  start_year: string;
  end_year: string;
  period_label: string;
  parent: string;
  primary_discipline: string;
  related_disciplines: string[];
  status: string;
  sort_order: number;
};

const emptyNodeDraft: NodeDraft = {
  node_type: "theory_tradition",
  canonical_name_zh: "",
  canonical_name_en: "",
  slug: "",
  aliases: [],
  summary: "",
  definition: "",
  core_questions: "",
  basic_propositions: "",
  theoretical_boundary: "",
  start_year: "",
  end_year: "",
  period_label: "",
  parent: "",
  primary_discipline: "",
  related_disciplines: [],
  status: "draft",
  sort_order: 0,
};

function nodeToDraft(node: KnowledgeNode): NodeDraft {
  return {
    node_type: node.node_type,
    canonical_name_zh: node.canonical_name_zh,
    canonical_name_en: node.canonical_name_en,
    slug: node.slug,
    aliases: node.aliases.map((item) => ({
      alias: item.alias,
      language: item.language || "zh-CN",
      alias_type: item.alias_type || "alias",
    })),
    summary: node.summary,
    definition: node.definition,
    core_questions: node.core_questions.join("\n"),
    basic_propositions: node.basic_propositions.join("\n"),
    theoretical_boundary: node.theoretical_boundary,
    start_year: node.start_year?.toString() ?? "",
    end_year: node.end_year?.toString() ?? "",
    period_label: node.period_label,
    parent: node.parent ?? "",
    primary_discipline: node.primary_discipline ?? "",
    related_disciplines: node.discipline_links
      .filter((item) => item.relation_type !== "primary")
      .map((item) => item.discipline.id),
    status: node.status,
    sort_order: node.sort_order,
  };
}

export function TheoryNodesAdmin() {
  const [nodeType, setNodeType] = useState("theory_tradition");
  const [legacyId, setLegacyId] = useState("");
  const [legacyOpened, setLegacyOpened] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [disciplineFilter, setDisciplineFilter] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<KnowledgeNode | null>(null);
  const [draft, setDraft] = useState<NodeDraft>(emptyNodeDraft);
  const [cover, setCover] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [messageState, setMessageState] = useState<ActionState>("idle");
  const { pendingAction, startAction, finishAction } = useActionGuard();
  const [entityLabels, setEntityLabels] = useState<Record<string, string>>({});
  const [versions, setVersions] = useState<Array<{ id: string; version_number: number; change_note: string; created_by_name: string; created_at: string }> | null>(null);
  const [mergeTarget, setMergeTarget] = useState("");

  const params = useMemo(() => {
    const search = new URLSearchParams({ node_type: nodeType });
    if (statusFilter) search.set("status", statusFilter);
    if (disciplineFilter) search.set("discipline", disciplineFilter);
    if (query.trim()) search.set("q", query.trim());
    if (legacyId) search.set("legacy_id", legacyId);
    return search.toString();
  }, [nodeType, statusFilter, disciplineFilter, query, legacyId]);
  const nodes = useAdminData<Page<KnowledgeNode>>(`/catalog/admin/theory-system/nodes/?${params}`);
  const allNodes = useAdminData<Page<KnowledgeNode>>("/catalog/admin/theory-system/nodes/");
  const disciplines = useAdminData<Page<Discipline>>("/catalog/admin/disciplines/");

  useEffect(() => {
    const search = new URLSearchParams(window.location.search);
    const requested = search.get("node_type");
    const requestedLegacyId = search.get("legacy_id") || "";
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      if (requested && Object.prototype.hasOwnProperty.call(nodeTypeLabels, requested)) {
        setNodeType(requested);
        setDraft((current) => ({ ...current, node_type: requested }));
      }
      setLegacyId(requestedLegacyId);
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const mapped = nodes.data?.results[0];
    if (!legacyId || legacyOpened || !mapped) return;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setEditing(mapped);
      setDraft(nodeToDraft(mapped));
      setCover(null);
      setMessage("已通过旧版映射打开规范节点。后续只需在本页维护。");
      setVersions(null);
      setMergeTarget("");
      setLegacyOpened(true);
    });
    return () => {
      active = false;
    };
  }, [legacyId, legacyOpened, nodes.data]);

  function start(node?: KnowledgeNode) {
    setEditing(node ?? null);
    setDraft(node ? nodeToDraft(node) : { ...emptyNodeDraft, node_type: nodeType, primary_discipline: disciplines.data?.results[0]?.id ?? "" });
    setCover(null);
    setMessage("");
    setMessageState("idle");
    setEntityLabels({});
    setVersions(null);
    setMergeTarget("");
  }

  async function saveNode(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = "save-theory-node";
    if (!startAction(actionKey)) return;
    setMessage("");
    setMessageState("pending");
    const aliases = draft.aliases
      .map((item) => ({
        alias: item.alias.trim(),
        language: item.language || "zh-CN",
        alias_type: item.alias_type || "alias",
      }))
      .filter((item) => item.alias);
    const discipline_links = draft.related_disciplines.map((discipline_id, index) => ({
      discipline_id,
      relation_type: "related",
      discipline_specific_summary: "",
      sort_order: index,
      status: draft.status === "published" ? "published" : "pending",
    }));
    const payload = {
      node_type: draft.node_type,
      canonical_name_zh: draft.canonical_name_zh,
      canonical_name_en: draft.canonical_name_en,
      slug: draft.slug,
      aliases,
      summary: draft.summary,
      definition: draft.definition,
      core_questions: lines(draft.core_questions),
      basic_propositions: lines(draft.basic_propositions),
      theoretical_boundary: draft.theoretical_boundary,
      start_year: draft.start_year ? Number(draft.start_year) : null,
      end_year: draft.end_year ? Number(draft.end_year) : null,
      period_label: draft.period_label,
      parent: draft.parent || null,
      primary_discipline: draft.primary_discipline || null,
      discipline_links,
      status: draft.status,
      sort_order: draft.sort_order,
    };
    try {
      const saved = await apiRequest<KnowledgeNode>(
        `/catalog/admin/theory-system/nodes/${editing ? `${editing.id}/` : ""}`,
        { method: editing ? "PATCH" : "POST", body: JSON.stringify(payload) },
        token,
      );
      if (cover) {
        const imageBody = new FormData();
        imageBody.append("cover_asset", cover);
        await apiRequest(`/catalog/admin/theory-system/nodes/${saved.id}/`, { method: "PATCH", body: imageBody }, token);
      }
      setEditing(saved);
      setDraft(nodeToDraft(saved));
      setMessage("节点已保存。公开页、学科页和局部图谱会从同一条规范记录读取。 ");
      setMessageState("success");
      nodes.refresh();
      allNodes.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "保存失败");
      setMessageState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  async function loadVersions() {
    if (!editing) return;
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = "load-node-versions";
    if (!startAction(actionKey)) return;
    try {
      const payload = await apiRequest<Page<{ id: string; version_number: number; change_note: string; created_by_name: string; created_at: string }>>(`/catalog/admin/theory-system/nodes/${editing.id}/versions/`, {}, token);
      setVersions(payload.results);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "历史版本读取失败");
      setMessageState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  async function mergeNode() {
    if (!editing || !mergeTarget) return;
    const target = allNodes.data?.results.find((item) => item.id === mergeTarget);
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = "merge-theory-node";
    if (!startAction(actionKey)) return;
    setMessage("正在计算合并影响……");
    setMessageState("pending");
    try {
      const preview = await apiRequest<{ affected: Record<string, number> }>(`/catalog/admin/theory-system/nodes/${editing.id}/merge-preview/`, {}, token);
      const impact = Object.entries(preview.affected).map(([key, value]) => `${key} ${value}`).join("、");
      if (!window.confirm(`将“${editing.canonical_name_zh}”合并到“${target?.canonical_name_zh || "目标节点"}”？\n受影响范围 ${impact || "已计算"}`)) {
        setMessage("已取消节点合并。");
        setMessageState("idle");
        return;
      }
      await apiRequest(`/catalog/admin/theory-system/nodes/${editing.id}/merge/`, { method: "POST", body: JSON.stringify({ target_node: mergeTarget, change_note: "后台人工合并" }) }, token);
      setMessage("节点已在事务中合并，合并记录可供管理员回滚。");
      setMessageState("success");
      setEditing(null);
      nodes.refresh();
      allNodes.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "合并失败");
      setMessageState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  const visibleNodes = nodes.data?.results ?? [];
  const disciplineName = (id: string) => disciplines.data?.results.find((item) => item.id === id)?.name || entityLabels[id] || "已选择学科";
  const nodeName = (id: string) => allNodes.data?.results.find((item) => item.id === id)?.canonical_name_zh || entityLabels[id] || "已选择节点";
  return (
    <AdminFrame
      eyebrow="知识组织"
      title="理论节点管理"
      description="维护规范理论节点、子学科、概念、争论和研究问题。前台各页面从这些结构化数据自动生成。"
      actions={<button className="admin-outline-button" type="button" onClick={() => { nodes.refresh(); allNodes.refresh(); }}><RefreshCw size={15} />刷新</button>}
    >
      <div className="theory-node-admin-grid">
        <section className="admin-panel theory-node-table-panel">
          <nav className="theory-node-tabs">
            {Object.entries(nodeTypeLabels).map(([value, label]) => <button className={nodeType === value ? "active" : ""} type="button" key={value} onClick={() => { setNodeType(value); start(); }}>{label}</button>)}
          </nav>
          <div className="theory-admin-filters">
            <ResearchEntityPicker label="所属学科筛选" endpoint="/catalog/admin/disciplines/" entityType="discipline" step="maintenance_theory_nodes" field="filter_discipline" values={onePickerValue(disciplineFilter, disciplineName(disciplineFilter))} onChange={(next) => { const selected = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDisciplineFilter(selected?.id ?? ""); }} />
            <label><span>状态</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">全部</option><option value="draft">草稿</option><option value="pending">待审核</option><option value="published">已发布</option><option value="rejected">已拒绝</option><option value="archived">已下线</option></select></label>
            <label className="theory-admin-search"><span>名称或别名</span><div><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索节点……" /></div></label>
            <button className="button" type="button" onClick={() => start()}><Plus size={15} />新建节点</button>
          </div>
          <ErrorNotice message={nodes.error || disciplines.error} retry={nodes.refresh} />
          {nodes.loading ? <div className="theory-admin-loading">正在读取节点……</div> : null}
          <div className="theory-admin-table-wrap">
            <table className="theory-admin-table">
              <thead><tr><th>标准中文名</th><th>节点类型</th><th>主要学科</th><th>关联学科</th><th>别名</th><th>馆藏</th><th>关系</th><th>状态</th><th>最后编辑</th></tr></thead>
              <tbody>{visibleNodes.map((node) => <tr className={editing?.id === node.id ? "selected" : ""} key={node.id} role="button" tabIndex={0} aria-label={`编辑理论节点 ${node.canonical_name_zh}`} onClick={() => start(node)} onKeyDown={(event) => activateOnEnterOrSpace(event, () => start(node))}><td><strong>{node.canonical_name_zh}</strong><small>{node.canonical_name_en}</small></td><td>{nodeTypeLabels[node.node_type]}</td><td>{node.primary_discipline_data?.name || "未指定"}</td><td>{node.discipline_links.filter((item) => item.relation_type !== "primary").map((item) => item.discipline.name).join("、") || "—"}</td><td>{node.aliases.length}</td><td>{node.work_count}</td><td>{node.relation_count}</td><td><StatusBadge value={node.status} /></td><td>{asDate(node.updated_at)}</td></tr>)}</tbody>
            </table>
          </div>
          {!nodes.loading && !visibleNodes.length ? <div className="theory-admin-empty"><FileText size={22} /><strong>当前筛选下没有节点</strong><button type="button" onClick={() => start()}>建立第一个节点</button></div> : null}
          <footer className="theory-admin-count">共 {nodes.data?.count ?? 0} 个节点</footer>
        </section>

        <form className="admin-panel theory-node-editor" onSubmit={saveNode}>
          <header><div><h2>{editing ? `编辑 ${editing.canonical_name_zh}` : "新建节点"}</h2><p>{editing ? `馆藏 ${editing.work_count} · 关系 ${editing.relation_count}` : "建立规范节点后再审核馆藏关系"}</p></div>{editing ? <div className="theory-editor-preview-links"><Link href={`/theories/nodes/${editing.slug}`} target="_blank">查看条目 <ExternalLink size={14} /></Link><Link href={`/theories/graph?center=${encodeURIComponent(editing.slug)}`} target="_blank">预览图谱 <ExternalLink size={14} /></Link></div> : null}</header>
          <div className="inline-fields"><label><span>标准中文名</span><input autoComplete="off" required value={draft.canonical_name_zh} onChange={(event) => setDraft({ ...draft, canonical_name_zh: event.target.value })} /></label><label><span>节点类型</span><select value={draft.node_type} onChange={(event) => setDraft({ ...draft, node_type: event.target.value })}>{Object.entries(nodeTypeLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label></div>
          <AuthoritySuggestions
            entityType={draft.node_type === "theory_tradition" ? "theory_tradition" : draft.node_type === "subdiscipline" ? "subdiscipline" : "concept"}
            query={draft.canonical_name_en.trim() || draft.canonical_name_zh}
          />
          <label><span>外文名称</span><input value={draft.canonical_name_en} onChange={(event) => setDraft({ ...draft, canonical_name_en: event.target.value })} /></label>
          <StructuredRowsEditor
            label="别名和不同译名"
            description="分别记录名称、语言和用途，避免根据字符外观猜测语言。"
            rowLabel="别名"
            addLabel="添加别名"
            value={draft.aliases.map((item) => ({ ...item }))}
            createRow={() => ({ alias: "", language: "zh-CN", alias_type: "alias" })}
            columns={[
              { key: "alias", label: "名称" },
              { key: "language", label: "语言", options: [{ value: "zh-CN", label: "简体中文" }, { value: "zh-TW", label: "繁体中文" }, { value: "en", label: "英语" }, { value: "fr", label: "法语" }, { value: "de", label: "德语" }, { value: "other", label: "其他" }] },
              { key: "alias_type", label: "类型", options: [{ value: "alias", label: "别名" }, { value: "translation", label: "译名" }, { value: "abbreviation", label: "简称" }, { value: "former_name", label: "旧称" }] },
            ]}
            onChange={(value) => setDraft({ ...draft, aliases: value.map((item) => ({ alias: item.alias || "", language: item.language || "zh-CN", alias_type: item.alias_type || "alias" })) })}
          />
          <FieldEnrichmentControl
            targetType="knowledge_node"
            targetId={editing?.id}
            title="理论字段核对"
            fields={[
              { name: "alias", label: "译名或别名", currentValue: draft.aliases },
              { name: "discipline", label: "学科分类", currentValue: draft.related_disciplines },
              { name: "subdiscipline", label: "子学科分类", currentValue: draft.parent },
            ]}
            formContext={{ language: "zh" }}
            onAccepted={() => { nodes.refresh(); allNodes.refresh(); }}
          />
          <div className="inline-fields three"><ResearchEntityPicker label="主要学科" endpoint="/catalog/admin/disciplines/" entityType="discipline" step="maintenance_theory_nodes" field="primary_discipline" values={onePickerValue(draft.primary_discipline, disciplineName(draft.primary_discipline))} onChange={(next) => { const selected = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, primary_discipline: selected?.id ?? "", related_disciplines: draft.related_disciplines.filter((id) => id !== selected?.id) }); }} /><ResearchEntityPicker label="上级节点" endpoint="/catalog/admin/theory-system/nodes/" entityType="knowledge_node" step="maintenance_theory_nodes" field="parent" values={onePickerValue(draft.parent, nodeName(draft.parent))} onChange={(next) => { const selected = next.at(-1); if (selected?.id === editing?.id) return; setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, parent: selected?.id ?? "" }); }} /><label><span>固定链接</span><input required value={draft.slug} onChange={(event) => setDraft({ ...draft, slug: event.target.value })} placeholder="symbolic-interactionism" /></label></div>
          <ResearchEntityPicker label="关联学科" endpoint="/catalog/admin/disciplines/" entityType="discipline" step="maintenance_theory_nodes" field="related_disciplines" multiple values={manyPickerValues(draft.related_disciplines, disciplineName)} onChange={(next) => { setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, related_disciplines: next.flatMap((value) => value.id && value.id !== draft.primary_discipline ? [value.id] : []) }); }} />
          <label><span>简介</span><textarea rows={3} value={draft.summary} onChange={(event) => setDraft({ ...draft, summary: event.target.value })} /></label>
          <label><span>完整定义</span><textarea rows={5} value={draft.definition} onChange={(event) => setDraft({ ...draft, definition: event.target.value })} /></label>
          <StringListEditor label="核心问题" itemLabel="问题" value={editorLines(draft.core_questions)} onChange={(value) => setDraft({ ...draft, core_questions: value.join("\n") })} addLabel="添加问题" />
          <StringListEditor label="基本命题" itemLabel="命题" value={editorLines(draft.basic_propositions)} onChange={(value) => setDraft({ ...draft, basic_propositions: value.join("\n") })} addLabel="添加命题" />
          <label><span>理论边界</span><textarea rows={5} value={draft.theoretical_boundary} onChange={(event) => setDraft({ ...draft, theoretical_boundary: event.target.value })} placeholder="主要解释什么、解释范围、与相邻理论的区别" /></label>
          <div className="inline-fields three"><label><span>开始年份</span><input type="number" value={draft.start_year} onChange={(event) => setDraft({ ...draft, start_year: event.target.value })} /></label><label><span>结束年份</span><input type="number" value={draft.end_year} onChange={(event) => setDraft({ ...draft, end_year: event.target.value })} /></label><label><span>显示时期</span><input value={draft.period_label} onChange={(event) => setDraft({ ...draft, period_label: event.target.value })} /></label></div>
          <div className="inline-fields"><label><span>审核状态</span><select value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}><option value="draft">草稿</option><option value="pending">提交审核</option><option value="published">发布</option><option value="rejected">拒绝</option><option value="archived">下线</option></select></label><label><span>显示顺序</span><input type="number" min={0} value={draft.sort_order} onChange={(event) => setDraft({ ...draft, sort_order: Number(event.target.value) })} /></label></div>
          <label className="knowledge-image-upload"><ImagePlus size={18} /><span>{cover?.name || (editing?.cover_url ? "替换黑白几何主视觉" : "上传黑白几何主视觉")}</span><input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setCover(event.target.files?.[0] ?? null)} /></label>
          {editing ? <div className="theory-node-secondary-actions"><ActionButton type="button" state={pendingAction === "load-node-versions" ? "pending" : "idle"} pendingLabel="读取中" disabled={Boolean(pendingAction) && pendingAction !== "load-node-versions"} onClick={() => void loadVersions()}><History size={14} />历史版本</ActionButton></div> : null}
          {versions ? <section className="theory-version-list"><header><strong>历史版本</strong><button type="button" aria-label="关闭历史版本" onClick={() => setVersions(null)}><X size={14} /></button></header>{versions.map((version) => <article key={version.id}><strong>第 {version.version_number} 版</strong><span>{version.change_note || "内容更新"}</span><small>{version.created_by_name || "系统"} · {asDate(version.created_at)}</small></article>)}</section> : null}
          {editing ? <section className="theory-merge-box"><strong><GitMerge size={15} />合并重复节点</strong><p>合并前会计算文献、关系、学者、时间轴和阅读路径的影响。</p><div><ResearchEntityPicker label="选择保留的目标节点" endpoint="/catalog/admin/theory-system/nodes/" entityType="knowledge_node" step="maintenance_theory_nodes" field="merge_target" values={onePickerValue(mergeTarget, nodeName(mergeTarget))} onChange={(next) => { const selected = next.at(-1); if (selected?.id === editing.id || selected?.status === "archived") return; setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setMergeTarget(selected?.id ?? ""); }} /><ActionButton type="button" state={pendingAction === "merge-theory-node" ? "pending" : "idle"} pendingLabel="正在计算影响" disabled={!mergeTarget || (Boolean(pendingAction) && pendingAction !== "merge-theory-node")} onClick={() => void mergeNode()}>预览并合并</ActionButton></div></section> : null}
          {editing ? <EntityLifecycleActions kind="knowledge-node" id={editing.id} name={editing.canonical_name_zh} status={draft.status} previewHref={`/theories/nodes/${editing.slug}`} onChanged={(snapshot) => { setDraft((current) => ({ ...current, status: snapshot.status })); setEditing((current) => current ? { ...current, status: snapshot.status } : current); nodes.refresh(); allNodes.refresh(); }} onDeleted={() => { setEditing(null); setDraft({ ...emptyNodeDraft, node_type: nodeType, primary_discipline: disciplines.data?.results[0]?.id ?? "" }); nodes.refresh(); allNodes.refresh(); }} /> : null}
          <div className="theory-editor-footer"><ActionButton className="button" state={pendingAction === "save-theory-node" ? "pending" : "idle"} pendingLabel="正在保存" disabled={Boolean(pendingAction) && pendingAction !== "save-theory-node"} type="submit"><Save size={15} />{draft.status === "published" ? "保存并发布" : "保存"}</ActionButton></div>
          {message ? <AsyncStatus state={messageState} message={message} /> : null}
        </form>
      </div>
    </AdminFrame>
  );
}

type ReviewTask = {
  id: string;
  task_type: string;
  work: string | null;
  work_title: string;
  file: string | null;
  file_page_count: number | null;
  candidate_node: string | null;
  node_name: string;
  suggested_node_name: string;
  suggested_relation_type: string;
  confidence: number;
  evidence_pages: Array<number | string>;
  evidence_text: string;
  status: string;
  assigned_to: string | null;
  submitted_at: string | null;
  reviewed_at: string | null;
  review_note: string;
  viewer_href: string | null;
  created_at: string;
};

type KnowledgeRelation = {
  id: string;
  source_node: string;
  source_name: string;
  target_node: string;
  target_name: string;
  relation_type: string;
  relation_label: string;
  direction: string;
  description: string;
  evidence_source: string;
  confidence: number;
  status: string;
  updated_at: string;
};

function RelationGraphPreview({
  relations,
  centerId,
}: {
  relations: KnowledgeRelation[];
  centerId?: string;
}) {
  const effectiveCenter = centerId || relations[0]?.source_node;
  const visible = relations
    .filter((relation) => !effectiveCenter || relation.source_node === effectiveCenter || relation.target_node === effectiveCenter)
    .slice(0, 8);
  if (!visible.length) {
    return <div className="admin-relation-preview empty"><span>保存关系后，这里会生成局部图谱预览。</span></div>;
  }
  const centerName = visible.find((relation) => relation.source_node === effectiveCenter)?.source_name
    || visible.find((relation) => relation.target_node === effectiveCenter)?.target_name
    || visible[0].source_name;
  return (
    <section className="admin-relation-preview" aria-label="局部理论关系预览">
      <header><strong>局部图谱预览</strong><span>只显示当前中心的一层关系，避免馆藏增长后画布失控。</span></header>
      <div className="admin-relation-preview-body">
        <strong className="relation-center-node">{centerName}</strong>
        <div className="relation-preview-spokes">
          {visible.map((relation) => {
            const outward = relation.source_node === effectiveCenter;
            const adjacentName = outward ? relation.target_name : relation.source_name;
            return <div key={relation.id}>
              <span>{outward ? relation.relation_label : `${relation.relation_label}的来源`}</span>
              <ArrowRight size={14} aria-hidden="true" />
              <strong>{adjacentName}</strong>
              <StatusBadge value={relation.status} />
            </div>;
          })}
        </div>
      </div>
    </section>
  );
}

const workRelationOptions = [
  ["foundational_work", "奠基性原著"],
  ["systematic_exposition", "系统阐释"],
  ["theoretical_development", "理论发展"],
  ["empirical_application", "经验应用"],
  ["comparative_study", "比较研究"],
  ["critique", "批评反思"],
  ["general_mention", "一般提及"],
] as const;

const knowledgeRelationOptions = [
  ["inherited_from", "继承"],
  ["revises", "修正"],
  ["criticizes", "批判"],
  ["competes_with", "竞争"],
  ["synthesizes", "综合"],
  ["branches_from", "分化"],
  ["borrows_concept_from", "概念借用"],
  ["transferred_to", "跨学科传播"],
  ["influenced_by", "受到影响"],
  ["overlaps_with", "部分重叠"],
] as const;

export function TheoryRelationsAdmin() {
  const [taskStatus, setTaskStatus] = useState("pending");
  const [taskQuery, setTaskQuery] = useState("");
  const [selected, setSelected] = useState<ReviewTask | null>(null);
  const [candidateNode, setCandidateNode] = useState("");
  const [relationRole, setRelationRole] = useState("general_mention");
  const [newNodeType, setNewNodeType] = useState("theory_tradition");
  const [newNodeDiscipline, setNewNodeDiscipline] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [message, setMessage] = useState("");
  const [messageState, setMessageState] = useState<ActionState>("idle");
  const { pendingAction, startAction, finishAction } = useActionGuard();
  const [entityLabels, setEntityLabels] = useState<Record<string, string>>({});
  const [editingRelation, setEditingRelation] = useState<KnowledgeRelation | null>(null);
  const [relationDraft, setRelationDraft] = useState({ source_node: "", target_node: "", relation_type: "criticizes", direction: "directed", description: "", evidence_source: "", confidence: 1, status: "pending" });

  const taskParams = useMemo(() => {
    const params = new URLSearchParams();
    if (taskStatus) params.set("status", taskStatus);
    if (taskQuery.trim()) params.set("q", taskQuery.trim());
    return params.toString();
  }, [taskStatus, taskQuery]);
  const tasks = useAdminData<Page<ReviewTask>>(`/catalog/admin/theory-system/review-tasks/?${taskParams}`);
  const nodes = useAdminData<Page<KnowledgeNode>>("/catalog/admin/theory-system/nodes/");
  const disciplines = useAdminData<Page<Discipline>>("/catalog/admin/disciplines/");
  const relations = useAdminData<Page<KnowledgeRelation>>("/catalog/admin/theory-system/relations/");

  function chooseTask(task: ReviewTask) {
    setSelected(task);
    setCandidateNode(task.candidate_node ?? "");
    setRelationRole(workRelationOptions.some(([value]) => value === task.suggested_relation_type) ? task.suggested_relation_type : "general_mention");
    setNewNodeType("theory_tradition");
    setNewNodeDiscipline("");
    setReviewNote(task.review_note || "");
    setMessage("");
    setMessageState("idle");
    setEntityLabels({});
  }

  async function review(action: "confirm" | "modify_confirm" | "create_node" | "alias_existing" | "reject" | "defer" | "insufficient" | "needs_changes") {
    if (!selected) return;
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = `review-task:${selected.id}:${action}`;
    if (!startAction(actionKey)) return;
    setMessage("正在提交审核决定……");
    setMessageState("pending");
    try {
      const updated = await apiRequest<ReviewTask>(`/catalog/admin/theory-system/review-tasks/${selected.id}/action/`, {
        method: "POST",
        body: JSON.stringify({
          action,
          candidate_node: candidateNode || null,
          relation_type: relationRole,
          review_note: reviewNote,
          canonical_name_zh: selected.suggested_node_name,
          node_type: newNodeType,
          primary_discipline: newNodeDiscipline || null,
        }),
      }, token);
      setSelected(updated);
      setMessage(
        action === "create_node"
          ? "已创建待完善的规范节点草稿。文献关系已进入下一条审核任务。"
          : action === "alias_existing"
            ? "候选名称已保存为已有节点别名。文献关系已进入下一条审核任务。"
            : action === "confirm" || action === "modify_confirm"
              ? "候选已确认。馆藏关系和页码证据已同步写入。"
              : "审核状态已更新。",
      );
      setMessageState("success");
      tasks.refresh();
      nodes.refresh();
      relations.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "审核操作失败");
      setMessageState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  async function saveRelation(event: FormEvent) {
    event.preventDefault();
    if (!relationDraft.source_node || !relationDraft.target_node) return;
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = editingRelation ? `save-relation:${editingRelation.id}` : "create-relation";
    if (!startAction(actionKey)) return;
    setMessage(editingRelation ? "正在保存关系修改……" : "正在添加理论关系……");
    setMessageState("pending");
    try {
      await apiRequest(
        editingRelation
          ? `/catalog/admin/theory-system/relations/${editingRelation.id}/`
          : "/catalog/admin/theory-system/relations/",
        { method: editingRelation ? "PATCH" : "POST", body: JSON.stringify(relationDraft) },
        token,
      );
      setMessage(editingRelation ? "理论关系已更新。前台只显示已发布关系。" : "理论关系已保存。只有已发布关系会显示在前台详情页和图谱中。");
      setMessageState("success");
      setEditingRelation(null);
      setRelationDraft({ source_node: "", target_node: "", relation_type: "criticizes", direction: "directed", description: "", evidence_source: "", confidence: 1, status: "pending" });
      relations.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "关系保存失败");
      setMessageState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  async function removeRelation(relation: KnowledgeRelation) {
    if (!window.confirm(`删除“${relation.source_name} ${relation.relation_label} ${relation.target_name}”吗？`)) return;
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = `delete-relation:${relation.id}`;
    if (!startAction(actionKey)) return;
    setMessage("正在删除理论关系……");
    setMessageState("pending");
    try {
      await apiRequest(`/catalog/admin/theory-system/relations/${relation.id}/`, { method: "DELETE" }, token);
      if (editingRelation?.id === relation.id) {
        setEditingRelation(null);
        setRelationDraft({ source_node: "", target_node: "", relation_type: "criticizes", direction: "directed", description: "", evidence_source: "", confidence: 1, status: "pending" });
      }
      relations.refresh();
      setMessage("理论关系已删除。");
      setMessageState("success");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "删除失败");
      setMessageState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  function editRelation(relation: KnowledgeRelation) {
    setEditingRelation(relation);
    setRelationDraft({
      source_node: relation.source_node,
      target_node: relation.target_node,
      relation_type: relation.relation_type,
      direction: relation.direction,
      description: relation.description,
      evidence_source: relation.evidence_source,
      confidence: relation.confidence,
      status: relation.status,
    });
    setMessage("");
    setMessageState("idle");
  }

  async function removeReviewTask() {
    if (!selected) return;
    const label = selected.work_title || selected.suggested_node_name || "该审核项";
    if (!window.confirm(`确认删除“${label}”的审核候选吗？已确认生成的公开关系不会随审核记录一起删除。`)) return;
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = `delete-review-task:${selected.id}`;
    if (!startAction(actionKey)) return;
    setMessage("正在删除审核候选……");
    setMessageState("pending");
    try {
      await apiRequest(`/catalog/admin/theory-system/review-tasks/${selected.id}/`, { method: "DELETE" }, token);
      setSelected(null);
      setMessage("审核候选已删除，操作已写入审计记录。");
      setMessageState("success");
      tasks.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "审核候选删除失败");
      setMessageState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  const counts = tasks.data?.results.reduce<Record<string, number>>((acc, item) => { acc[item.status] = (acc[item.status] || 0) + 1; return acc; }, {}) ?? {};
  const relationNodeName = (id: string) => nodes.data?.results.find((item) => item.id === id)?.canonical_name_zh || entityLabels[id] || "已选择节点";
  const relationDisciplineName = (id: string) => disciplines.data?.results.find((item) => item.id === id)?.name || entityLabels[id] || "已选择学科";
  return (
    <AdminFrame eyebrow="知识审核" title="理论关系与审核" description="核对系统从 PDF 提出的理论候选、关系类型和原文证据。待审核结果不会出现在公共页面。">
      <div className="theory-review-layout">
        <section className="admin-panel theory-review-list">
          <nav className="theory-review-tabs">
            {[["pending", "待审核"], ["needs_changes", "待修改"], ["confirmed", "已确认"], ["rejected", "已拒绝"], ["", "全部"]].map(([value, label]) => <button className={taskStatus === value ? "active" : ""} type="button" key={label} onClick={() => { setTaskStatus(value); setSelected(null); }}>{label}{counts[value] ? <span>{counts[value]}</span> : null}</button>)}
          </nav>
          <div className="theory-review-filter"><Search size={15} /><input value={taskQuery} onChange={(event) => setTaskQuery(event.target.value)} placeholder="搜索文献、候选理论或证据……" /><button type="button" onClick={tasks.refresh} aria-label="刷新审核候选" title="刷新审核候选"><RefreshCw size={15} /></button></div>
          <ErrorNotice message={tasks.error} retry={tasks.refresh} />
          <div className="theory-admin-table-wrap">
            <table className="theory-admin-table theory-review-table">
              <thead><tr><th>文献</th><th>候选理论</th><th>建议关系</th><th>置信度</th><th>证据页码</th><th>状态</th><th>提交时间</th></tr></thead>
              <tbody>{tasks.data?.results.map((task) => <tr className={selected?.id === task.id ? "selected" : ""} key={task.id} role="button" tabIndex={0} aria-label={`打开审核候选 ${task.work_title || task.suggested_node_name || "系统候选"}`} onClick={() => chooseTask(task)} onKeyDown={(event) => activateOnEnterOrSpace(event, () => chooseTask(task))}><td><strong>{task.work_title || task.suggested_node_name || "系统候选"}</strong><small>{task.file_page_count ? `${task.file_page_count} 页 PDF` : task.task_type}</small></td><td>{task.node_name || task.suggested_node_name || "待匹配规范节点"}</td><td>{task.task_type === "new_node" ? "建议新增节点" : workRelationOptions.find(([value]) => value === task.suggested_relation_type)?.[1] || task.suggested_relation_type || "待判断"}</td><td><span className="theory-confidence">{Math.round(task.confidence * 100)}%</span></td><td>{task.evidence_pages.join("–") || "—"}</td><td><StatusBadge value={task.status} /></td><td>{asDate(task.submitted_at || task.created_at)}</td></tr>)}</tbody>
            </table>
          </div>
          {!tasks.loading && !tasks.data?.results.length ? <div className="theory-admin-empty"><Check size={22} /><strong>当前没有待处理候选</strong><span>新 PDF 完成理论识别后会进入这里。</span></div> : null}
        </section>

        <aside className="admin-panel theory-review-editor">
          {selected ? <>
            <header><div><p>当前审核项</p><h2>{selected.work_title || selected.suggested_node_name}</h2><span>置信度 {Math.round(selected.confidence * 100)}% · {selected.evidence_pages.length ? `第 ${selected.evidence_pages.join("–")} 页` : "暂无页码"}</span></div>{selected.viewer_href ? <Link href={selected.viewer_href} target="_blank">查看 PDF <ExternalLink size={14} /></Link> : null}</header>
            {selected.task_type === "new_node" ? <section className="theory-new-node-notice"><strong>建议新增知识节点</strong><p>系统在多个 PDF 页面发现“{selected.suggested_node_name}”。请先判断它是新节点，还是已有节点的别名。创建后仍需在节点管理中完善和发布。</p></section> : null}
            <ResearchEntityPicker label={selected.task_type === "new_node" ? "归并到已有节点" : "候选理论"} endpoint="/catalog/admin/theory-system/nodes/" entityType="knowledge_node" step="maintenance_theory_relations" field="review_candidate" values={onePickerValue(candidateNode, relationNodeName(candidateNode))} onChange={(next) => { const picked = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setCandidateNode(picked?.id ?? ""); }} />
            {selected.task_type === "new_node" ? <div className="inline-fields"><label><span>新节点类型</span><select value={newNodeType} onChange={(event) => setNewNodeType(event.target.value)}>{Object.entries(nodeTypeLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><ResearchEntityPicker label="主要学科" endpoint="/catalog/admin/disciplines/" entityType="discipline" step="maintenance_theory_relations" field="new_node_discipline" values={onePickerValue(newNodeDiscipline, relationDisciplineName(newNodeDiscipline))} onChange={(next) => { const picked = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setNewNodeDiscipline(picked?.id ?? ""); }} /></div> : null}
            <label><span>建议关系类型</span><select value={relationRole} onChange={(event) => setRelationRole(event.target.value)}>{workRelationOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
            <section className="theory-evidence-card"><header><strong>原文片段</strong><span>{selected.file ? "PDF/OCR 证据" : "系统建议"}</span></header><blockquote>{selected.evidence_text || "这条建议尚未附带原文，不应直接确认。"}</blockquote><footer>{selected.evidence_pages.length ? `页码 ${selected.evidence_pages.join("–")}` : "页码待补充"}</footer></section>
            <label><span>审核备注</span><textarea rows={4} value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} placeholder="记录修改理由或参考资料" /></label>
            {selected.task_type === "new_node" ? <div className="theory-review-primary-actions"><ActionButton className="button" type="button" state={pendingAction?.endsWith(":create_node") ? "pending" : "idle"} pendingLabel="正在创建" disabled={Boolean(pendingAction) && !pendingAction?.endsWith(":create_node")} onClick={() => void review("create_node")}><Plus size={15} />创建草稿节点</ActionButton><ActionButton disabled={!candidateNode || (Boolean(pendingAction) && !pendingAction?.endsWith(":alias_existing"))} state={pendingAction?.endsWith(":alias_existing") ? "pending" : "idle"} pendingLabel="正在归并" type="button" onClick={() => void review("alias_existing")}>作为已有节点别名</ActionButton><ActionButton type="button" state={pendingAction?.endsWith(":reject") ? "pending" : "idle"} pendingLabel="正在拒绝" disabled={Boolean(pendingAction) && !pendingAction?.endsWith(":reject")} onClick={() => void review("reject")}>拒绝</ActionButton></div> : <div className="theory-review-primary-actions"><ActionButton className="button" disabled={!candidateNode || Boolean(pendingAction)} state={pendingAction?.endsWith(":confirm") || pendingAction?.endsWith(":modify_confirm") ? "pending" : "idle"} pendingLabel="正在确认" type="button" onClick={() => void review(selected.candidate_node === candidateNode && selected.suggested_relation_type === relationRole ? "confirm" : "modify_confirm")}><Check size={15} />确认</ActionButton><ActionButton type="button" state={pendingAction?.endsWith(":needs_changes") ? "pending" : "idle"} pendingLabel="正在退回" disabled={Boolean(pendingAction) && !pendingAction?.endsWith(":needs_changes")} onClick={() => void review("needs_changes")}>退回修改</ActionButton><ActionButton type="button" state={pendingAction?.endsWith(":reject") ? "pending" : "idle"} pendingLabel="正在拒绝" disabled={Boolean(pendingAction) && !pendingAction?.endsWith(":reject")} onClick={() => void review("reject")}>拒绝</ActionButton></div>}
            <div className="theory-review-secondary-actions"><ActionButton type="button" state={pendingAction?.endsWith(":defer") ? "pending" : "idle"} pendingLabel="处理中" disabled={Boolean(pendingAction) && !pendingAction?.endsWith(":defer")} onClick={() => void review("defer")}>延后处理</ActionButton><ActionButton type="button" state={pendingAction?.endsWith(":insufficient") ? "pending" : "idle"} pendingLabel="处理中" disabled={Boolean(pendingAction) && !pendingAction?.endsWith(":insufficient")} onClick={() => void review("insufficient")}>证据不足</ActionButton><ActionButton className="danger-link" type="button" state={pendingAction === `delete-review-task:${selected.id}` ? "pending" : "idle"} pendingLabel="删除中" disabled={Boolean(pendingAction) && pendingAction !== `delete-review-task:${selected.id}`} onClick={() => void removeReviewTask()}><Trash2 size={13} />删除候选</ActionButton></div>
          </> : <div className="theory-admin-empty"><BookOpen size={24} /><strong>选择一个审核项</strong><span>右侧会显示候选理论、原文内容和 PDF 页码。</span></div>}
          {message ? <AsyncStatus state={messageState} message={message} /> : null}
        </aside>
      </div>

      <section className="admin-panel theory-relation-editor-section">
        <header>
          <div><p>人工维护</p><h2>{editingRelation ? "编辑理论关系" : "理论与理论之间的关系"}</h2><span>关系类型为受控选项，证据说明会进入版本记录。</span></div>
          {relationDraft.source_node ? <Link
            className="admin-outline-button"
            href={`/theories/graph?center=${encodeURIComponent(nodes.data?.results.find((node) => node.id === relationDraft.source_node)?.slug || "")}`}
            target="_blank"
          >预览局部图谱 <ExternalLink size={14} /></Link> : <Link className="admin-outline-button" href="/theories/graph" target="_blank">预览公共图谱 <ExternalLink size={14} /></Link>}
        </header>
        <div className="theory-relation-bottom-grid">
          <form onSubmit={saveRelation}>
            <div className="inline-fields"><ResearchEntityPicker label="源理论" endpoint="/catalog/admin/theory-system/nodes/" entityType="knowledge_node" step="maintenance_theory_relations" field="source_node" values={onePickerValue(relationDraft.source_node, relationNodeName(relationDraft.source_node))} onChange={(next) => { const picked = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setRelationDraft({ ...relationDraft, source_node: picked?.id ?? "", target_node: picked?.id === relationDraft.target_node ? "" : relationDraft.target_node }); }} /><ResearchEntityPicker label="目标理论" endpoint="/catalog/admin/theory-system/nodes/" entityType="knowledge_node" step="maintenance_theory_relations" field="target_node" values={onePickerValue(relationDraft.target_node, relationNodeName(relationDraft.target_node))} onChange={(next) => { const picked = next.at(-1); if (picked?.id === relationDraft.source_node) return; setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setRelationDraft({ ...relationDraft, target_node: picked?.id ?? "" }); }} /></div>
            <div className="inline-fields"><label><span>关系类型</span><select value={relationDraft.relation_type} onChange={(event) => setRelationDraft({ ...relationDraft, relation_type: event.target.value })}>{knowledgeRelationOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label><span>方向</span><select value={relationDraft.direction} onChange={(event) => setRelationDraft({ ...relationDraft, direction: event.target.value })}><option value="directed">有方向</option><option value="undirected">无方向</option></select></label></div>
            <label><span>关系说明</span><textarea rows={3} value={relationDraft.description} onChange={(event) => setRelationDraft({ ...relationDraft, description: event.target.value })} /></label>
            <label><span>证据来源</span><textarea rows={3} value={relationDraft.evidence_source} onChange={(event) => setRelationDraft({ ...relationDraft, evidence_source: event.target.value })} placeholder="馆藏页码、参考文献或人工校订说明" /></label>
            <div className="inline-fields"><label><span>审核状态</span><select value={relationDraft.status} onChange={(event) => setRelationDraft({ ...relationDraft, status: event.target.value })}><option value="draft">草稿</option><option value="pending">待审核</option><option value="published">发布</option><option value="rejected">拒绝</option><option value="archived">下线</option></select></label><label><span>置信度</span><input type="number" min={0} max={1} step={0.01} value={relationDraft.confidence} onChange={(event) => setRelationDraft({ ...relationDraft, confidence: Number(event.target.value) })} /></label></div>
            <div className="theory-review-primary-actions"><ActionButton className="button" type="submit" state={pendingAction === (editingRelation ? `save-relation:${editingRelation.id}` : "create-relation") ? "pending" : "idle"} pendingLabel={editingRelation ? "正在保存修改" : "正在添加关系"} disabled={Boolean(pendingAction) && pendingAction !== (editingRelation ? `save-relation:${editingRelation.id}` : "create-relation")}>{editingRelation ? <Save size={15} /> : <Plus size={15} />}{editingRelation ? "保存修改" : "添加关系"}</ActionButton>{editingRelation ? <button type="button" onClick={() => { setEditingRelation(null); setRelationDraft({ source_node: "", target_node: "", relation_type: "criticizes", direction: "directed", description: "", evidence_source: "", confidence: 1, status: "pending" }); }}>取消编辑</button> : null}</div>
          </form>
          <div className="theory-existing-relations">
            <RelationGraphPreview relations={relations.data?.results ?? []} centerId={relationDraft.source_node} />
            <h3>现有关系</h3>{relations.data?.results.map((relation) => <article className={editingRelation?.id === relation.id ? "selected" : ""} key={relation.id}><div><strong>{relation.source_name}</strong><span>{relation.relation_label}</span><strong>{relation.target_name}</strong></div><p>{relation.description || relation.evidence_source || "尚未填写说明"}</p><footer><StatusBadge value={relation.status} /><span><button type="button" onClick={() => editRelation(relation)}><Pencil size={13} />编辑</button><ActionButton type="button" state={pendingAction === `delete-relation:${relation.id}` ? "pending" : "idle"} pendingLabel="删除中" disabled={Boolean(pendingAction) && pendingAction !== `delete-relation:${relation.id}`} onClick={() => void removeRelation(relation)}><Trash2 size={13} />删除</ActionButton></span></footer></article>)}{!relations.data?.results.length ? <p>尚未建立规范理论关系。</p> : null}
          </div>
        </div>
      </section>
    </AdminFrame>
  );
}

type TimelineRelation = {
  id?: string;
  relation_type: string;
  node: string | null;
  node_name?: string;
  discipline: string | null;
  discipline_name?: string;
  scholar: string | null;
  scholar_name?: string;
  work: string | null;
  work_title?: string;
  evidence: string | null;
  description: string;
  sort_order: number;
};

type TimelineEvent = {
  id: string;
  title: string;
  description: string;
  event_type: string;
  start_year: number | null;
  end_year: number | null;
  date_label: string;
  orientation: string;
  source: string;
  evidence_asset: string | null;
  evidence_page: number | null;
  evidence_printed_label: string;
  evidence_text: string;
  confidence: number;
  review_status: string;
  display_order: number;
  discipline: string | null;
  theory_school: string | null;
  subdiscipline: string | null;
  scholar: string | null;
  work: string | null;
  relations: TimelineRelation[];
};

type TimelineDraft = {
  title: string;
  description: string;
  event_type: string;
  start_year: string;
  end_year: string;
  date_label: string;
  source: string;
  evidence_page: string;
  evidence_printed_label: string;
  evidence_text: string;
  confidence: number;
  review_status: string;
  display_order: number;
  nodes: string[];
  disciplines: string[];
  scholar: string;
  work: string;
};

const timelineTypes = [
  ["publication", "重要著作出版"],
  ["concept_proposed", "理论概念提出"],
  ["school_formation", "学派形成"],
  ["institution", "学术机构建立"],
  ["debate", "重要争论"],
  ["theoretical_turn", "理论转向"],
  ["translation", "重要译介"],
  ["china_reception", "理论进入中国学界"],
  ["scholar", "学者生平事件"],
  ["institutionalization", "学科制度化事件"],
  ["formation", "旧数据：形成"],
  ["development", "旧数据：发展"],
] as const;

const emptyTimelineDraft: TimelineDraft = {
  title: "",
  description: "",
  event_type: "publication",
  start_year: "",
  end_year: "",
  date_label: "",
  source: "",
  evidence_page: "",
  evidence_printed_label: "",
  evidence_text: "",
  confidence: 1,
  review_status: "suggested",
  display_order: 0,
  nodes: [],
  disciplines: [],
  scholar: "",
  work: "",
};

function timelineToDraft(event: TimelineEvent): TimelineDraft {
  return {
    title: event.title,
    description: event.description,
    event_type: event.event_type,
    start_year: event.start_year?.toString() ?? "",
    end_year: event.end_year?.toString() ?? "",
    date_label: event.date_label,
    source: event.source,
    evidence_page: event.evidence_page?.toString() ?? "",
    evidence_printed_label: event.evidence_printed_label,
    evidence_text: event.evidence_text,
    confidence: event.confidence,
    review_status: event.review_status,
    display_order: event.display_order,
    nodes: event.relations.filter((item) => item.node).map((item) => item.node as string),
    disciplines: event.relations.filter((item) => item.discipline).map((item) => item.discipline as string),
    scholar: event.scholar ?? event.relations.find((item) => item.scholar)?.scholar ?? "",
    work: event.work ?? event.relations.find((item) => item.work)?.work ?? "",
  };
}

export function NormalizedTimelineAdmin() {
  const [editing, setEditing] = useState<TimelineEvent | null>(null);
  const [draft, setDraft] = useState<TimelineDraft>(emptyTimelineDraft);
  const [disciplineFilter, setDisciplineFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [messageState, setMessageState] = useState<ActionState>("idle");
  const { pendingAction, startAction, finishAction } = useActionGuard();
  const [entityLabels, setEntityLabels] = useState<Record<string, string>>({});

  const params = useMemo(() => {
    const search = new URLSearchParams();
    if (disciplineFilter) search.set("discipline", disciplineFilter);
    if (typeFilter) search.set("event_type", typeFilter);
    if (statusFilter) search.set("review_status", statusFilter);
    if (query.trim()) search.set("q", query.trim());
    return search.toString();
  }, [disciplineFilter, typeFilter, statusFilter, query]);
  const events = useAdminData<Page<TimelineEvent>>(`/catalog/admin/theory-timeline/?${params}`);
  const nodes = useAdminData<Page<KnowledgeNode>>("/catalog/admin/theory-system/nodes/");
  const disciplines = useAdminData<Page<Discipline>>("/catalog/admin/disciplines/");
  const works = useAdminData<Page<WorkCompact>>("/catalog/works/");
  const scholars = useAdminData<Page<ScholarCompact>>("/catalog/admin/scholars/");

  function start(event?: TimelineEvent) {
    setEditing(event ?? null);
    setDraft(event ? timelineToDraft(event) : { ...emptyTimelineDraft });
    setMessage("");
    setMessageState("idle");
    setEntityLabels({});
  }

  async function saveEvent(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = editing ? `save-timeline-event:${editing.id}` : "create-timeline-event";
    if (!startAction(actionKey)) return;
    setMessage(editing ? "正在保存时间轴事件……" : "正在创建时间轴事件……");
    setMessageState("pending");
    const relations: TimelineRelation[] = [
      ...draft.nodes.map((node, index) => ({ relation_type: "subject", node, discipline: null, scholar: null, work: null, evidence: null, description: "", sort_order: index })),
      ...draft.disciplines.map((discipline, index) => ({ relation_type: "context", node: null, discipline, scholar: null, work: null, evidence: null, description: "", sort_order: draft.nodes.length + index })),
    ];
    const payload = {
      title: draft.title,
      description: draft.description,
      event_type: draft.event_type,
      start_year: draft.start_year ? Number(draft.start_year) : null,
      end_year: draft.end_year ? Number(draft.end_year) : null,
      date_label: draft.date_label,
      orientation: "neutral",
      source: draft.source,
      evidence_page: draft.evidence_page ? Number(draft.evidence_page) : null,
      evidence_printed_label: draft.evidence_printed_label,
      evidence_text: draft.evidence_text,
      confidence: draft.confidence,
      review_status: draft.review_status,
      display_order: draft.display_order,
      discipline: null,
      theory_school: null,
      subdiscipline: null,
      scholar: draft.scholar || null,
      work: draft.work || null,
      relations,
    };
    try {
      const saved = await apiRequest<TimelineEvent>(`/catalog/admin/theory-timeline/${editing ? `${editing.id}/` : ""}`, { method: editing ? "PATCH" : "POST", body: JSON.stringify(payload) }, token);
      setEditing(saved);
      setDraft(timelineToDraft(saved));
      setMessage("时间轴事件已保存。只有确认发布的事件会进入公共时间轴。");
      setMessageState("success");
      events.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "事件保存失败");
      setMessageState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  async function removeEvent() {
    if (!editing || !window.confirm(`删除“${editing.title}”吗？`)) return;
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = `delete-timeline-event:${editing.id}`;
    if (!startAction(actionKey)) return;
    setMessage("正在删除时间轴事件……");
    setMessageState("pending");
    try {
      await apiRequest(`/catalog/admin/theory-timeline/${editing.id}/`, { method: "DELETE" }, token);
      setEditing(null);
      setDraft({ ...emptyTimelineDraft });
      setMessage("时间轴事件已删除。");
      setMessageState("success");
      events.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "删除失败");
      setMessageState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  const timelineNodeName = (id: string) => nodes.data?.results.find((item) => item.id === id)?.canonical_name_zh || entityLabels[id] || "已选择节点";
  const timelineDisciplineName = (id: string) => disciplines.data?.results.find((item) => item.id === id)?.name || entityLabels[id] || "已选择学科";
  const timelineScholarName = (id: string) => scholars.data?.results.find((item) => item.id === id)?.preferred_name || entityLabels[id] || "已选择学者";
  const timelineWorkName = (id: string) => works.data?.results.find((item) => item.id === id)?.title || entityLabels[id] || "已选择馆藏";

  return (
    <AdminFrame eyebrow="理论时间轴" title="时间轴事件管理" description="管理有来源、有审核状态的理论历史事件。出版年份或关键词共现不会自动成为公共事件。" actions={<Link className="admin-outline-button" href="/theories/timeline" target="_blank">预览前台 <ExternalLink size={14} /></Link>}>
      <div className="timeline-admin-grid">
        <section className="admin-panel normalized-timeline-list">
          <div className="theory-admin-filters timeline">
            <ResearchEntityPicker label="学科筛选" endpoint="/catalog/admin/disciplines/" entityType="discipline" step="maintenance_theory_timeline" field="filter_discipline" values={onePickerValue(disciplineFilter, timelineDisciplineName(disciplineFilter))} onChange={(next) => { const picked = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDisciplineFilter(picked?.id ?? ""); }} />
            <label><span>事件类型</span><select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}><option value="">全部</option>{timelineTypes.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
            <label><span>审核状态</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">全部</option><option value="suggested">候选</option><option value="approved">已发布</option><option value="rejected">已拒绝</option></select></label>
            <label className="theory-admin-search"><span>标题或来源</span><div><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索事件……" /></div></label>
          </div>
          <header className="timeline-list-actions"><button className="button" type="button" onClick={() => start()}><Plus size={15} />新建事件</button><button type="button" onClick={events.refresh}><RefreshCw size={15} />刷新</button></header>
          <ErrorNotice message={events.error} retry={events.refresh} />
          <div className="theory-admin-table-wrap"><table className="theory-admin-table"><thead><tr><th>显示时期</th><th>事件标题</th><th>事件类型</th><th>关联节点</th><th>证据页码</th><th>来源</th><th>状态</th><th>排序</th></tr></thead><tbody>{events.data?.results.map((item) => <tr className={editing?.id === item.id ? "selected" : ""} key={item.id} role="button" tabIndex={0} aria-label={`编辑时间轴事件 ${item.title}`} onClick={() => start(item)} onKeyDown={(event) => activateOnEnterOrSpace(event, () => start(item))}><td><strong>{item.date_label || item.start_year || "待定"}</strong>{item.end_year ? <small>至 {item.end_year}</small> : null}</td><td><strong>{item.title}</strong><small>{item.description}</small></td><td>{timelineTypes.find(([value]) => value === item.event_type)?.[1] || item.event_type}</td><td>{item.relations.filter((relation) => relation.node).map((relation) => relation.node_name).join("、") || "—"}</td><td>{item.evidence_page || "—"}</td><td>{item.source || "—"}</td><td><StatusBadge value={item.review_status} /></td><td>{item.display_order}</td></tr>)}</tbody></table></div>
          {!events.loading && !events.data?.results.length ? <div className="theory-admin-empty"><Clock3 size={22} /><strong>没有符合筛选条件的事件</strong></div> : null}
          <footer className="theory-admin-count">共 {events.data?.count ?? 0} 条事件</footer>
        </section>

        <form className="admin-panel timeline-event-editor" onSubmit={saveEvent}>
          <header><div><h2>{editing ? "编辑事件" : "新建事件"}</h2><p>来源和证据会显示在管理端，读者只看到发布内容。</p></div>{editing ? <ActionButton type="button" state={pendingAction === `delete-timeline-event:${editing.id}` ? "pending" : "idle"} pendingLabel="删除中" disabled={Boolean(pendingAction) && pendingAction !== `delete-timeline-event:${editing.id}`} onClick={() => void removeEvent()}><Trash2 size={14} />删除</ActionButton> : null}</header>
          <label><span>事件标题</span><input required value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
          <label><span>说明</span><textarea rows={4} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
          <div className="inline-fields"><label><span>开始年</span><input type="number" value={draft.start_year} onChange={(event) => setDraft({ ...draft, start_year: event.target.value })} /></label><label><span>结束年</span><input type="number" value={draft.end_year} onChange={(event) => setDraft({ ...draft, end_year: event.target.value })} /></label></div>
          <div className="inline-fields"><label><span>显示时期</span><input value={draft.date_label} onChange={(event) => setDraft({ ...draft, date_label: event.target.value })} placeholder="例如 20世纪中期" /></label><label><span>事件类型</span><select value={draft.event_type} onChange={(event) => setDraft({ ...draft, event_type: event.target.value })}>{timelineTypes.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label></div>
          <ResearchEntityPicker label="理论传统和知识节点，可多选" endpoint="/catalog/admin/theory-system/nodes/" entityType="knowledge_node" step="maintenance_theory_timeline" field="nodes" multiple values={manyPickerValues(draft.nodes, timelineNodeName)} onChange={(next) => { setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, nodes: next.flatMap((value) => value.id ? [value.id] : []) }); }} />
          <ResearchEntityPicker label="关联学科，可多选" endpoint="/catalog/admin/disciplines/" entityType="discipline" step="maintenance_theory_timeline" field="disciplines" multiple values={manyPickerValues(draft.disciplines, timelineDisciplineName)} onChange={(next) => { setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, disciplines: next.flatMap((value) => value.id ? [value.id] : []) }); }} />
          <div className="inline-fields"><ResearchEntityPicker label="关联学者" endpoint="/catalog/admin/scholars/" entityType="person" step="maintenance_theory_timeline" field="scholar" values={onePickerValue(draft.scholar, timelineScholarName(draft.scholar))} onChange={(next) => { const picked = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, scholar: picked?.id ?? "" }); }} /><ResearchEntityPicker label="关联馆藏" endpoint="/catalog/admin/library/works/" entityType="work" step="maintenance_theory_timeline" field="work" values={onePickerValue(draft.work, timelineWorkName(draft.work))} onChange={(next) => { const picked = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, work: picked?.id ?? "" }); }} /></div>
          <label><span>来源</span><input value={draft.source} onChange={(event) => setDraft({ ...draft, source: event.target.value })} placeholder="书目、论文或馆藏来源" /></label>
          <div className="inline-fields"><label><span>证据页码</span><input type="number" value={draft.evidence_page} onChange={(event) => setDraft({ ...draft, evidence_page: event.target.value })} /></label><label><span>印刷页码</span><input value={draft.evidence_printed_label} onChange={(event) => setDraft({ ...draft, evidence_printed_label: event.target.value })} /></label></div>
          <label><span>证据原文或来源说明</span><textarea rows={4} value={draft.evidence_text} onChange={(event) => setDraft({ ...draft, evidence_text: event.target.value })} /></label>
          <div className="inline-fields three"><label><span>审核状态</span><select value={draft.review_status} onChange={(event) => setDraft({ ...draft, review_status: event.target.value })}><option value="suggested">候选</option><option value="approved">发布</option><option value="rejected">拒绝</option></select></label><label><span>排序</span><input type="number" value={draft.display_order} onChange={(event) => setDraft({ ...draft, display_order: Number(event.target.value) })} /></label><label><span>置信度</span><input type="number" min={0} max={1} step={0.01} value={draft.confidence} onChange={(event) => setDraft({ ...draft, confidence: Number(event.target.value) })} /></label></div>
          <section className="timeline-draft-preview" aria-live="polite">
            <header><strong>时间轴发布预览</strong><StatusBadge value={draft.review_status} /></header>
            <div><time>{draft.date_label || draft.start_year || "时期待定"}</time><i /><article><strong>{draft.title || "事件标题将在这里显示"}</strong><span>{timelineTypes.find(([value]) => value === draft.event_type)?.[1] || draft.event_type}</span><p>{draft.description || "填写说明后，前台会以紧凑事件卡显示。"}</p></article></div>
            <footer>{draft.nodes.length ? `关联 ${draft.nodes.map(timelineNodeName).filter(Boolean).join("、")}` : "可独立关联学科、理论、学者或馆藏，不强制绑定馆藏。"}</footer>
          </section>
          <ActionButton className="button" type="submit" state={pendingAction?.startsWith("save-timeline-event:") || pendingAction === "create-timeline-event" ? "pending" : "idle"} pendingLabel="正在保存事件" disabled={Boolean(pendingAction) && !(pendingAction?.startsWith("save-timeline-event:") || pendingAction === "create-timeline-event")}><Save size={15} />{draft.review_status === "approved" ? "保存并发布" : "保存事件"}</ActionButton>
          {message ? <AsyncStatus state={messageState} message={message} /> : null}
        </form>
      </div>
    </AdminFrame>
  );
}

type ReadingPathItem = {
  id?: string;
  stage_name: string;
  stage_description: string;
  node: string | null;
  node_data?: KnowledgeNode | null;
  work: string | null;
  work_data?: WorkCompact | null;
  recommendation_reason: string;
  reading_order: number;
  is_required: boolean;
  editorial_note: string;
};

type ReadingPath = {
  id: string;
  title: string;
  slug: string;
  introduction: string;
  primary_discipline: string | null;
  primary_discipline_data: Discipline | null;
  audience: string;
  difficulty: string;
  estimated_reading: string;
  cover_url: string;
  status: string;
  sort_order: number;
  items: ReadingPathItem[];
  updated_at: string;
};

const emptyPathDraft = { title: "", slug: "", introduction: "", primary_discipline: "", audience: "", difficulty: "beginner", estimated_reading: "", status: "draft", sort_order: 0 };

function emptyPathItem(order: number): ReadingPathItem {
  return { stage_name: `第 ${order + 1} 阶段`, stage_description: "", node: null, work: null, recommendation_reason: "", reading_order: order, is_required: false, editorial_note: "" };
}

export function ReadingPathsAdmin() {
  const paths = useAdminData<Page<ReadingPath>>("/catalog/admin/theory-system/reading-paths/");
  const nodes = useAdminData<Page<KnowledgeNode>>("/catalog/admin/theory-system/nodes/");
  const disciplines = useAdminData<Page<Discipline>>("/catalog/admin/disciplines/");
  const works = useAdminData<Page<WorkCompact>>("/catalog/works/");
  const [editing, setEditing] = useState<ReadingPath | null>(null);
  const [draft, setDraft] = useState({ ...emptyPathDraft });
  const [items, setItems] = useState<ReadingPathItem[]>([]);
  const [cover, setCover] = useState<File | null>(null);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [messageState, setMessageState] = useState<ActionState>("idle");
  const { pendingAction, startAction, finishAction } = useActionGuard();

  function start(path?: ReadingPath) {
    setEditing(path ?? null);
    setDraft(path ? { title: path.title, slug: path.slug, introduction: path.introduction, primary_discipline: path.primary_discipline ?? "", audience: path.audience, difficulty: path.difficulty, estimated_reading: path.estimated_reading, status: path.status, sort_order: path.sort_order } : { ...emptyPathDraft });
    setItems(path ? path.items.map((item, index) => ({ ...item, reading_order: index })) : [emptyPathItem(0)]);
    setCover(null);
    setMessage("");
    setMessageState("idle");
  }

  function updateItem(index: number, patch: Partial<ReadingPathItem>) {
    setItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
  }

  function moveItem(from: number, to: number) {
    if (to < 0 || to >= items.length || from === to) return;
    setItems((current) => {
      const next = [...current];
      const [item] = next.splice(from, 1);
      next.splice(to, 0, item);
      return next.map((row, index) => ({ ...row, reading_order: index }));
    });
  }

  async function savePath(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = editing ? `save-reading-path:${editing.id}` : "create-reading-path";
    if (!startAction(actionKey)) return;
    setMessage(editing ? "正在保存阅读路径……" : "正在创建阅读路径……");
    setMessageState("pending");
    const payload = {
      ...draft,
      expected_updated_at: editing?.updated_at,
      primary_discipline: draft.primary_discipline || null,
      items: items.map((item, index) => ({
        stage_name: item.stage_name,
        stage_description: item.stage_description,
        node: item.node || null,
        work: item.work || null,
        recommendation_reason: item.recommendation_reason,
        reading_order: index,
        is_required: item.is_required,
        editorial_note: item.editorial_note,
      })),
    };
    try {
      const saved = await apiRequest<ReadingPath>(`/catalog/admin/theory-system/reading-paths/${editing ? `${editing.id}/` : ""}`, { method: editing ? "PATCH" : "POST", body: JSON.stringify(payload) }, token);
      if (cover) {
        const body = new FormData();
        body.append("cover_asset", cover);
        await apiRequest(`/catalog/admin/theory-system/reading-paths/${saved.id}/`, { method: "PATCH", body }, token);
      }
      setEditing(saved);
      setMessage("阅读路径已保存。公开页面会按这里的阶段和顺序呈现。");
      setMessageState("success");
      paths.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "保存失败");
      setMessageState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  async function removePath() {
    if (!editing || !window.confirm(`删除阅读路径“${editing.title}”吗？`)) return;
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = `delete-reading-path:${editing.id}`;
    if (!startAction(actionKey)) return;
    setMessage("正在删除阅读路径……");
    setMessageState("pending");
    try {
      await apiRequest(`/catalog/admin/theory-system/reading-paths/${editing.id}/`, { method: "DELETE" }, token);
      setEditing(null);
      setItems([]);
      setMessage("阅读路径已删除。");
      setMessageState("success");
      paths.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "删除失败");
      setMessageState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  return (
    <AdminFrame eyebrow="策展阅读" title="阅读路径管理" description="用阶段、理论节点和馆藏文献组织可维护的阅读顺序。拖动阶段即可调整公开顺序。" actions={<button className="button" type="button" onClick={() => start()}><Plus size={15} />新建路径</button>}>
      <div className="reading-path-admin-grid">
        <section className="admin-panel reading-path-list"><header><h2>路径列表</h2><button type="button" onClick={paths.refresh}><RefreshCw size={14} />刷新</button></header><ErrorNotice message={paths.error} retry={paths.refresh} />{paths.data?.results.map((path) => <article className={editing?.id === path.id ? "selected" : ""} key={path.id} role="button" tabIndex={0} aria-label={`编辑阅读路径 ${path.title}`} onClick={() => start(path)} onKeyDown={(event) => activateOnEnterOrSpace(event, () => start(path))}><div className="reading-path-number">{String(path.sort_order + 1).padStart(2, "0")}</div><div><strong>{path.title}</strong><p>{path.introduction || "尚未填写简介"}</p><small>{path.primary_discipline_data?.name || "跨学科"} · {path.items.length} 个阶段 · {path.difficulty === "beginner" ? "入门" : path.difficulty === "intermediate" ? "进阶" : "深入"}</small></div><StatusBadge value={path.status} /><ArrowRight size={15} /></article>)}{!paths.loading && !paths.data?.results.length ? <div className="theory-admin-empty"><BookOpen size={22} /><strong>尚未建立阅读路径</strong></div> : null}</section>

        <form className="admin-panel reading-path-editor" onSubmit={savePath}>
          <header><div><h2>{editing ? `编辑 ${editing.title}` : "新建阅读路径"}</h2><p>每个阶段至少关联一个理论节点或馆藏文献。</p></div>{editing ? <div><Link href={`/theories/reading-paths/${editing.slug}`} target="_blank">预览 <ExternalLink size={13} /></Link><ActionButton type="button" state={pendingAction === `delete-reading-path:${editing.id}` ? "pending" : "idle"} pendingLabel="删除中" disabled={Boolean(pendingAction) && pendingAction !== `delete-reading-path:${editing.id}`} aria-label={`删除阅读路径 ${editing.title}`} onClick={() => void removePath()}><Trash2 size={14} /></ActionButton></div> : null}</header>
          <div className="inline-fields"><label><span>标题</span><input required value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label><span>固定链接</span><input required value={draft.slug} onChange={(event) => setDraft({ ...draft, slug: event.target.value })} /></label></div>
          <label><span>简介</span><textarea rows={4} value={draft.introduction} onChange={(event) => setDraft({ ...draft, introduction: event.target.value })} /></label>
          <div className="inline-fields three"><label><span>主要学科</span><select value={draft.primary_discipline} onChange={(event) => setDraft({ ...draft, primary_discipline: event.target.value })}><option value="">跨学科</option>{disciplines.data?.results.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label><span>适合人群</span><input value={draft.audience} onChange={(event) => setDraft({ ...draft, audience: event.target.value })} /></label><label><span>难度</span><select value={draft.difficulty} onChange={(event) => setDraft({ ...draft, difficulty: event.target.value })}><option value="beginner">入门</option><option value="intermediate">进阶</option><option value="advanced">深入</option></select></label></div>
          <div className="inline-fields three"><label><span>预计阅读量</span><input value={draft.estimated_reading} onChange={(event) => setDraft({ ...draft, estimated_reading: event.target.value })} placeholder="例如 6 部作品" /></label><label><span>状态</span><select value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}><option value="draft">草稿</option><option value="pending">提交审核</option><option value="published">发布</option><option value="archived">下线</option></select></label><label><span>排序</span><input type="number" value={draft.sort_order} onChange={(event) => setDraft({ ...draft, sort_order: Number(event.target.value) })} /></label></div>
          <label className="knowledge-image-upload"><ImagePlus size={18} /><span>{cover?.name || "上传黑白几何封面"}</span><input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setCover(event.target.files?.[0] ?? null)} /></label>
          <section className="reading-path-items"><header><div><h3>路径阶段</h3><p>拖动卡片或使用上下按钮调整顺序。</p></div><button type="button" onClick={() => setItems([...items, emptyPathItem(items.length)])}><Plus size={14} />添加阶段</button></header>{items.map((item, index) => <article draggable key={item.id || index} onDragStart={() => setDragIndex(index)} onDragOver={(event) => event.preventDefault()} onDrop={() => { if (dragIndex !== null) moveItem(dragIndex, index); setDragIndex(null); }}><header><span>{index + 1}</span><input aria-label={`第 ${index + 1} 阶段名称`} value={item.stage_name} onChange={(event) => updateItem(index, { stage_name: event.target.value })} /><div><button type="button" aria-label={`上移第 ${index + 1} 阶段`} disabled={index === 0} onClick={() => moveItem(index, index - 1)}><ArrowUp size={13} /></button><button type="button" aria-label={`下移第 ${index + 1} 阶段`} disabled={index === items.length - 1} onClick={() => moveItem(index, index + 1)}><ArrowDown size={13} /></button><button type="button" aria-label={`删除第 ${index + 1} 阶段`} onClick={() => setItems(items.filter((_, itemIndex) => itemIndex !== index).map((row, order) => ({ ...row, reading_order: order })))}><Trash2 size={13} /></button></div></header><label><span>阶段说明</span><textarea rows={2} value={item.stage_description} onChange={(event) => updateItem(index, { stage_description: event.target.value })} /></label><div className="inline-fields"><label><span>理论节点</span><select value={item.node || ""} onChange={(event) => updateItem(index, { node: event.target.value || null })}><option value="">无</option>{nodes.data?.results.map((node) => <option value={node.id} key={node.id}>{node.canonical_name_zh}</option>)}</select></label><label><span>馆藏文献</span><select value={item.work || ""} onChange={(event) => updateItem(index, { work: event.target.value || null })}><option value="">无</option>{works.data?.results.map((work) => <option value={work.id} key={work.id}>{work.title}</option>)}</select></label></div><label><span>推荐理由</span><textarea rows={2} value={item.recommendation_reason} onChange={(event) => updateItem(index, { recommendation_reason: event.target.value })} /></label><label className="reading-required"><input type="checkbox" checked={item.is_required} onChange={(event) => updateItem(index, { is_required: event.target.checked })} />设为必读</label></article>)}</section>
          <ActionButton className="button" type="submit" state={pendingAction?.startsWith("save-reading-path:") || pendingAction === "create-reading-path" ? "pending" : "idle"} pendingLabel="正在保存阅读路径" disabled={Boolean(pendingAction) && !(pendingAction?.startsWith("save-reading-path:") || pendingAction === "create-reading-path")}><Save size={15} />{draft.status === "published" ? "保存并发布" : "保存阅读路径"}</ActionButton>
          {message ? <AsyncStatus state={messageState} message={message} /> : null}
        </form>
      </div>
    </AdminFrame>
  );
}
