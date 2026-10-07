"use client";

import { editorialHeaders, isEditorialConflict } from "@/lib/editorial-version";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { buildTheoryNodePayload, theoryNodeToDraft as nodeToDraft, type TheoryNodeDraft } from "@/lib/theory-node-draft";
import { buildRelationPayload, buildTimelinePayload, relationToDraft, timelineToDraft, emptyTimelineDraft, type TimelineDraft, type TimelineRecord } from "@/lib/relation-timeline-draft";
import { EditorialPrefillNotice, useEditorialPrefills } from "@/components/admin/curation/editorial-prefills";
import { safeAdminHref } from "@/lib/admin-route-context";
import type { CollectionPage, WorkLibraryRow } from "@/lib/api/admin-collections";
import { EditorialConflictHelp } from "@/components/admin/knowledge/editorial-conflict-help";
import { CurationSelectionPreview } from "@/components/admin/curation/curation-draft-queue";

import {
  BookOpen,
  Check,
  Clock3,
  ExternalLink,
  GitMerge,
  History,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { FixedPageEditor } from "@/components/admin/curation/fixed-page-editor";
import { PreviewSurface, type KnowledgePreviewPayload } from "@/components/admin/preview/knowledge-page-preview";
import type { KnowledgeNodeDetail, NormalizedTimelineEvent } from "@/lib/api/knowledge.types";
import { KnowledgeVisualEditor } from "@/components/admin/knowledge/knowledge-visual-editor";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { adminListHref, adminPageNumber } from "@/lib/admin-route-context";
import { KnowledgeImagePanel } from "./admin/media/knowledge-image-panel";
import type { FormEvent, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { EntityLifecycleActions } from "@/components/entity-lifecycle-actions";
import { CurationFieldAssistant } from "@/components/admin/curation/curation-field-assistant";
import { asRecord, asString } from "@/components/admin/workflow/workflow-types";
import { ResearchEntityPicker } from "@/components/admin/research/research-entity-picker";
import { EntityPicker, type EntityValue } from "@/components/admin/forms/workflow-fields";
import {
  StringListEditor,
  StructuredRowsEditor,
} from "@/components/structured-editors";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useActionGuard } from "@/lib/use-action-guard";
import { ActionButton, AsyncStatus, type ActionState } from "@/components/action-feedback";
import {
  KnowledgeObjectContextPanel,
  type KnowledgeObjectType,
} from "@/components/admin/knowledge/knowledge-object-context-panel";

type Page<T> = { count: number; next?: string | null; previous?: string | null; results: T[] };

function useEditorListLocation() {
  const search = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const href = (updates: Record<string, string | number | null>) => adminListHref(pathname, search.toString(), updates);
  return { search, href, update: (updates: Record<string, string | number | null>) => router.replace(href(updates), { scroll: false }) };
}

function EditorListPages({ data, page, pageKey, label, ordering, busy, href }: {
  data: Page<unknown> | null; page: number; pageKey: string; label: string; ordering: string; busy: boolean;
  href: (updates: Record<string, string | number | null>) => string;
}) {
  return <footer className="theory-admin-pagination" aria-busy={busy}>
    <span aria-live="polite">{data ? `共 ${data.count} 条，${ordering}` : busy ? "正在读取列表…" : "列表暂未读取成功"}</span>
    <nav aria-label={label}>
      {page > 1 ? <Link href={href({ [pageKey]: 1 })} scroll={false}>第一页</Link> : null}
      {!busy && data?.previous ? <Link href={href({ [pageKey]: page - 1 })} scroll={false}>上一页</Link> : <span aria-disabled="true">上一页</span>}
      <span>第 {page} 页</span>
      {!busy && data?.next ? <Link href={href({ [pageKey]: page + 1 })} scroll={false}>下一页</Link> : <span aria-disabled="true">下一页</span>}
    </nav>
  </footer>;
}

function knowledgeStudioNodeType(nodeType: string): KnowledgeObjectType {
  if (nodeType === "concept") return "concept";
  if (nodeType === "debate") return "debate";
  if (nodeType === "research_problem") return "research_problem";
  return "theory";
}

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

type NodeSubdisciplineLink = {
  id?: string;
  subdiscipline: Discipline & { discipline_id: string };
  is_primary: boolean;
  relation_role: string;
  source: string;
  confidence: number;
  sort_order: number;
  status: string;
};

type NodeTopicLink = {
  id?: string;
  topic: { id: string; name: string; slug: string };
  relation_label: string;
  source: string;
  confidence: number;
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
  subdiscipline_links: NodeSubdisciplineLink[];
  topic_links: NodeTopicLink[];
  work_count: number;
  relation_count: number;
  cover_url: string;
  updated_at: string;
  editorial_revision?: EditorialRevisionSummary;
};

type EditorialRevisionSummary = {
  id: string;
  revision: number;
  changed_fields: string[];
  status: "draft" | "published" | "superseded";
  has_conflict?: boolean;
  publish_url: string;
  updated_at?: string;
};

function SavedDraftActions({ revision, dirty, busy, impact, publish }: { revision?: EditorialRevisionSummary; dirty: boolean; busy: boolean; impact: string; publish: () => void }) {
  const canPublish = hasAdminCapability(useAdminSession(), "can_publish_authority");
  if (!revision) return null;
  return <section className="form-message" aria-label="待发布修改">
    <p>修改已保存{revision.updated_at ? `（${asDate(revision.updated_at)}）` : ""}，读者看到的内容尚未改变。</p>
    <p>{impact}</p>
    {dirty ? <p>还有未保存的输入，请先保存再发布。</p> : null}
    {revision.has_conflict ? <p>公开内容已变化，请打开最新内容核对。</p> : null}
    <ActionButton type="button" className="button" disabled={busy || dirty || !canPublish || revision.has_conflict} onClick={publish}>确认发布已保存的修改</ActionButton>
    {!canPublish ? <p>当前账户可以保存修改，但没有正式发布权限。</p> : null}
  </section>;
}

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

const editableNodeTypeEntries = Object.entries(nodeTypeLabels).filter(
  ([value]) => value !== "subdiscipline",
);

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

function useAdminData<T>(path: string | null) {
  const [result, setResult] = useState<{ path: string | null; data: T | null; error: string }>({ path: null, data: null, error: "" });
  const [loading, setLoading] = useState(Boolean(path));
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
        setResult({ path, data: payload, error: "" });
      })
      .catch((reason) => {
        if (!active) return;
        setResult((previous) => ({ path, data: previous.path === path ? previous.data : null, error: reason instanceof Error ? reason.message : "读取失败" }));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [path, revision]);

  const current = result.path === path;
  return { data: current ? result.data : null, loading: Boolean(path && (loading || !current)), error: current ? result.error : "", refresh };
}

function AdminFrame({ eyebrow, title, description, actions, children, className = "", hideHeader = false }: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  hideHeader?: boolean;
}) {
  return (
    <div className={`admin-page theory-system-admin ${className}`}>
      {!hideHeader ? <header className="admin-page-title theory-admin-title">
        <div><p>{eyebrow}</p><h1>{title}</h1><span>{description}</span></div>
        {actions ? <div className="theory-admin-title-actions">{actions}</div> : null}
      </header> : null}
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

type NodeDraft = TheoryNodeDraft;

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
  subdisciplines: [],
  topics: [],
  status: "draft",
  sort_order: 0,
};


export function TheoryNodesAdmin({ initialNodeId = "" }: { initialNodeId?: string }) {
  const search = useSearchParams();
  const nodeId = initialNodeId || search.get("node") || "";
  const legacyId = search.get("legacy_id") || "";
  if (search.get("section") === "timeline") return <TimelineEditor key={`${nodeId}:${search.get("event") || "list"}`} nodeId={nodeId} requestedId={search.get("event") || ""} />;
  if (!nodeId && !legacyId && search.get("create") !== "1") return <TheoryNodesDirectory />;
  return <TheoryNodesEditor key={`${nodeId}:${legacyId}`} initialNodeId={nodeId} initialLegacyId={legacyId} />;
}

function TheoryNodesDirectory() {
  const location = useEditorListLocation();
  const page = adminPageNumber(location.search.get("page"));
  const query = location.search.get("q") || "";
  const type = location.search.get("node_type") || "";
  const params = new URLSearchParams({ page: String(page), q: query, type });
  const nodes = useAdminData<Page<KnowledgeNode>>(`/catalog/admin/theory-system/nodes/?${params}`);
  const [selectedId, setSelectedId] = useState("");
  const selected = nodes.data?.results.find(node => node.id === selectedId) || nodes.data?.results[0];
  const returnTo = location.href({});
  return <AdminFrame eyebrow="理论流派" title="理论流派管理" description="选择流派或概念继续编辑" actions={<Link className="button secondary" href="/admin/theories?create=1">新建流派或概念</Link>}>
    <form className="theory-directory-toolbar" onSubmit={event => { event.preventDefault(); location.update({ page: 1, q: String(new FormData(event.currentTarget).get("q") || "").trim() }); }}>
      <label><Search size={17}/><input key={query} type="search" name="q" defaultValue={query} aria-label="搜索流派名称、原名或关键词" placeholder="搜索流派名称、原名或关键词"/></label>
      <select aria-label="资料类型" value={type} onChange={event => location.update({ page: 1, node_type: event.target.value })}><option value="">全部类型</option>{editableNodeTypeEntries.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
      <button type="submit" className="button secondary">搜索</button>
    </form>
    <div className="knowledge-directory-reference theory-directory-reference"><section className="admin-panel">
      <ErrorNotice message={nodes.error} retry={nodes.refresh}/>
      {nodes.loading ? <p role="status">正在读取流派与概念…</p> : null}
      <table className="theory-directory-table"><thead><tr><th>名称</th><th>类型</th><th>主要领域</th><th>操作</th></tr></thead><tbody>{nodes.data?.results.map(node => <tr key={node.id} className={selected?.id === node.id ? "selected" : ""}>
        <td><button type="button" className="reference-select-title" aria-pressed={selected?.id === node.id} onClick={() => setSelectedId(node.id)}>{node.canonical_name_zh}<small>{node.canonical_name_en}</small></button></td>
        <td>{nodeTypeLabels[node.node_type] || "—"}</td><td>{node.primary_discipline_data?.name || "—"}</td>
        <td><Link className={`button${selected?.id === node.id ? "" : " secondary"}`} href={`/admin/theories/${node.id}`}>编辑</Link></td>
      </tr>)}</tbody></table>
      {!nodes.loading && !nodes.error && !nodes.data?.results.length ? <p className="empty-state">当前条件下没有流派或概念。</p> : null}
      <EditorListPages data={nodes.data} page={page} pageKey="page" label="流派与概念分页" ordering="按显示顺序排列" busy={nodes.loading} href={location.href}/>
    </section><CurationSelectionPreview key={selected?.id || "empty"} item={selected ? {object_type:"knowledge_node",object_id:selected.id,title:selected.canonical_name_zh,label:nodeTypeLabels[selected.node_type] || "理论流派",edit_url:`/admin/theories/${selected.id}`,can_edit:true} : undefined} returnTo={returnTo}/></div>
  </AdminFrame>;
}

function TheoryNodesEditor({ initialNodeId, initialLegacyId }: { initialNodeId: string; initialLegacyId: string }) {
  const router = useRouter();
  const theoryLocation = useEditorListLocation();
  const nodePage = adminPageNumber(theoryLocation.search.get("page"));
  const [editConflict, setEditConflict] = useState(false);
  const [nodeType, setNodeType] = useState("theory_tradition");
  const [legacyId, setLegacyId] = useState(initialLegacyId);
  const [legacyOpened, setLegacyOpened] = useState(false);
  const [requestedNodeId, setRequestedNodeId] = useState(initialNodeId);
  const [requestedNodeOpened, setRequestedNodeOpened] = useState(false);
  const statusFilter = theoryLocation.search.get("status") || "";
  const disciplineFilter = theoryLocation.search.get("discipline") || "";
  const query = theoryLocation.search.get("q") || "";
  const [editing, setEditing] = useState<KnowledgeNode | null>(null);
  const [draft, setDraft] = useState<NodeDraft>(emptyNodeDraft);
  const nodeDirty = useUnsavedForm(draft, editing ? nodeToDraft(editing) : emptyNodeDraft);
  const prefills = useEditorialPrefills(editing?.id || "new-theory", draft, setDraft);
  const [imageRevision, setImageRevision] = useState(0);
  const [message, setMessage] = useState("");
  const [messageState, setMessageState] = useState<ActionState>("idle");
  const { pendingAction, startAction, finishAction } = useActionGuard();
  const [entityLabels, setEntityLabels] = useState<Record<string, string>>({});
  const [versions, setVersions] = useState<Array<{ id: string; version_number: number; change_note: string; created_by_name: string; created_at: string }> | null>(null);
  const [mergeTarget, setMergeTarget] = useState("");
  const [pendingRevision, setPendingRevision] = useState<EditorialRevisionSummary | null>(null);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      const typeLabel = draft.node_type === "theory_tradition" ? "理论流派" : nodeTypeLabels[draft.node_type] || "理论条目";
      const title = `${editing ? "编辑" : "新建"}${typeLabel}${draft.canonical_name_zh ? ` · ${draft.canonical_name_zh}` : ""}`;
      window.dispatchEvent(new CustomEvent("admin-theory-title", { detail: title }));
    });
    return () => {
      active = false;
      window.dispatchEvent(new CustomEvent("admin-theory-title", { detail: "" }));
    };
  }, [editing, draft.node_type, draft.canonical_name_zh]);

  const params = useMemo(() => {
    const search = new URLSearchParams({ type: nodeType, page: String(nodePage) });
    if (statusFilter) search.set("status", statusFilter);
    if (disciplineFilter) search.set("discipline", disciplineFilter);
    if (query.trim()) search.set("q", query.trim());
    if (legacyId) search.set("legacy_id", legacyId);
    return search.toString();
  }, [nodeType, statusFilter, disciplineFilter, query, legacyId, nodePage]);
  const nodes = useAdminData<Page<KnowledgeNode>>(`/catalog/admin/theory-system/nodes/?${params}`);
  const allNodes = useAdminData<Page<KnowledgeNode>>("/catalog/admin/theory-system/nodes/");
  const requestedNode = useAdminData<KnowledgeNode>(
    requestedNodeId ? `/catalog/admin/theory-system/nodes/${requestedNodeId}/` : null,
  );
  const disciplines = useAdminData<Page<Discipline>>("/catalog/admin/disciplines/");

  useEffect(() => {
    const search = new URLSearchParams(window.location.search);
    const requested = search.get("node_type");
    const requestedLegacyId = search.get("legacy_id") || "";
    const requestedNode = search.get("node") || initialNodeId;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      if (requested && Object.prototype.hasOwnProperty.call(nodeTypeLabels, requested)) {
        setNodeType(requested);
        setDraft((current) => ({ ...current, node_type: requested }));
      }
      setLegacyId(requestedLegacyId);
      setRequestedNodeId(requestedNode);
    });
    return () => {
      active = false;
    };
  }, [initialNodeId]);

  useEffect(() => {
    const mapped = nodes.data?.results[0];
    if (!legacyId || legacyOpened || !mapped) return;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setEditing(mapped);
      setDraft(nodeToDraft(mapped));
      setMessage("已通过旧版映射打开理论或概念资料。后续只需在本页维护。");
      setVersions(null);
      setMergeTarget("");
      setLegacyOpened(true);
    });
    return () => {
      active = false;
    };
  }, [legacyId, legacyOpened, nodes.data]);

  useEffect(() => {
    const node = requestedNode.data;
    if (!requestedNodeId || requestedNodeOpened || !node) return;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setNodeType(node.node_type);
      setEditing(node);
      setDraft(nodeToDraft(node));
      setMessage("已从 知识管理 打开这个理论或概念资料。");
      setVersions(null);
      setMergeTarget("");
      setPendingRevision(node.editorial_revision ?? null);
      setRequestedNodeOpened(true);
    });
    return () => {
      active = false;
    };
  }, [requestedNode.data, requestedNodeId, requestedNodeOpened]);

  async function saveNode(event?: FormEvent, draftOnly = false) {
    event?.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return false;
    const actionKey = "save-theory-node";
    if (editing && !nodeDirty && !prefills.ids.length) {
      setMessage("当前没有需要保存的修改。");
      setMessageState("success");
      return true;
    }
    if (!draftOnly && draft.status === "published" && editing?.status !== "published" && !window.confirm("保存并公开这份理论或概念资料？读者将看到本页内容。")) return false;
    if (!startAction(actionKey)) return false;
    setEditConflict(false);
    setMessage("");
    setMessageState("pending");
    const payload = {
      ...buildTheoryNodePayload(draft, editing, draftOnly),
      assisted_candidates: prefills.ids,
      assisted_candidate_decisions: prefills.decisions,
    };
    try {
      const saved = await apiRequest<KnowledgeNode>(
        `/catalog/admin/theory-system/nodes/${editing ? `${editing.id}/` : ""}`,
        { method: editing ? "PATCH" : "POST", headers: editing ? editorialHeaders(editing) : undefined, body: JSON.stringify(payload) },
        token,
      );
      setEditing(saved);
      prefills.clear();
      setPendingRevision(saved.editorial_revision ?? null);
      setDraft(nodeToDraft(saved));
      if (!editing) router.replace(`/admin/theories/${saved.id}${window.location.search}`);
      setMessage(saved.editorial_revision
        ? `本页资料已保存（${new Date().toLocaleTimeString("zh-CN")}），尚未发布。公开页保持原内容，你仍在当前编辑页。`
        : `本页资料已保存（${new Date().toLocaleTimeString("zh-CN")}）。${saved.status === "published" ? "当前资料已公开。" : "尚未公开。"}你仍在当前编辑页。`);
      setMessageState("success");
      nodes.refresh();
      allNodes.refresh();
      return true;
    } catch (reason) {
      setEditConflict(isEditorialConflict(reason));
      setMessage(reason instanceof Error ? reason.message : "保存失败");
      setMessageState("error");
      return false;
    } finally {
      finishAction(actionKey);
    }
  }

  async function refreshAssistantRevision() {
    if (!editing) return;
    const [response, updated] = await Promise.all([
      apiRequest<{ results?: EditorialRevisionSummary[] }>(`/catalog/admin/editorial-revisions/?target_type=knowledge_node&target_id=${editing.id}&status=draft&limit=1`, {}, getServerSessionCredential()),
      apiRequest<KnowledgeNode>(`/catalog/admin/theory-system/nodes/${editing.id}/`, {}, getServerSessionCredential()),
    ]);
    setEditing((current) => current?.id === updated.id ? updated : current);
    setPendingRevision(response.results?.[0] ?? null);
    nodes.refresh();
    allNodes.refresh();
  }

  async function publishRevision() {
    if (!pendingRevision) return;
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = "publish-node-revision";
    if (!startAction(actionKey)) return;
    setMessageState("pending");
    try {
      if (pendingRevision.has_conflict) throw new Error("正式内容已经变化，请刷新后重新建立草稿。");
      if (nodeDirty) { setMessage("还有未保存的填写，请先保存本页，再发布已保存的修改。"); setMessageState("error"); return; }
      if (!window.confirm("发布已保存的修改？相关理论、学科页面将更新，尚未保存的输入不会发布。")) {
        setMessageState("idle");
        return;
      }
      await apiRequest(pendingRevision.publish_url, { method: "POST", body: "{}" }, token);
      if (editing) {
        const refreshed = await apiRequest<KnowledgeNode>(`/catalog/admin/theory-system/nodes/${editing.id}/`, {}, token);
        setEditing(refreshed);
        setDraft(nodeToDraft(refreshed));
      }
      setPendingRevision(null);
      setMessage("已提交发布，相关页面和搜索结果正在更新。请查看右侧公开结果。");
      setMessageState("success");
      nodes.refresh();
      allNodes.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "发布未完成，已保存内容仍保留。");
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
      if (!window.confirm(`将“${editing.canonical_name_zh}”合并到“${target?.canonical_name_zh || "保留的理论或概念"}”？\n受影响范围 ${impact || "已计算"}`)) {
        setMessage("已取消理论或概念合并。");
        setMessageState("idle");
        return;
      }
      await apiRequest(`/catalog/admin/theory-system/nodes/${editing.id}/merge/`, { method: "POST", body: JSON.stringify({ target_node: mergeTarget, change_note: "后台人工合并" }) }, token);
      setMessage("理论或概念已在事务中合并，合并记录可供管理员回滚。");
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

  const openingNode = Boolean(requestedNodeId && !requestedNodeOpened) || Boolean(legacyId && !legacyOpened);
  const disciplineName = (id: string) => disciplines.data?.results.find((item) => item.id === id)?.name || (editing?.primary_discipline_data?.id===id?editing.primary_discipline_data.name:"") || editing?.discipline_links?.find(item=>item.discipline.id===id)?.discipline.name || entityLabels[id] || "已选择学科";
  const subdisciplineName = (id: string) => editing?.subdiscipline_links?.find((item) => item.subdiscipline.id === id)?.subdiscipline.name || entityLabels[id] || "已选择子学科";
  const topicName = (id: string) => editing?.topic_links?.find((item) => item.topic.id === id)?.topic.name || entityLabels[id] || "已选择主题";
  const nodeName = (id: string) => allNodes.data?.results.find((item) => item.id === id)?.canonical_name_zh || entityLabels[id] || "已选择理论或概念";
  return (
    <AdminFrame
      eyebrow=""
      title=""
      description=""
      className="theory-reference-editor"
      hideHeader
    >
      <div className="theory-node-editor-page">
        <KnowledgeVisualEditor key={editing?.id || "new"} presentation="theory" editorTitle={`${editing ? "编辑" : "新建"}${draft.node_type==="theory_tradition"?"理论流派":nodeTypeLabels[draft.node_type] || "理论条目"}`} objectType={knowledgeStudioNodeType(editing?.node_type || draft.node_type)} objectId={editing?.id} savedRecord={editing} onPublished={() => {nodes.refresh();allNodes.refresh();requestedNode.refresh();setEditConflict(true);setMessage("发布操作已提交，请打开最新资料后继续编辑。");}} draft={{...draft,preview_labels:{...entityLabels,...Object.fromEntries((disciplines.data?.results || []).map(row=>[row.id,row.name]))}}} dirty={nodeDirty} refreshKey={`${editing?.updated_at}:${imageRevision}`}>
        {openingNode ? <div role="status"><p>正在读取指定理论或概念，载入后即可编辑。</p><ErrorNotice message={requestedNode.error || nodes.error} retry={requestedNodeId ? requestedNode.refresh : nodes.refresh} /></div> : null}
        <form id="theory-node-form" className="admin-panel theory-node-editor" onSubmit={(event) => void saveNode(event, true)} inert={openingNode} aria-busy={openingNode}>
          <EditorialPrefillNotice state={prefills} />
          <fieldset disabled={openingNode || Boolean(pendingAction)} style={{ display: "contents" }}>
          <label data-editor-section="identity"><span>中文名 <b aria-hidden="true">*</b></span><input autoComplete="off" required value={draft.canonical_name_zh} onChange={(event) => setDraft({ ...draft, canonical_name_zh: event.target.value })} /></label>
          <label data-editor-section="original-name"><span>原名 <b aria-hidden="true">*</b></span><input aria-required="true" value={draft.canonical_name_en} onChange={(event) => setDraft({ ...draft, canonical_name_en: event.target.value })} /></label>
          <div className="theory-reference-discipline" data-editor-section="primary-discipline"><EntityPicker label="所属学科" endpoint="/catalog/admin/disciplines/" singleSelect ariaRequired values={onePickerValue(draft.primary_discipline, disciplineName(draft.primary_discipline))} onChange={(next) => { const selected=next.at(-1);setEntityLabels((current)=>({...current,...pickerLabels(next)}));setDraft({...draft,primary_discipline:selected?.id??"",related_disciplines:draft.related_disciplines.filter(id=>id!==selected?.id)}); }}/></div>
          <label className="theory-reference-summary" data-editor-section="summary"><span>简介 <b aria-hidden="true">*</b></span><textarea aria-required="true" maxLength={500} rows={6} value={draft.summary} onChange={(event)=>setDraft({...draft,summary:event.target.value})}/><small>{draft.summary.length} / 500</small></label>
          <details className="theory-reference-other" data-editor-section="identity"><summary>其他信息（别名、关键词、简介来源等）</summary>
          <label><span>资料类型</span><select value={draft.node_type} onChange={(event)=>setDraft({...draft,node_type:event.target.value})}>{editableNodeTypeEntries.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
          <label><span>固定链接</span><input value={draft.slug} onChange={(event)=>setDraft({...draft,slug:event.target.value})}/></label>
          <label><span>显示顺序</span><input type="number" min={0} value={draft.sort_order} onChange={(event)=>setDraft({...draft,sort_order:Number(event.target.value)})}/></label>
          <CurationFieldAssistant
            label="名称"
            scopeId={editing?.id || "new"}
            affectedFields={["标准中文名", "外文名称"]}
            authorityType={draft.node_type === "theory_tradition" ? "theory_tradition" : draft.node_type === "subdiscipline" ? "subdiscipline" : "concept"}
            query={draft.canonical_name_en.trim() || draft.canonical_name_zh}
            onApply={(_value, suggestion) => suggestion && prefills.fill("", (current) => ({
              ...current,
              canonical_name_zh: suggestion.label || current.canonical_name_zh,
              canonical_name_en: suggestion.originalName || current.canonical_name_en,
            }))}
          />
          <details className="theory-editor-group"><summary>其他名称与译名</summary>
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
          <CurationFieldAssistant hasUnsavedChanges={nodeDirty}
            label="译名或别名"
            targetType="knowledge_node"
            targetId={editing?.id}
            fieldName="alias"
            currentValue={draft.aliases}
            query={draft.canonical_name_en.trim() || draft.canonical_name_zh}
            formContext={{ language: "zh", name: draft.canonical_name_zh, original_name: draft.canonical_name_en, node_type: draft.node_type, primary_discipline_id: draft.primary_discipline, summary: draft.summary }}
            onFillSuggestion={(candidateId, value) => {
              if (!value || typeof value !== "object") return false;
              const row = value as Record<string, unknown>;
              const alias = String(row.alias || row.name || "").trim();
              if (!alias || draft.aliases.some((item) => item.alias.normalize("NFKC").toLocaleLowerCase() === alias.normalize("NFKC").toLocaleLowerCase())) return false;
              return prefills.fill(candidateId, (current) => ({ ...current, aliases: current.aliases.concat({ alias, language: String(row.language || "und"), alias_type: String(row.alias_type || "alias") }) }));
            }}
            onAccepted={refreshAssistantRevision}
          />
          </details>
          </details>
          <label><span>完整定义</span><textarea rows={5} value={draft.definition} onChange={(event) => setDraft({ ...draft, definition: event.target.value })} /></label>
          <StringListEditor label="核心问题" itemLabel="问题" value={editorLines(draft.core_questions)} onChange={(value) => setDraft({ ...draft, core_questions: value.join("\n") })} addLabel="添加问题" />
          <StringListEditor label="基本命题" itemLabel="命题" value={editorLines(draft.basic_propositions)} onChange={(value) => setDraft({ ...draft, basic_propositions: value.join("\n") })} addLabel="添加命题" />
          <label><span>理论边界</span><textarea rows={5} value={draft.theoretical_boundary} onChange={(event) => setDraft({ ...draft, theoretical_boundary: event.target.value })} placeholder="主要解释什么、解释范围、与相邻理论的区别" /></label>
          <div className="inline-fields three" data-editor-section="content"><label><span>开始年份</span><input type="number" value={draft.start_year} onChange={(event) => setDraft({ ...draft, start_year: event.target.value })} /></label><label><span>结束年份</span><input type="number" value={draft.end_year} onChange={(event) => setDraft({ ...draft, end_year: event.target.value })} /></label><label><span>显示时期</span><input value={draft.period_label} onChange={(event) => setDraft({ ...draft, period_label: event.target.value })} /></label></div>
          <div data-editor-section="relations"><ResearchEntityPicker label="所属理论或概念" endpoint="/catalog/admin/theory-system/nodes/" entityType="knowledge_node" step="maintenance_theory_nodes" field="parent" values={onePickerValue(draft.parent,nodeName(draft.parent))} onChange={(next)=>{const selected=next.at(-1);if(selected?.id===editing?.id)return;setEntityLabels(current=>({...current,...pickerLabels(next)}));setDraft({...draft,parent:selected?.id??""});}}/></div>
          <details className="theory-editor-group" data-editor-section="relations"><summary>更多学科和主题关联</summary>
          <ResearchEntityPicker label="关联学科" endpoint="/catalog/admin/disciplines/" entityType="discipline" step="maintenance_theory_nodes" field="related_disciplines" multiple values={manyPickerValues(draft.related_disciplines, disciplineName)} onChange={(next) => { setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, related_disciplines: next.flatMap((value) => value.id && value.id !== draft.primary_discipline ? [value.id] : []) }); }} />
          <div className="inline-fields">
            <ResearchEntityPicker label="子学科" endpoint="/catalog/admin/subdisciplines/" entityType="subdiscipline" step="maintenance_theory_nodes" field="subdiscipline_links" multiple values={manyPickerValues(draft.subdisciplines, subdisciplineName)} onChange={(next) => { setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, subdisciplines: next.flatMap((value) => value.id ? [value.id] : []) }); }} />
            <ResearchEntityPicker label="主题" endpoint="/catalog/admin/topics/" entityType="topic" step="maintenance_theory_nodes" field="topic_links" multiple values={manyPickerValues(draft.topics, topicName)} onChange={(next) => { setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, topics: next.flatMap((value) => value.id ? [value.id] : []) }); }} />
          </div>
          <div className="workflow-field-assistant-row"><strong>学科分类</strong><CurationFieldAssistant label="学科分类" targetType="knowledge_node" targetId={editing?.id} fieldName="discipline" currentValue={{ primary: draft.primary_discipline, related: draft.related_disciplines }} onFillSuggestion={(candidateId, value, label) => {
            const row = asRecord(value), id = asString(row.discipline_id);
            if (!id) return false;
            if (row.relation_type === "primary") {
              if (draft.primary_discipline && draft.primary_discipline !== id && !window.confirm(`将主要学科从“${disciplineName(draft.primary_discipline)}”改为“${label}”？这一步只填写表单，尚未保存。`)) return false;
              setEntityLabels((current) => ({ ...current, [id]: label }));
              return prefills.fill(candidateId, (current) => ({ ...current, primary_discipline: id, related_disciplines: current.related_disciplines.filter((entry) => entry !== id) }));
            }
            if (id === draft.primary_discipline) return false;
            setEntityLabels((current) => ({ ...current, [id]: label }));
            return prefills.fill(candidateId, (current) => ({ ...current, related_disciplines: [...new Set([...current.related_disciplines, id])] }));
          }} lookupLabel="获取分类建议" /></div>
          <div className="workflow-field-assistant-row"><strong>子学科分类</strong><CurationFieldAssistant label="子学科分类" targetType="knowledge_node" targetId={editing?.id} fieldName="subdiscipline" currentValue={draft.subdisciplines} onFillSuggestion={(candidateId, value, label) => {
            const row = asRecord(value), id = asString(row.subdiscipline_node_id);
            if (!id) return false;
            setEntityLabels((current) => ({ ...current, [id]: label }));
            return prefills.fill(candidateId, (current) => ({ ...current, subdisciplines: [...new Set([...current.subdisciplines, id])] }));
          }} lookupLabel="获取分类建议" /></div>
          </details>
          <div data-editor-section="publication">
          {editing ? <div className="theory-node-secondary-actions"><ActionButton type="button" state={pendingAction === "load-node-versions" ? "pending" : "idle"} pendingLabel="读取中" disabled={Boolean(pendingAction) && pendingAction !== "load-node-versions"} onClick={() => void loadVersions()}><History size={14} />历史版本</ActionButton></div> : null}
          {versions ? <section className="theory-version-list"><header><strong>历史版本</strong><button type="button" aria-label="关闭历史版本" onClick={() => setVersions(null)}><X size={14} /></button></header>{versions.map((version) => <article key={version.id}><strong>第 {version.version_number} 版</strong><span>{version.change_note || "内容更新"}</span><small>{version.created_by_name || "系统"} · {asDate(version.created_at)}</small></article>)}</section> : null}
          {pendingRevision?.status === "draft" ? <section className="theory-editorial-revision"><div><strong>待发布编辑草稿</strong><p>第 {pendingRevision.revision} 版修改 {pendingRevision.changed_fields.join("、")}。当前公开页仍使用正式内容。</p></div><ActionButton className="button" type="button" state={pendingAction === "publish-node-revision" ? "pending" : "idle"} pendingLabel="正在发布草稿" disabled={Boolean(pendingAction) || pendingRevision.has_conflict} onClick={() => void publishRevision()}><Check size={14} />单人确认并发布</ActionButton></section> : null}
          {editing ? <section className="theory-merge-box"><strong><GitMerge size={15} />合并重复理论或概念</strong><p>合并前会计算文献、关系、学者、时间轴和阅读路径的影响。</p><div><ResearchEntityPicker label="选择保留的理论或概念" endpoint="/catalog/admin/theory-system/nodes/" entityType="knowledge_node" step="maintenance_theory_nodes" field="merge_target" values={onePickerValue(mergeTarget, nodeName(mergeTarget))} onChange={(next) => { const selected = next.at(-1); if (selected?.id === editing.id || selected?.status === "archived") return; setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setMergeTarget(selected?.id ?? ""); }} /><ActionButton type="button" state={pendingAction === "merge-theory-node" ? "pending" : "idle"} pendingLabel="正在计算影响" disabled={!mergeTarget || (Boolean(pendingAction) && pendingAction !== "merge-theory-node")} onClick={() => void mergeNode()}>预览并合并</ActionButton></div></section> : null}
          {editing ? <EntityLifecycleActions kind="knowledge-node" id={editing.id} name={editing.canonical_name_zh} status={draft.status} previewHref={`/theories/nodes/${editing.slug}`} onChanged={(snapshot) => { setDraft((current) => ({ ...current, status: snapshot.status })); setEditing((current) => current ? { ...current, status: snapshot.status } : current); nodes.refresh(); allNodes.refresh(); }} onDeleted={() => {
            setEditing(null);setDraft({ ...emptyNodeDraft });nodes.refresh();allNodes.refresh();
            const returnTo=theoryLocation.search.get("return_to");
            router.replace(`/admin/theories${returnTo ? `?return_to=${encodeURIComponent(returnTo)}` : ""}`);
          }} /> : null}
          </div>
          <footer className="theory-reference-save" data-editor-section="publication"><ActionButton form="theory-node-form" className="button secondary" state={pendingAction==="save-theory-node"?"pending":"idle"} pendingLabel="正在保存" disabled={openingNode || Boolean(pendingAction)} type="submit">保存草稿</ActionButton></footer>
          {message ? <div role={messageState==="error"?"alert":"status"} className={messageState==="error"?"":"sr-only"}><AsyncStatus state={messageState} message={message}/></div> : null}
          <EditorialConflictHelp visible={editConflict} href={`/admin/theories?node=${editing?.id}`} />
          </fieldset>
        </form>
        <div className="knowledge-object-editor-rail">
          {editing ? <KnowledgeImagePanel objectType="knowledge_node" objectId={editing.id} refreshKey={`${editing.updated_at}:${imageRevision}`} onChanged={() => setImageRevision((value) => value + 1)} /> : null}
          <KnowledgeObjectContextPanel
            hasUnsavedChanges={nodeDirty}
            objectType={knowledgeStudioNodeType(editing?.node_type || draft.node_type)}
            objectId={editing?.id}
            refreshKey={`${editing?.updated_at}:${imageRevision}`}
            onChanged={() => { nodes.refresh(); allNodes.refresh(); requestedNode.refresh(); setImageRevision((value) => value + 1); }}
          />
        </div>
        </KnowledgeVisualEditor>
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
  editorial_revision?: EditorialRevisionSummary;
  public_status?: string;
};

const emptyRelationDraft = { source_node: "", target_node: "", relation_type: "criticizes", direction: "directed", description: "", evidence_source: "", confidence: 1, status: "pending" };

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
  const search = useSearchParams();
  return <TheoryRelationsEditor key={search.get("relation") || "list"} requestedId={search.get("relation") || ""} />;
}

function TheoryRelationsEditor({ requestedId }: { requestedId: string }) {
  const location = useEditorListLocation();
  const taskPage = adminPageNumber(location.search.get("review_page"));
  const relationPage = adminPageNumber(location.search.get("relations_page"));
  const [editConflict, setEditConflict] = useState(false);
  const canPublish = hasAdminCapability(useAdminSession(), "can_publish_authority");
  const taskStatus = location.search.get("review_status") === "all" ? "" : location.search.get("review_status") || "pending";
  const taskFilter = location.search.get("review_q") || "";
  const relationFilter = location.search.get("relation_q") || "";
  const relationStatus = location.search.get("relation_status") || "";
  const [taskQuery, setTaskQuery] = useState(taskFilter);
  const [relationQuery, setRelationQuery] = useState(relationFilter);
  useEffect(() => { const timer=window.setTimeout(()=>setTaskQuery(taskFilter),0);return()=>window.clearTimeout(timer); }, [taskFilter]);
  useEffect(() => { const timer=window.setTimeout(()=>setRelationQuery(relationFilter),0);return()=>window.clearTimeout(timer); }, [relationFilter]);
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
  const [relationDraft, setRelationDraft] = useState(emptyRelationDraft);
  const [relationStep, setRelationStep] = useState("details");
  const relationSteps = [{id:"identity",label:"选择关系"},{id:"details",label:"填写说明"},{id:"publication",label:"预览发布"}];
  const relationStepIndex = relationSteps.findIndex(row => row.id === relationStep);
  const relationSource = useAdminData<KnowledgeNode>(relationDraft.source_node ? `/catalog/admin/theory-system/nodes/${relationDraft.source_node}/` : null);
  const relationPreviewType = relationSource.data?.node_type === "theory_tradition" ? "theory" : relationSource.data?.node_type;
  const relationPreview = useAdminData<KnowledgePreviewPayload>(relationPreviewType ? `/catalog/admin/knowledge-preview/${relationPreviewType}/${relationDraft.source_node}/` : null);
  const relationDirty = useUnsavedForm(relationDraft, editingRelation ? relationToDraft(editingRelation) : emptyRelationDraft);

  const taskParams = useMemo(() => {
    const params = new URLSearchParams();
    params.set("page", String(taskPage));
    if (taskStatus) params.set("status", taskStatus);
    if (taskFilter.trim()) params.set("q", taskFilter.trim());
    return params.toString();
  }, [taskStatus, taskFilter, taskPage]);
  const tasks = useAdminData<Page<ReviewTask>>(`/catalog/admin/theory-system/review-tasks/?${taskParams}`);
  const nodes = useAdminData<Page<KnowledgeNode>>("/catalog/admin/theory-system/nodes/");
  const disciplines = useAdminData<Page<Discipline>>("/catalog/admin/disciplines/");
  const relationParams = new URLSearchParams({ page: String(relationPage) });
  if (relationFilter) relationParams.set("q", relationFilter);
  if (relationStatus) relationParams.set("status", relationStatus);
  const relations = useAdminData<Page<KnowledgeRelation>>(`/catalog/admin/theory-system/relations/?${relationParams}`);
  const requested = useAdminData<KnowledgeRelation>(requestedId ? `/catalog/admin/theory-system/relations/${requestedId}/` : null);
  useEffect(() => {
    if (!requested.data) return;
    const selected=requested.data;
    const timer=window.setTimeout(()=>{setEditingRelation(selected);setRelationDraft(relationToDraft(selected));},0);
    return()=>window.clearTimeout(timer);
  }, [requested.data]);

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
          ? "已创建待完善的理论或概念资料草稿。文献关系已进入下一条审核任务。"
          : action === "alias_existing"
            ? "候选名称已保存为已有理论或概念别名。文献关系已进入下一条审核任务。"
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
    const payload = buildRelationPayload(relationDraft, editingRelation);
    if (!Object.keys(payload).length) { setMessage("当前内容已保存。"); setMessageState("success"); return; }
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = editingRelation ? `save-relation:${editingRelation.id}` : "create-relation";
    if (!startAction(actionKey)) return;
    setMessage(editingRelation ? "正在保存关系修改……" : "正在添加理论关系……");
    setMessageState("pending");
    try {
      const saved = await apiRequest<KnowledgeRelation>(
        editingRelation
          ? `/catalog/admin/theory-system/relations/${editingRelation.id}/`
          : "/catalog/admin/theory-system/relations/",
        { method: editingRelation ? "PATCH" : "POST", headers: editingRelation ? editorialHeaders(editingRelation) : undefined, body: JSON.stringify(payload) },
        token,
      );
      setMessage(saved.editorial_revision ? "修改已保存，尚未公开。核对关系说明后，再确认发布。" : "关系已保存，尚未公开。选择准备公开并保存后，可确认发布。");
      setMessageState("success");
      setEditingRelation(saved);
      setRelationDraft(relationToDraft(saved));
      setEditConflict(false);
      relations.refresh();
      if (saved.id !== requestedId) location.update({ relation: saved.id });
    } catch (reason) {
      setEditConflict(isEditorialConflict(reason));
      setMessage(reason instanceof Error ? reason.message : "关系保存失败");
      setMessageState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  async function publishRelation() {
    const revision = editingRelation?.editorial_revision;
    if (!revision || relationDirty || !canPublish || !window.confirm("确认发布这条关系的已保存修改？相关理论页面和关系图会使用这些内容。")) return;
    if (!startAction("publish-relation")) return;
    try {
      await apiRequest(revision.publish_url, { method: "POST", body: "{}" }, getServerSessionCredential());
      const saved = await apiRequest<KnowledgeRelation>(`/catalog/admin/theory-system/relations/${editingRelation!.id}/`, {}, getServerSessionCredential());
      setEditingRelation(saved);
      setRelationDraft(relationToDraft(saved));
      setMessage(saved.status === "published" ? "关系修改已发布。相关搜索和推荐的后台更新可能尚未完成。" : "关系已下线，读者页面不再展示。后台更新可能尚未完成。");
      setMessageState("success");
      relations.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "发布失败，可重试同一份已保存修改。");
      setMessageState("error");
    } finally { finishAction("publish-relation"); }
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
      await apiRequest(`/catalog/admin/theory-system/relations/${relation.id}/`, { method: "DELETE", headers: editorialHeaders(relation) }, token);
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
    if (pendingAction || (relationDirty && !window.confirm("当前输入尚未保存，放弃这些输入并打开另一条关系吗？"))) return;
    if (relation.id !== requestedId) { location.update({ relation: relation.id }); return; }
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
    setEditConflict(false);
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

  const relationNodeName = (id: string) => entityLabels[id] || nodes.data?.results.find((item) => item.id === id)?.canonical_name_zh || (editingRelation?.source_node === id ? editingRelation.source_name : editingRelation?.target_node === id ? editingRelation.target_name : "") || "已选择理论";
  const relationDisciplineName = (id: string) => disciplines.data?.results.find((item) => item.id === id)?.name || entityLabels[id] || "已选择学科";
  const previewNode = relationPreview.data?.perspective.data as KnowledgeNodeDetail | undefined;
  const previewRelation = {...relationDraft,id:editingRelation?.id || "current-input",source_name:relationNodeName(relationDraft.source_node),target_name:relationNodeName(relationDraft.target_node),source_slug:previewNode?.slug || "",target_slug:nodes.data?.results.find(row=>row.id===relationDraft.target_node)?.slug || "",relation_label:knowledgeRelationOptions.find(([value])=>value===relationDraft.relation_type)?.[1] || relationDraft.relation_type};
  const relationPreviewPayload = relationPreview.data && previewNode ? {...relationPreview.data,perspective:{...relationPreview.data.perspective,data:{...previewNode,direct_relations:[...(previewNode.direct_relations || []).filter(row=>row.id!==editingRelation?.id),...(relationDraft.source_node && relationDraft.target_node ? [previewRelation] : [])]}}} : null;
  return (
    <AdminFrame eyebrow="知识与关联" title="编辑学术关系" description="设置两个理论流派之间的学术关系及说明，在网站上向读者展示它们的思想联系。">
      <details className="theory-suggestion-section" open={Boolean(taskFilter || location.search.get("review_page") || location.search.get("review_status"))}>
      <summary>系统建议{tasks.data ? `（当前筛选共 ${tasks.data.count} 条）` : ""}</summary>
      <div className="theory-review-layout">
        <section className="admin-panel theory-review-list">
          <nav className="theory-review-tabs">
            {[["pending", "待核对"], ["needs_changes", "待修改"], ["confirmed", "已确认"], ["rejected", "不采用"], ["", "全部"]].map(([value, label]) => <button className={taskStatus === value ? "active" : ""} type="button" key={label} onClick={() => { location.update({ review_status: value || "all", review_page: 1 }); setSelected(null); }}>{label}</button>)}
          </nav>
          <form className="theory-review-filter" onSubmit={(event) => { event.preventDefault(); location.update({ review_q: taskQuery.trim(), review_page: 1 }); }}><Search size={15} /><input aria-label="搜索待核对建议" value={taskQuery} onChange={(event) => setTaskQuery(event.target.value)} placeholder="搜索文献、理论或原文…" /><button type="submit">搜索建议</button></form>
          <ErrorNotice message={tasks.error} retry={tasks.refresh} />
          <div className="theory-admin-table-wrap">
            <table className="theory-admin-table theory-review-table">
              <thead><tr><th>文献</th><th>候选理论</th><th>建议关系</th><th>审核提示</th><th>证据页码</th><th>状态</th><th>提交时间</th></tr></thead>
              <tbody>{tasks.data?.results.map((task) => <tr className={selected?.id === task.id ? "selected" : ""} key={task.id}>
                <td data-label="文献"><button type="button" onClick={() => chooseTask(task)}><strong>{task.work_title || task.suggested_node_name || "系统建议"}</strong><small>{task.file_page_count ? `${task.file_page_count} 页 PDF` : "待核对建议"}</small></button></td>
                <td data-label="理论或概念">{task.node_name || task.suggested_node_name || "待选择条目"}</td>
                <td data-label="关联方式">{task.task_type === "new_node" ? "建议新增条目" : workRelationOptions.find(([value]) => value === task.suggested_relation_type)?.[1] || task.suggested_relation_type || "待判断"}</td>
                <td data-label="需注意"><span className="theory-confidence">{task.status === "needs_changes" ? "存在冲突" : "需要确认"}</span></td><td data-label="依据页码">{task.evidence_pages.join("–") || "—"}</td>
                <td data-label="状态"><StatusBadge value={task.status} /></td><td data-label="提交时间">{asDate(task.submitted_at || task.created_at)}</td>
              </tr>)}</tbody>
            </table>
          </div>
          {!tasks.loading && !tasks.data?.results.length ? <div className="theory-admin-empty"><Check size={22} /><strong>当前没有待处理候选</strong><span>新 PDF 完成理论识别后会进入这里。</span></div> : null}
          <EditorListPages data={tasks.data} page={taskPage} pageKey="review_page" label="建议列表分页" ordering="按提交时间从新到旧" busy={tasks.loading} href={location.href} />
        </section>

        <aside className="admin-panel theory-review-editor">
          {selected ? <>
            <header><div><p>当前审核项</p><h2>{selected.work_title || selected.suggested_node_name}</h2><span>{selected.status === "needs_changes" ? "请修改后确认" : "请核对原文与关系"} · {selected.evidence_pages.length ? `第 ${selected.evidence_pages.join("–")} 页` : "暂无页码"}</span></div>{selected.viewer_href ? <Link href={selected.viewer_href} target="_blank">查看 PDF <ExternalLink size={14} /></Link> : null}</header>
            {selected.task_type === "new_node" ? <section className="theory-new-node-notice"><strong>建议新增知识理论或概念</strong><p>系统在多个 PDF 页面发现“{selected.suggested_node_name}”。请先判断它是新理论或概念，还是已有理论或概念的别名。创建后仍需在理论或概念管理中完善和发布。</p></section> : null}
            <ResearchEntityPicker label={selected.task_type === "new_node" ? "归并到已有理论或概念" : "候选理论"} endpoint="/catalog/admin/theory-system/nodes/" entityType="knowledge_node" step="maintenance_theory_relations" field="review_candidate" values={onePickerValue(candidateNode, relationNodeName(candidateNode))} onChange={(next) => { const picked = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setCandidateNode(picked?.id ?? ""); }} />
            {selected.task_type === "new_node" ? <div className="inline-fields"><label><span>新资料类型</span><select value={newNodeType} onChange={(event) => setNewNodeType(event.target.value)}>{Object.entries(nodeTypeLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><ResearchEntityPicker label="主要学科" endpoint="/catalog/admin/disciplines/" entityType="discipline" step="maintenance_theory_relations" field="new_node_discipline" values={onePickerValue(newNodeDiscipline, relationDisciplineName(newNodeDiscipline))} onChange={(next) => { const picked = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setNewNodeDiscipline(picked?.id ?? ""); }} /></div> : null}
            <label><span>建议关系类型</span><select value={relationRole} onChange={(event) => setRelationRole(event.target.value)}>{workRelationOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
            <section className="theory-evidence-card"><header><strong>原文片段</strong><span>{selected.file ? "PDF/OCR 证据" : "系统建议"}</span></header><blockquote>{selected.evidence_text || "这条建议尚未附带原文，不应直接确认。"}</blockquote><footer>{selected.evidence_pages.length ? `页码 ${selected.evidence_pages.join("–")}` : "页码待补充"}</footer></section>
            <label><span>审核备注</span><textarea rows={4} value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} placeholder="记录修改理由或参考资料" /></label>
            {selected.task_type === "new_node" ? <div className="theory-review-primary-actions"><ActionButton className="button" type="button" state={pendingAction?.endsWith(":create_node") ? "pending" : "idle"} pendingLabel="正在创建" disabled={Boolean(pendingAction) && !pendingAction?.endsWith(":create_node")} onClick={() => void review("create_node")}><Plus size={15} />创建草稿理论或概念</ActionButton><ActionButton disabled={!candidateNode || (Boolean(pendingAction) && !pendingAction?.endsWith(":alias_existing"))} state={pendingAction?.endsWith(":alias_existing") ? "pending" : "idle"} pendingLabel="正在归并" type="button" onClick={() => void review("alias_existing")}>作为已有理论或概念别名</ActionButton><ActionButton type="button" state={pendingAction?.endsWith(":reject") ? "pending" : "idle"} pendingLabel="正在拒绝" disabled={Boolean(pendingAction) && !pendingAction?.endsWith(":reject")} onClick={() => void review("reject")}>拒绝</ActionButton></div> : <div className="theory-review-primary-actions"><ActionButton className="button" disabled={!candidateNode || Boolean(pendingAction)} state={pendingAction?.endsWith(":confirm") || pendingAction?.endsWith(":modify_confirm") ? "pending" : "idle"} pendingLabel="正在确认" type="button" onClick={() => void review(selected.candidate_node === candidateNode && selected.suggested_relation_type === relationRole ? "confirm" : "modify_confirm")}><Check size={15} />确认</ActionButton><ActionButton type="button" state={pendingAction?.endsWith(":needs_changes") ? "pending" : "idle"} pendingLabel="正在退回" disabled={Boolean(pendingAction) && !pendingAction?.endsWith(":needs_changes")} onClick={() => void review("needs_changes")}>退回修改</ActionButton><ActionButton type="button" state={pendingAction?.endsWith(":reject") ? "pending" : "idle"} pendingLabel="正在拒绝" disabled={Boolean(pendingAction) && !pendingAction?.endsWith(":reject")} onClick={() => void review("reject")}>拒绝</ActionButton></div>}
            <div className="theory-review-secondary-actions"><ActionButton type="button" state={pendingAction?.endsWith(":defer") ? "pending" : "idle"} pendingLabel="处理中" disabled={Boolean(pendingAction) && !pendingAction?.endsWith(":defer")} onClick={() => void review("defer")}>延后处理</ActionButton><ActionButton type="button" state={pendingAction?.endsWith(":insufficient") ? "pending" : "idle"} pendingLabel="处理中" disabled={Boolean(pendingAction) && !pendingAction?.endsWith(":insufficient")} onClick={() => void review("insufficient")}>证据不足</ActionButton><ActionButton className="danger-link" type="button" state={pendingAction === `delete-review-task:${selected.id}` ? "pending" : "idle"} pendingLabel="删除中" disabled={Boolean(pendingAction) && pendingAction !== `delete-review-task:${selected.id}`} onClick={() => void removeReviewTask()}><Trash2 size={13} />删除候选</ActionButton></div>
          </> : <div className="theory-admin-empty"><BookOpen size={24} /><strong>选择一个审核项</strong><span>右侧会显示候选理论、原文内容和 PDF 页码。</span></div>}
          {!editingRelation && message ? <AsyncStatus state={messageState} message={message} /> : null}
        </aside>
      </div>

      </details>
      <nav className="knowledge-reference-steps" aria-label="学术关系编辑步骤">{relationSteps.map((step,index)=><button key={step.id} type="button" aria-current={relationStep===step.id ? "step" : undefined} onClick={()=>setRelationStep(step.id)}><span>{index<relationStepIndex ? "✓" : index+1}</span><strong>{step.label}</strong></button>)}</nav>
      <section className="reference-theory-relation-editor">
        <FixedPageEditor sections={relationSteps} navigationSections={[]} activeSection={relationStep} onSectionChange={setRelationStep} dirty={relationDirty}
          preview={relationPreviewPayload ? <PreviewSurface payload={relationPreviewPayload} pageId="relations"/> : <p role={relationPreview.error ? "alert" : "status"}>{relationPreview.error || (relationDraft.source_node ? "正在读取理论页面…" : "选择起点流派后显示页面预览。")}</p>}
          publishedHref={relationPreview.data?.preview_routes.published ? `${relationPreview.data.preview_routes.published}/relations` : undefined}
          toolbar={<footer className="knowledge-reference-step-actions"><button type="button" className="button secondary" disabled={relationStepIndex===0} onClick={()=>setRelationStep(relationSteps[relationStepIndex-1].id)}>上一步</button><button className="button secondary" type="submit" form="theory-relation-form" disabled={Boolean(pendingAction) || !relationDraft.source_node || !relationDraft.target_node}>保存草稿</button>{relationStepIndex<2 ? <button type="button" className="button" onClick={()=>setRelationStep(relationSteps[relationStepIndex+1].id)}>下一步：{relationSteps[relationStepIndex+1].label}</button> : <button type="button" className="button" disabled={!canPublish || relationDirty || !editingRelation?.editorial_revision || Boolean(pendingAction)} onClick={()=>void publishRelation()}>确认发布</button>}</footer>}
          fields={<form id="theory-relation-form" aria-label="编辑理论关系" onSubmit={saveRelation}>

            <ErrorNotice message={requested.error} retry={requested.refresh} />
            {requestedId && !requested.data ? <p>正在读取所选关系。</p> : null}
            <fieldset className="dedicated-editor-fields" disabled={Boolean(pendingAction) || Boolean(requestedId && !requested.data)}>
            <div hidden={relationStep=== "publication"}>
            <div className="inline-fields"><ResearchEntityPicker label="源理论" endpoint="/catalog/admin/theory-system/nodes/" entityType="knowledge_node" step="maintenance_theory_relations" field="source_node" values={onePickerValue(relationDraft.source_node, relationNodeName(relationDraft.source_node))} onChange={(next) => { const picked = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setRelationDraft({ ...relationDraft, source_node: picked?.id ?? "", target_node: picked?.id === relationDraft.target_node ? "" : relationDraft.target_node }); }} /><ResearchEntityPicker label="目标理论" endpoint="/catalog/admin/theory-system/nodes/" entityType="knowledge_node" step="maintenance_theory_relations" field="target_node" values={onePickerValue(relationDraft.target_node, relationNodeName(relationDraft.target_node))} onChange={(next) => { const picked = next.at(-1); if (picked?.id === relationDraft.source_node) return; setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setRelationDraft({ ...relationDraft, target_node: picked?.id ?? "" }); }} /></div>
            <div className="inline-fields"><label><span>关系类型</span><select value={relationDraft.relation_type} onChange={(event) => setRelationDraft({ ...relationDraft, relation_type: event.target.value })}>{knowledgeRelationOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label><span>方向</span><select value={relationDraft.direction} onChange={(event) => setRelationDraft({ ...relationDraft, direction: event.target.value })}><option value="directed">有方向</option><option value="undirected">无方向</option></select></label></div>
            <label><span>关系说明</span><textarea rows={3} value={relationDraft.description} onChange={(event) => setRelationDraft({ ...relationDraft, description: event.target.value })} /></label>
            <label><span>证据来源</span><textarea rows={3} value={relationDraft.evidence_source} onChange={(event) => setRelationDraft({ ...relationDraft, evidence_source: event.target.value })} placeholder="馆藏页码、参考文献或人工校订说明" /></label>
            </div>
            <div hidden={relationStep!=="publication"}><p>{previewRelation.source_name} → {previewRelation.target_name}</p><p>{relationDraft.description}</p><p>{relationDraft.evidence_source}</p>
            <div className="inline-fields"><label><span>保存后的安排</span><select value={relationDraft.status} onChange={(event) => setRelationDraft({ ...relationDraft, status: event.target.value })}><option value="draft">留作草稿</option><option value="pending">留待核对</option><option value="published" disabled={!canPublish && editingRelation?.status !== "published"}>准备公开</option><option value="rejected">不采用</option><option value="archived" disabled={!canPublish}>准备下线</option></select></label></div>
            </div>
            {editingRelation ? <button type="button" onClick={() => { if (relationDirty && !window.confirm("放弃当前尚未保存的输入吗？")) return; location.update({ relation: null }); setEditingRelation(null); setRelationDraft(emptyRelationDraft); setRelationStep("identity"); }}>新建另一条关系</button> : null}
            </fieldset>
            <SavedDraftActions revision={editingRelation?.editorial_revision} dirty={relationDirty} busy={Boolean(pendingAction)} impact="请核对上方的理论、关系和来源。发布后，相关理论页面和关系图会使用已保存的内容。" publish={() => void publishRelation()} />
            <EditorialConflictHelp visible={editConflict} href={location.href({ relation: editingRelation?.id ?? null })} />
            {editingRelation && message ? <AsyncStatus state={messageState} message={message} /> : null}
          </form>} />
          <details className="theory-existing-relations"><summary>已保存的关系</summary>
            <form className="theory-relation-list-filters" onSubmit={(event) => { event.preventDefault(); location.update({ relation_q: relationQuery.trim(), relations_page: 1 }); }}>
              <label><span>查找关系</span><input value={relationQuery} onChange={(event) => setRelationQuery(event.target.value)} placeholder="理论名称、说明或来源…" /></label>
              <label><span>当前公开状态</span><select value={relationStatus} onChange={(event) => location.update({ relation_status: event.target.value, relations_page: 1 })}><option value="">全部</option><option value="published">已公开</option><option value="draft">草稿</option><option value="pending">待核对</option><option value="rejected">不采用</option><option value="archived">已下线</option></select></label>
              <button type="submit">搜索关系</button>
            </form>
            <ErrorNotice message={relations.error} retry={relations.refresh} />
            <h3>现有关系</h3>{relations.data?.results.map((relation) => <article className={editingRelation?.id === relation.id ? "selected" : ""} key={relation.id}><div><strong>{relation.source_name}</strong><span>{relation.relation_label}</span><strong>{relation.target_name}</strong></div><p>{relation.description || relation.evidence_source || "尚未填写说明"}</p>{relation.editorial_revision ? <p>有已保存的修改，尚未公开</p> : null}<footer><StatusBadge value={relation.public_status ?? relation.status} /><span><button type="button" onClick={() => editRelation(relation)}><Pencil size={13} />编辑</button><ActionButton type="button" state={pendingAction === `delete-relation:${relation.id}` ? "pending" : "idle"} pendingLabel="删除中" disabled={Boolean(pendingAction) && pendingAction !== `delete-relation:${relation.id}`} onClick={() => void removeRelation(relation)}><Trash2 size={13} />删除</ActionButton></span></footer></article>)}{!relations.data?.results.length ? <p>尚未建立规范理论关系。</p> : null}
        <EditorListPages data={relations.data} page={relationPage} pageKey="relations_page" label="关系列表分页" ordering="按修改时间从新到旧" busy={relations.loading} href={location.href} />
          </details>
      </section>
    </AdminFrame>
  );
}

type TimelineEvent = TimelineRecord & { editorial_revision?: EditorialRevisionSummary; public_status?: string };

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

function TimelineEvidenceFields({ draft, saved, workName, onChange, onLabels }: {
  draft: TimelineDraft; saved: TimelineEvent | null; workName: string;
  onChange: (patch: Partial<TimelineDraft>) => void;
  onLabels: (values: EntityValue[]) => void;
}) {
  const [page, setPage] = useState(1);
  const [notice, setNotice] = useState("");
  const path = draft.source_work ? `/catalog/admin/library/works/?view=editions&work_id=${encodeURIComponent(draft.source_work)}` : null;
  const editions = useAdminData<CollectionPage<WorkLibraryRow>>(path ? `${path}&page=${page}` : null);
  const listed = editions.data?.results.find((row) => row.id === draft.source_edition);
  const selected = useAdminData<CollectionPage<WorkLibraryRow>>(path && draft.source_edition && !listed ? `${path}&edition_id=${encodeURIComponent(draft.source_edition)}` : null);
  const edition = listed ?? selected.data?.results.find((row) => row.id === draft.source_edition);
  const files = edition?.assets?.filter((row) => row.kind === "normalized") ?? [];
  const file = files.find((row) => row.id === draft.evidence_asset);
  const savedFile = saved?.evidence_file?.id === draft.evidence_asset ? saved.evidence_file : null;
  const savedPageMatches = savedFile && String(saved?.evidence_page ?? "") === draft.evidence_page;
  const changeSource = (patch: Partial<TimelineDraft>) => {
    onChange({ ...patch, evidence_page: "", evidence_printed_label: "" });
    setNotice("出处已更换，PDF 页序和印刷页码已清空。文字来源与摘录保留，请重新核对。");
  };
  return <section className="timeline-evidence-fields" aria-label="馆藏出处">
    <h3>馆藏出处（可选）</h3>
    <p>有馆内 PDF 时，选择出处文献、出版版本和阅读文件。出处可以不是上方关联的作品；没有 PDF 也可以只保存文字来源。不选文件时，请把出处书目写在上方“来源”中。</p>
    <EntityPicker label="出处馆藏" endpoint="/catalog/admin/library/works/" queryParam="q" nameField="title" placeholder="搜索馆内出处文献…" values={onePickerValue(draft.source_work, workName)} onChange={(values) => {
      onLabels(values);
      const picked = values.at(-1)?.id ?? "";
      if (picked !== draft.source_work) { setPage(1); changeSource({ source_work: picked, source_edition: "", evidence_asset: "" }); }
    }} />
    {draft.source_work ? <>
      <ErrorNotice message={editions.error || selected.error} retry={() => { editions.refresh(); selected.refresh(); }} />
      <label><span>出处出版版本</span><select name="evidence_edition" value={draft.source_edition} disabled={editions.loading} onChange={(event) => changeSource({ source_edition: event.target.value, evidence_asset: "" })}>
        <option value="">请选择出版版本</option>
        {draft.source_edition && !listed ? <option value={draft.source_edition}>{edition?.label || saved?.evidence_file?.edition_label || "已选版本，正在核对"}</option> : null}
        {editions.data?.results.map((row) => <option key={row.id} value={row.id}>{row.label || "出版信息待补"}{row.is_primary ? "（主版本）" : ""}</option>)}
      </select></label>
      <nav className="timeline-source-pages" aria-label="出处版本分页">
        <span>{editions.data ? `共 ${editions.data.count} 个版本，第 ${page} 页` : "正在读取版本…"}</span>
        <button type="button" disabled={editions.loading || !editions.data?.previous} onClick={() => setPage((value) => value - 1)}>上一页版本</button>
        <button type="button" disabled={editions.loading || !editions.data?.next} onClick={() => setPage((value) => value + 1)}>下一页版本</button>
      </nav>
      {draft.source_edition ? <>
        <label><span>出处阅读文件</span><select name="evidence_asset" value={draft.evidence_asset} disabled={!edition || Boolean(editions.error || selected.error)} onChange={(event) => changeSource({ evidence_asset: event.target.value })}>
          <option value="">不关联阅读文件</option>
          {draft.evidence_asset && !file ? <option value={draft.evidence_asset}>{savedFile?.filename || "原文件引用，待核对"}</option> : null}
          {files.map((row) => <option key={row.id} value={row.id} disabled={row.status !== "ready" || row.validation_status !== "valid" || row.page_count < 1}>
            {row.original_filename || "阅读文件"} · 文件版本 {row.version} · {row.page_count} 页{row.validation_status === "invalid" ? " · 验证失败" : row.validation_status !== "valid" ? " · 等待验证" : row.status !== "ready" ? " · 尚未就绪" : ""}
          </option>)}
        </select></label>
        {edition && !files.length ? <p>这个出版版本没有阅读文件，可只填写文字来源，或到该版本补充 PDF。</p> : null}
        <Link href={`/admin/library/works/${draft.source_work}?edition=${draft.source_edition}#file`} target="_blank" rel="noopener noreferrer">在新标签页管理这个版本的文件</Link>
      </> : null}
    </> : null}
    <div className="inline-fields">
      <label><span>PDF 页序</span><input name="evidence_page" type="number" min={1} max={file?.page_count ?? savedFile?.page_count} required={Boolean(draft.evidence_asset)} value={draft.evidence_page} onChange={(event) => { setNotice(""); onChange({ evidence_page: event.target.value }); }} aria-describedby="timeline-page-help" /></label>
      <label><span>印刷页码</span><input name="evidence_printed_label" autoComplete="off" value={draft.evidence_printed_label} onChange={(event) => { setNotice(""); onChange({ evidence_printed_label: event.target.value }); }} placeholder="例如 卷二，第 35 页…" /></label>
    </div>
    <p id="timeline-page-help">PDF 页序从文件第一页算起，用于阅读定位；印刷页码是书页上标注的页码，可以不同。{file || savedFile ? `所选文件共 ${file?.page_count ?? savedFile?.page_count} 页。` : "未选择文件时不会生成阅读链接。"}</p>
    {file || savedFile ? <p className="timeline-source-file">{file?.original_filename || savedFile?.filename} · 文件版本 {file?.version ?? savedFile?.version}</p> : null}
    {notice ? <p role="status">{notice}</p> : null}
    {savedPageMatches ? <p>{savedFile.detail}{savedFile.reader_href ? <> <Link href={savedFile.reader_href} target="_blank" rel="noopener noreferrer">打开已保存的出处页</Link></> : null}</p> : draft.evidence_asset ? <p>保存事件后，可核对这份文件的实际阅读链接。选择文件本身不会把它公开。</p> : null}
  </section>;
}

export function NormalizedTimelineAdmin() {
  const search = useSearchParams();
  return <TimelineEditor key={`${search.get("node") || "all"}:${search.get("event") || "list"}`} nodeId={search.get("node") || ""} requestedId={search.get("event") || ""} />;
}

function TimelineEditor({ requestedId, nodeId = "" }: { requestedId: string; nodeId?: string }) {
  const location = useEditorListLocation();
  const page = adminPageNumber(location.search.get("page"));
  const [editConflict, setEditConflict] = useState(false);
  const canPublish = hasAdminCapability(useAdminSession(), "can_publish_authority");
  const [editing, setEditing] = useState<TimelineEvent | null>(null);
  const initialDraft = useMemo(() => ({ ...emptyTimelineDraft, nodes: nodeId ? [nodeId] : [] }), [nodeId]);
  const [draft, setDraft] = useState<TimelineDraft>(initialDraft);
  const [timelineStep, setTimelineStep] = useState("details");
  const timelineSteps = [{id:"identity",label:"选择事件"},{id:"details",label:"编辑内容"},{id:"publication",label:"预览发布"}];
  const timelineStepIndex = timelineSteps.findIndex(row=>row.id===timelineStep);
  const previewNodeId = nodeId || draft.nodes[0] || "";
  const timelineSource = useAdminData<KnowledgeNode>(previewNodeId ? `/catalog/admin/theory-system/nodes/${previewNodeId}/` : null);
  const timelinePreviewType = timelineSource.data?.node_type === "theory_tradition" ? "theory" : timelineSource.data?.node_type;
  const timelinePreview = useAdminData<KnowledgePreviewPayload>(timelinePreviewType ? `/catalog/admin/knowledge-preview/${timelinePreviewType}/${previewNodeId}/` : null);
  const timelineDirty = useUnsavedForm(draft, editing ? timelineToDraft(editing) : initialDraft);
  const disciplineFilter = location.search.get("discipline") || "";
  const typeFilter = location.search.get("event_type") || "";
  const statusFilter = location.search.get("review_status") || "";
  const appliedQuery = location.search.get("q") || "";
  const [query, setQuery] = useState(appliedQuery);
  useEffect(() => { const timer=window.setTimeout(()=>setQuery(appliedQuery),0);return()=>window.clearTimeout(timer); }, [appliedQuery]);
  const setDisciplineFilter = (value: string) => location.update({ discipline: value, page: 1 });
  const setTypeFilter = (value: string) => location.update({ event_type: value, page: 1 });
  const setStatusFilter = (value: string) => location.update({ review_status: value, page: 1 });
  const [message, setMessage] = useState("");
  const [messageState, setMessageState] = useState<ActionState>("idle");
  const { pendingAction, startAction, finishAction } = useActionGuard();
  const [entityLabels, setEntityLabels] = useState<Record<string, string>>({});

  const params = useMemo(() => {
    const search = new URLSearchParams();
    search.set("page", String(page));
    if (nodeId) search.set("node", nodeId);
    if (disciplineFilter) search.set("discipline", disciplineFilter);
    if (typeFilter) search.set("event_type", typeFilter);
    if (statusFilter) search.set("review_status", statusFilter);
    if (appliedQuery.trim()) search.set("q", appliedQuery.trim());
    return search.toString();
  }, [disciplineFilter, typeFilter, statusFilter, appliedQuery, page, nodeId]);
  const selectedNode = useAdminData<KnowledgeNode>(nodeId ? `/catalog/admin/theory-system/nodes/${nodeId}/` : null);
  const events = useAdminData<Page<TimelineEvent>>(nodeId && !selectedNode.data ? null : `/catalog/admin/theory-timeline/?${params}`);
  const nodes = useAdminData<Page<KnowledgeNode>>("/catalog/admin/theory-system/nodes/");
  const disciplines = useAdminData<Page<Discipline>>("/catalog/admin/disciplines/");
  const works = useAdminData<Page<WorkCompact>>("/catalog/works/");
  const scholars = useAdminData<Page<ScholarCompact>>("/catalog/admin/scholars/");
  const requested = useAdminData<TimelineEvent>(requestedId ? `/catalog/admin/theory-timeline/${requestedId}/` : null);
  const wrongNode = Boolean(nodeId && requested.data && !requested.data.relations.some((row) => row.node === nodeId));
  useEffect(() => {
    if (!requested.data || wrongNode) return;
    const selected=requested.data;
    const timer=window.setTimeout(()=>{setEditing(selected);setDraft(timelineToDraft(selected));},0);
    return()=>window.clearTimeout(timer);
  }, [requested.data, wrongNode]);

  function start(event?: TimelineEvent) {
    if (pendingAction || (timelineDirty && !window.confirm("当前输入尚未保存，放弃这些输入并打开另一个事件吗？"))) return;
    if ((event?.id || "") !== requestedId) { location.update({ event: event?.id ?? null }); return; }
    setEditing(event ?? null);
    setDraft(event ? timelineToDraft(event) : { ...initialDraft });
    setMessage("");
    setMessageState("idle");
    setEntityLabels({});
    setEditConflict(false);
  }

  async function saveEvent(event: FormEvent) {
    event.preventDefault();
    if (wrongNode || (nodeId && !selectedNode.data)) return;
    if (editing && !Object.keys(buildTimelinePayload(draft, editing)).length) { setMessage("当前内容已保存。"); setMessageState("success"); return; }
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = editing ? `save-timeline-event:${editing.id}` : "create-timeline-event";
    if (!startAction(actionKey)) return;
    setMessage(editing ? "正在保存时间轴事件……" : "正在创建时间轴事件……");
    setMessageState("pending");
    const payload = buildTimelinePayload(draft, editing);
    try {
      const saved = await apiRequest<TimelineEvent>(`/catalog/admin/theory-timeline/${editing ? `${editing.id}/` : ""}`, { method: editing ? "PATCH" : "POST", headers: editing ? editorialHeaders(editing) : undefined, body: JSON.stringify(payload) }, token);
      setEditing(saved);
      setDraft(timelineToDraft(saved));
      setMessage(saved.editorial_revision ? "修改已保存，尚未公开。核对事件预览后，再确认发布。" : "事件已保存，尚未公开。选择准备公开并保存后，可确认发布。");
      setEditConflict(false);
      setMessageState("success");
      events.refresh();
      if (saved.id !== requestedId) location.update({ event: saved.id });
    } catch (reason) {
      setEditConflict(isEditorialConflict(reason));
      setMessage(reason instanceof Error ? reason.message : "事件保存失败");
      setMessageState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  async function publishEvent() {
    const revision = editing?.editorial_revision;
    if (!revision || timelineDirty || !canPublish || !window.confirm("确认发布此事件的已保存修改？公开时间线和关联页面会使用这些内容。")) return;
    if (!startAction("publish-timeline")) return;
    try {
      await apiRequest(revision.publish_url, { method: "POST", body: "{}" }, getServerSessionCredential());
      const saved = await apiRequest<TimelineEvent>(`/catalog/admin/theory-timeline/${editing!.id}/`, {}, getServerSessionCredential());
      setEditing(saved);
      setDraft(timelineToDraft(saved));
      setMessage(saved.review_status === "approved" ? "事件修改已发布。相关搜索的后台更新可能尚未完成。" : "事件已下线，公开时间线不再展示。后台更新可能尚未完成。");
      setMessageState("success");
      events.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "发布失败，可重试同一份已保存修改。");
      setMessageState("error");
    } finally { finishAction("publish-timeline"); }
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
      await apiRequest(`/catalog/admin/theory-timeline/${editing.id}/`, { method: "DELETE", headers: editorialHeaders(editing) }, token);
      setEditing(null);
      setDraft({ ...initialDraft });
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

  const timelineNodeName = (id: string) => entityLabels[id] || (selectedNode.data?.id === id ? selectedNode.data.canonical_name_zh : "") || nodes.data?.results.find((item) => item.id === id)?.canonical_name_zh || editing?.relations.find((row) => row.node === id)?.node_name || "已选择理论";
  const timelineDisciplineName = (id: string) => entityLabels[id] || disciplines.data?.results.find((item) => item.id === id)?.name || editing?.relations.find((row) => row.discipline === id)?.discipline_name || "已选择学科";
  const timelineScholarName = (id: string) => scholars.data?.results.find((item) => item.id === id)?.preferred_name || entityLabels[id] || "已选择学者";
  const timelineWorkName = (id: string) => works.data?.results.find((item) => item.id === id)?.title || entityLabels[id] || "已选择馆藏";

  const matchesSavedSource = Boolean(editing?.evidence_file && editing.evidence_file.id===draft.evidence_asset && String(editing.evidence_page ?? "")===draft.evidence_page && editing.evidence_file.work_id===draft.source_work && editing.evidence_file.edition_id===draft.source_edition);
  const liveTimelineEvent: NormalizedTimelineEvent = {id:editing?.id || "current-input",title:draft.title,description:draft.description,event_type:draft.event_type,start_year:draft.start_year ? Number(draft.start_year) : null,end_year:draft.end_year ? Number(draft.end_year) : null,date_label:draft.date_label,source:draft.source,evidence_page:draft.evidence_page ? Number(draft.evidence_page) : null,evidence_printed_label:draft.evidence_printed_label,evidence_text:draft.evidence_text,relations:draft.nodes.map(id=>({relation_type:"subject",type:"node",id,name:timelineNodeName(id)})),reader_href:matchesSavedSource ? editing?.evidence_file?.reader_href || null : null};
  const liveTimeline = [...(timelinePreview.data?.secondary_preview?.timeline || []).filter(row=>row.id!==editing?.id),...(draft.title && draft.nodes.includes(previewNodeId) ? [liveTimelineEvent] : [])].sort((a,b)=>(a.start_year ?? Infinity)-(b.start_year ?? Infinity));
  const timelinePreviewPayload = timelinePreview.data ? {...timelinePreview.data,secondary_preview:{...timelinePreview.data.secondary_preview,timeline:liveTimeline}} : null;

  return (
    <AdminFrame eyebrow="理论管理 / 时间线" title={nodeId ? `${selectedNode.data?.canonical_name_zh || "所选理论"}的时间线` : "全部理论事件"} description="填写事件标题、发生时间和说明，再注明来源。保存后，确认发布才会更新所关联理论的页面和公开时间线。" actions={<Link className="admin-outline-button" href={`/theories/timeline${selectedNode.data ? `?node=${encodeURIComponent(selectedNode.data.slug)}` : ""}`} target="_blank">查看当前公开时间线 <ExternalLink size={14} /></Link>}>
      <nav aria-label="时间线返回位置"><Link href={safeAdminHref(location.search.get("returnTo"), nodeId ? `/admin/theories/${nodeId}` : "/admin/theories")}>返回{selectedNode.data?.canonical_name_zh || "理论管理"}</Link>{nodeId ? <> · <Link href="/admin/theories/timeline">查看全部理论事件</Link></> : null}</nav>
      <ErrorNotice message={selectedNode.error} retry={selectedNode.refresh} />
      {nodeId && !selectedNode.data ? <p>尚未读取到所选理论。不会改为另一个理论，也不能在此新建事件。</p> : null}
      {wrongNode ? <p role="alert">这个事件不属于当前理论。请返回事件所属理论，或从全部理论事件中查看。</p> : null}
      <p>同一事件可以关联多个理论，修改会影响所有关联理论。关联学者或馆藏用于说明事件涉及谁、哪部作品，不会自动替代学者生平或主题发展内容。</p>
      <nav className="knowledge-reference-steps" aria-label="时间线编辑步骤">{timelineSteps.map((step,index)=><button key={step.id} type="button" aria-current={timelineStep===step.id ? "step" : undefined} onClick={()=>setTimelineStep(step.id)}><span>{index<timelineStepIndex ? "✓" : index+1}</span><strong>{step.label}</strong></button>)}</nav>
      <div className="timeline-reference-editor">
        <section className="admin-panel normalized-timeline-list" hidden={timelineStep!=="identity"}>
          <form className="theory-admin-filters timeline" onSubmit={(event) => { event.preventDefault(); location.update({ q: query.trim(), page: 1 }); }}>
            <ResearchEntityPicker label="学科筛选" endpoint="/catalog/admin/disciplines/" entityType="discipline" step="maintenance_theory_timeline" field="filter_discipline" values={onePickerValue(disciplineFilter, timelineDisciplineName(disciplineFilter))} onChange={(next) => { const picked = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDisciplineFilter(picked?.id ?? ""); }} />
            <label><span>事件类型</span><select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}><option value="">全部</option>{timelineTypes.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
            <label><span>当前公开状态</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">全部</option><option value="suggested">待核对</option><option value="approved">已公开</option><option value="rejected">不采用或已下线</option></select></label>
            <label className="theory-admin-search"><span>标题或来源</span><div><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索事件……" /></div></label>
            <button className="button" type="submit">搜索事件</button>
          </form>
          <header className="timeline-list-actions"><button className="button" type="button" onClick={() => start()}><Plus size={15} />新建事件</button><button type="button" onClick={events.refresh}><RefreshCw size={15} />刷新</button></header>
          <ErrorNotice message={events.error} retry={events.refresh} />
          <div className="theory-admin-table-wrap"><table className="theory-admin-table"><thead><tr><th>事件标题</th><th>显示时期</th><th>事件类型</th><th>关联条目</th><th>证据页码</th><th>来源</th><th>状态</th><th>排序</th></tr></thead><tbody>{events.data?.results.map((item) => <tr className={editing?.id === item.id ? "selected" : ""} key={item.id}>
            <td data-label="事件标题"><button type="button" aria-label={`编辑时间轴事件 ${item.title}`} onClick={() => start(item)}><strong>{item.title}</strong><small>{item.description}</small></button></td>
            <td data-label="显示时期"><strong>{item.date_label || item.start_year || "待定"}</strong>{item.end_year ? <small>至 {item.end_year}</small> : null}</td>
            <td data-label="事件类型">{timelineTypes.find(([value]) => value === item.event_type)?.[1] || item.event_type}</td><td data-label="关联条目">{item.relations.filter((relation) => relation.node).map((relation) => relation.node_name).join("、") || "—"}</td>
            <td data-label="证据页码">{item.evidence_page || "—"}</td><td data-label="来源">{item.source || "—"}</td><td data-label="状态"><StatusBadge value={item.public_status ?? item.review_status} />{item.editorial_revision ? <small>有修改待发布</small> : null}</td><td data-label="排序">{item.display_order}</td>
          </tr>)}</tbody></table></div>
          {!events.loading && !events.data?.results.length ? <div className="theory-admin-empty"><Clock3 size={22} /><strong>没有符合筛选条件的事件</strong></div> : null}
          <EditorListPages data={events.data} page={page} pageKey="page" label="事件列表分页" ordering="按发生年份从早到晚，同年按排序与标题排列" busy={events.loading} href={location.href} />
        </section>

        <FixedPageEditor sections={timelineSteps} navigationSections={[]} activeSection={timelineStep} onSectionChange={setTimelineStep} dirty={timelineDirty}
          preview={timelinePreviewPayload ? <PreviewSurface payload={timelinePreviewPayload} pageId="timeline"/> : <p role={timelinePreview.error ? "alert" : "status"}>{timelinePreview.error || "选择关联理论后显示完整时间线预览。"}</p>}
          publishedHref={timelinePreview.data?.preview_routes.published ? `${timelinePreview.data.preview_routes.published}/timeline` : undefined}
          toolbar={<footer className="knowledge-reference-step-actions"><button type="button" className="button secondary" disabled={timelineStepIndex===0} onClick={()=>setTimelineStep(timelineSteps[timelineStepIndex-1].id)}>上一步</button><button className="button secondary" type="submit" form="timeline-event-form" disabled={Boolean(pendingAction) || wrongNode || Boolean(nodeId && !selectedNode.data)}>保存草稿</button>{timelineStepIndex<2 ? <button type="button" className="button" onClick={()=>setTimelineStep(timelineSteps[timelineStepIndex+1].id)}>下一步：{timelineSteps[timelineStepIndex+1].label}</button> : <button type="button" className="button" disabled={!canPublish || timelineDirty || !editing?.editorial_revision || Boolean(pendingAction)} onClick={()=>void publishEvent()}>确认发布</button>}</footer>}
          fields={<form id="timeline-event-form" className="timeline-event-editor" onSubmit={saveEvent}>
          <ErrorNotice message={requested.error} retry={requested.refresh} />
          {requestedId && !requested.data ? <p>正在读取所选事件。</p> : null}
          <fieldset className="dedicated-editor-fields" disabled={Boolean(pendingAction) || Boolean(requestedId && !requested.data) || wrongNode || Boolean(nodeId && !selectedNode.data)}>
          <header><div><h2>{editing ? "编辑事件" : "新建事件"}</h2><p>标题、时间、说明、关联理论和来源会用于公开时间线。证据原文用于复核；有有效阅读文件和页码时，读者可打开馆藏出处。</p></div>{editing ? <ActionButton type="button" state={pendingAction === `delete-timeline-event:${editing.id}` ? "pending" : "idle"} pendingLabel="删除中" disabled={Boolean(pendingAction) && pendingAction !== `delete-timeline-event:${editing.id}`} onClick={() => void removeEvent()}><Trash2 size={14} />删除</ActionButton> : null}</header>
          <label><span>事件标题</span><input required value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
          <label><span>说明</span><textarea rows={4} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
          <div className="inline-fields"><label><span>开始年</span><input type="number" value={draft.start_year} onChange={(event) => setDraft({ ...draft, start_year: event.target.value })} /></label><label><span>结束年</span><input type="number" value={draft.end_year} onChange={(event) => setDraft({ ...draft, end_year: event.target.value })} /></label></div>
          <div className="inline-fields"><label><span>显示时期</span><input value={draft.date_label} onChange={(event) => setDraft({ ...draft, date_label: event.target.value })} placeholder="例如 20世纪中期" /></label><label><span>事件类型</span><select value={draft.event_type} onChange={(event) => setDraft({ ...draft, event_type: event.target.value })}>{timelineTypes.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label></div>
          <ResearchEntityPicker label="理论传统和知识理论或概念，可多选" endpoint="/catalog/admin/theory-system/nodes/" entityType="knowledge_node" step="maintenance_theory_timeline" field="nodes" multiple values={manyPickerValues(draft.nodes, timelineNodeName)} onChange={(next) => { setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, nodes: next.flatMap((value) => value.id ? [value.id] : []) }); }} />
          <ResearchEntityPicker label="关联学科，可多选" endpoint="/catalog/admin/disciplines/" entityType="discipline" step="maintenance_theory_timeline" field="disciplines" multiple values={manyPickerValues(draft.disciplines, timelineDisciplineName)} onChange={(next) => { setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, disciplines: next.flatMap((value) => value.id ? [value.id] : []) }); }} />
          <div className="inline-fields"><ResearchEntityPicker label="关联学者" endpoint="/catalog/admin/scholars/" entityType="person" step="maintenance_theory_timeline" field="scholar" values={onePickerValue(draft.scholar, timelineScholarName(draft.scholar))} onChange={(next) => { const picked = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, scholar: picked?.id ?? "" }); }} /><ResearchEntityPicker label="关联馆藏" endpoint="/catalog/admin/library/works/" entityType="work" step="maintenance_theory_timeline" field="work" values={onePickerValue(draft.work, timelineWorkName(draft.work))} onChange={(next) => { const picked = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, work: picked?.id ?? "" }); }} /></div>
          <label><span>来源</span><input value={draft.source} onChange={(event) => setDraft({ ...draft, source: event.target.value })} placeholder="书目、论文或馆藏来源" /></label>
          <TimelineEvidenceFields draft={draft} saved={editing} workName={entityLabels[draft.source_work] || editing?.evidence_file?.work_title || "已选择出处馆藏"} onLabels={(values) => setEntityLabels((current) => ({ ...current, ...pickerLabels(values) }))} onChange={(patch) => setDraft((current) => ({ ...current, ...patch }))} />
          <label><span>证据原文或来源说明</span><textarea rows={4} value={draft.evidence_text} onChange={(event) => setDraft({ ...draft, evidence_text: event.target.value })} /></label>
          <div className="inline-fields"><label><span>保存后的安排</span><select value={draft.review_status} onChange={(event) => setDraft({ ...draft, review_status: event.target.value })}><option value="suggested">留待核对</option><option value="approved" disabled={!canPublish && editing?.review_status !== "approved"}>准备公开</option><option value="rejected">不采用或准备下线</option></select></label><label><span>排序</span><input type="number" value={draft.display_order} onChange={(event) => setDraft({ ...draft, display_order: Number(event.target.value) })} /></label></div>
          </fieldset>
          <SavedDraftActions revision={editing?.editorial_revision} dirty={timelineDirty} busy={Boolean(pendingAction)} impact="请核对上方的事件预览与关联对象。确认发布后，公开时间线和关联页面会更新。" publish={() => void publishEvent()} />
          <EditorialConflictHelp visible={editConflict} href={location.href({ event: editing?.id ?? null })} />
          {message ? <AsyncStatus state={messageState} message={message} /> : null}
        </form>} />
      </div>
    </AdminFrame>
  );
}
