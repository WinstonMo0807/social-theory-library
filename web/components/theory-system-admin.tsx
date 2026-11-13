"use client";
import { AcademicRelations } from "./admin/academic-relations";

import { LoadingState } from "@/components/ui/loading-state";

import { confirmAction } from "@/lib/ui-dialog";

import { useScholarSave } from "./admin/knowledge/use-scholar-save";
import { RelationSourcePicker, type RelationSourceRequest } from "./admin/knowledge/relation-source-picker";
import type { components } from "@/lib/api/generated/schema";
import { ScholarProseEditor as KnowledgeProseEditor } from "./admin/knowledge/scholar-prose-editor";
import { nodeEditorialForSave, type NodeEditorialDetails, type NodeProseField } from "@/lib/api/node-editorial";
import type { ScholarProse } from "@/lib/api/scholar-prose";
import { TimelineSupplementalSources, TimelineSimilarCheck, emptyTimelineDetails, type TimelineEditorialDetails } from "./admin/knowledge/timeline-editor-details";
import { TimelineEvidenceImage, timelineEvidenceImageUrl } from "./admin/knowledge/timeline-evidence-image";
import { NodeMergeWorkspace } from "./admin/knowledge/node-merge-workspace";
import { TimelineMergeWorkspace } from "./admin/knowledge/timeline-merge-workspace";
import { TimelineParticipants } from "./admin/knowledge/timeline-participants";
import { workFilesPath } from "@/lib/api/work-files.client";
import type { WorkFilesState, WorkEdition } from "@/lib/api/work-files.types";
import timelineStyles from "./admin/knowledge/timeline-editor.module.css";
import { editorialHeaders, isEditorialConflict } from "@/lib/editorial-version";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { EditorialPrefillNotice, useEditorialPrefills } from "@/components/admin/curation/editorial-prefills";
import { safeAdminHref } from "@/lib/admin-route-context";
import type { CollectionPage, WorkLibraryRow } from "@/lib/api/admin-collections";
import { EditorialConflictHelp } from "@/components/admin/knowledge/editorial-conflict-help";

import {
  BookOpen,
  Check,
  Clock3,
  ExternalLink,
  FileText,
  History,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { TheoryGraphExplorer } from "@/components/theory-graph-explorer";
import { TheoryTimelinePublicList } from "@/components/public/theory-timeline-public-view";
import { KnowledgePublishEntry } from "@/components/admin/knowledge/knowledge-publish-control";
import { NodeAliasFields } from "./admin/knowledge/node-alias-fields";
import { KnowledgeVisualEditor } from "@/components/admin/knowledge/knowledge-visual-editor";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { adminListHref, adminPageNumber } from "@/lib/admin-route-context";
import { KnowledgeImagePanel } from "./admin/media/knowledge-image-panel";
import type { FormEvent, ReactNode, SetStateAction } from "react";
import { useCallback, useEffect, useEffectEvent, useId, useMemo, useRef, useState } from "react";
import { EntityLifecycleActions } from "@/components/entity-lifecycle-actions";
import { CurationFieldAssistant } from "@/components/admin/curation/curation-field-assistant";
import { asRecord, asString } from "@/components/admin/workflow/workflow-types";
import { ResearchEntityPicker } from "@/components/admin/research/research-entity-picker";
import { EntityPicker, type EntityValue } from "@/components/admin/forms/workflow-fields";
import {
  StringListEditor,
  StructuredRowsEditor,
} from "@/components/structured-editors";
import { apiRequest as baseApiRequest, getServerSessionCredential, subscribeToSessionChanges, normalizePublicResourceUrl } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
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
  editorial_details: NodeEditorialDetails;
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

function useEditorAccountKey() {
  const user = useAdminSession(), [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  return `${user?.id || ""}:${epoch}`;
}

function useEditorRequest() {
  const user = useAdminSession(), owner = String(user?.id || ""), lifetime = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController(); lifetime.current = controller;
    const unsubscribe = subscribeToSessionChanges(() => controller.abort());
    return () => { controller.abort(); unsubscribe(); };
  }, [owner]);
  return useCallback(<T,>(path: string, options: RequestInit = {}, credential?: string | null): Promise<T> => {
    const controller = lifetime.current;
    if (!owner || !controller || controller.signal.aborted) return Promise.reject(Error("编辑账户已变化，请重新打开当前资料。"));
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(60000), ...(options.signal ? [options.signal] : [])]);
    const headers = new Headers(options.headers); headers.set("X-Editor-Owner", owner);
    return withPrivateOwner(owner, () => baseApiRequest<T>(path, {...options, headers, signal, cache:"no-store"}, credential || getServerSessionCredential(), false), signal);
  }, [owner]);
}

function useAdminData<T>(path: string | null) {
  const user = useAdminSession(), owner = String(user?.id || "");
  const load = useCallback((url: string, signal: AbortSignal) => baseApiRequest<T>(url, {signal,cache:"no-store",headers:{"X-Editor-Owner":owner}}, getServerSessionCredential()), [owner]);
  const resource = usePersistentWorkspace<T>(path || "", owner, undefined, load);
  return { data: resource.error ? null : resource.data, loading: resource.loading, error: resource.error, refresh: resource.reload };
}

function AdminFrame({ eyebrow, title, description, actions, children }: {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="admin-page theory-system-admin">
      <header className="admin-page-title theory-admin-title">
        <div><p>{eyebrow}</p><h1>{title}</h1>{description ? <span>{description}</span> : null}</div>
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
  editorial_details: NodeEditorialDetails;
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
  subdisciplines: string[];
  topics: string[];
  status: string;
  sort_order: number;
};

const emptyNodeDraft: NodeDraft = {
  editorial_details: { internal_note: "", prose: {} },
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

function nodeToDraft(node: KnowledgeNode): NodeDraft {
  return {
    editorial_details: nodeEditorialForSave(node.editorial_details, node),
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
    subdisciplines: (node.subdiscipline_links ?? []).map(
      (item) => item.subdiscipline.id,
    ),
    topics: (node.topic_links ?? []).map((item) => item.topic.id),
    status: node.status,
    sort_order: node.sort_order,
  };
}

export function TheoryNodesAdmin({ initialNodeId = "" }: { initialNodeId?: string }) {
  const account = useEditorAccountKey();
  const search = useSearchParams();
  const nodeId = initialNodeId || search.get("node") || "";
  const legacyId = search.get("legacy_id") || "";
  if (search.get("section") === "timeline") return <TimelineEditor key={`${account}:${nodeId}:${search.get("event") || "list"}`} nodeId={nodeId} requestedId={search.get("event") || ""} />;
  return <TheoryNodesEditor key={`${account}:${nodeId}:${legacyId}`} initialNodeId={nodeId} initialLegacyId={legacyId} />;
}

function TheoryNodesEditor({ initialNodeId, initialLegacyId }: { initialNodeId: string; initialLegacyId: string }) {
  const apiRequest = useEditorRequest();
  const user = useAdminSession(), owner = String(user?.id || ""), command = useScholarSave(owner, "node");
  const canEdit = hasAdminCapability(user, "can_edit_draft_authority"), canCreate = hasAdminCapability(user, "can_create_authority");
  const relationGuard = useRef({dirty:false,pending:false,composing:false});
  const [knownSavedId, setKnownSavedId] = useState("");
  const composing = useRef(false), mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const theoryLocation = useEditorListLocation();
  const nodePage = adminPageNumber(theoryLocation.search.get("page"));
  const [editConflict, setEditConflict] = useState(false);
  const [nodeType, setNodeType] = useState("theory_tradition");
  const [legacyId, setLegacyId] = useState(initialLegacyId);
  const [legacyOpened, setLegacyOpened] = useState(false);
  const [requestedNodeId, setRequestedNodeId] = useState(initialNodeId);
  const [requestedNodeOpened, setRequestedNodeOpened] = useState(false);
  const [statusFilter, setStatusFilter] = useState(theoryLocation.search.get("status") || "");
  const [disciplineFilter, setDisciplineFilter] = useState(theoryLocation.search.get("discipline") || "");
  const [query, setQuery] = useState(theoryLocation.search.get("q") || "");
  const [editing, setEditing] = useState<KnowledgeNode | null>(null);
  const [draft, setDraft] = useState<NodeDraft>(emptyNodeDraft);
  function changeNodeProse(field: NodeProseField, text: string, format: NonNullable<ScholarProse["biography"]>) {
    setDraft(current => ({ ...current, [field]: text, editorial_details: { ...current.editorial_details,
      prose: { ...current.editorial_details.prose, [field]: { text, text_style: format.text_style || "paragraph", text_marks: format.text_marks || [] } },
    } }));
  }
  const nodeDirty = useUnsavedForm(draft, editing ? nodeToDraft(editing) : emptyNodeDraft);
  const prefills = useEditorialPrefills(editing?.id || "new-theory", draft, setDraft);
  const [imageRevision, setImageRevision] = useState(0);
  const [message, setMessage] = useState("");
  const [messageState, setMessageState] = useState<ActionState>("idle");
  const { pendingAction, startAction, finishAction } = useActionGuard();
  useUnsavedForm(Boolean(command.recovery) || Boolean(pendingAction) || Boolean(knownSavedId), false);
  const [entityLabels, setEntityLabels] = useState<Record<string, string>>({});
  const [versions, setVersions] = useState<Array<{ id: string; version_number: number; change_note: string; created_by_name: string; created_at: string }> | null>(null);
  const [pendingRevision, setPendingRevision] = useState<EditorialRevisionSummary | null>(null);

  const params = useMemo(() => {
    const search = new URLSearchParams({ node_type: nodeType, page: String(nodePage) });
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
      setMessage("已打开对应的理论或概念，可在本页继续编辑。");
      setVersions(null);
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
      setPendingRevision(node.editorial_revision ?? null);
      setRequestedNodeOpened(true);
    });
    return () => {
      active = false;
    };
  }, [requestedNode.data, requestedNodeId, requestedNodeOpened]);

  async function start(node?: KnowledgeNode) {
    if (composing.current || command.recovery || pendingAction || knownSavedId) return;
    if (relationGuard.current.pending || relationGuard.current.composing) { setMessage("请先在关系详情核对原请求，再切换主体。"); setMessageState("error"); return; }
    if (relationGuard.current.dirty && !(await confirmAction("关系还有未保存输入，放弃这些输入并切换主体吗？"))) return;
    if (nodeDirty && !(await confirmAction("当前理论或概念还有未保存的填写。放弃填写并切换吗？"))) return;
    prefills.clear();
    setEditing(node ?? null);
    setDraft(node ? nodeToDraft(node) : { ...emptyNodeDraft, node_type: nodeType, primary_discipline: disciplines.data?.results[0]?.id ?? "" });
    setMessage("");
    setMessageState("idle");
    setEntityLabels({});
    setVersions(null);
    setPendingRevision(node?.editorial_revision ?? null);
    return true;
  }

  async function saveNode(event?: FormEvent, draftOnly = false) {
    event?.preventDefault();
    if (relationGuard.current.dirty || relationGuard.current.pending || relationGuard.current.composing) { setMessage("请先保存关系输入并核对原请求，再保存主体。"); setMessageState("error"); return false; }
    if (composing.current || !canEdit || !command.ready || command.recovery || knownSavedId || openingNode || !editing && !canCreate) return false;
    const token = getServerSessionCredential();
    if (!token) return false;
    const actionKey = "save-theory-node";
    if (!draftOnly && draft.status === "published" && editing?.status !== "published" && !(await confirmAction("保存并公开这份理论或概念资料？读者将看到本页内容。"))) return false;
    if (!startAction(actionKey)) return false;
    setEditConflict(false);
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
    const subdiscipline_links = draft.subdisciplines.map(
      (subdiscipline_id, index) => ({
        subdiscipline_id,
        is_primary: index === 0,
        relation_role: index === 0 ? "home" : "related",
        source: "editorial",
        confidence: 1,
        sort_order: index,
        status: draft.status === "published" ? "published" : "pending",
      }),
    );
    const topic_links = draft.topics.map((topic_id, index) => ({
      topic_id,
      relation_label: index === 0 ? "核心研究主题" : "相关研究主题",
      source: "editorial",
      confidence: 1,
      sort_order: index,
      status: draft.status === "published" ? "published" : "pending",
    }));
    const payload = {
      assisted_candidates: prefills.ids,
      assisted_candidate_decisions: prefills.decisions,
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
      editorial_details: nodeEditorialForSave(draft.editorial_details, draft),
      start_year: draft.start_year ? Number(draft.start_year) : null,
      end_year: draft.end_year ? Number(draft.end_year) : null,
      period_label: draft.period_label,
      parent: draft.parent || null,
      primary_discipline: draft.primary_discipline || null,
      discipline_links,
      subdiscipline_links,
      topic_links,
      status: draftOnly ? (editing?.status ?? "draft") : draft.status,
      sort_order: draft.sort_order,
    };
    try {
      const saved = await command.save<KnowledgeNode>(
        `/catalog/admin/theory-system/nodes/${editing ? `${editing.id}/` : ""}`,
        JSON.stringify(payload), editing ? editorialHeaders(editing) : {}, editing ? "PATCH" : "POST",
      );
      if (!mounted.current) return false;
      setEditing(saved);
      prefills.clear();
      setPendingRevision(saved.editorial_revision ?? null);
      setDraft(nodeToDraft(saved));
      setMessage(saved.editorial_revision
        ? `本页资料已保存（${new Date().toLocaleTimeString("zh-CN")}），尚未发布。公开页保持原内容，你仍在当前编辑页。`
        : `本页资料已保存（${new Date().toLocaleTimeString("zh-CN")}）。${saved.status === "published" ? "当前资料已公开。" : "尚未公开。"}你仍在当前编辑页。`);
      setMessageState("success");
      nodes.refresh();
      allNodes.refresh();
      return true;
    } catch (reason) {
      if (!mounted.current) return false;
      setEditConflict(isEditorialConflict(reason));
      setMessage(reason instanceof Error ? reason.message : "保存失败");
      setMessageState("error");
      return false;
    } finally {
      finishAction(actionKey);
    }
  }

  function applyRecoveredNode(saved: KnowledgeNode) {
    setEditing(saved); setDraft(nodeToDraft(saved)); setNodeType(saved.node_type);
    setPendingRevision(saved.editorial_revision ?? null); setKnownSavedId("");
    setRequestedNodeOpened(true); setLegacyOpened(true); prefills.clear();
    setVersions(null); setEditConflict(false); nodes.refresh(); allNodes.refresh();
  }
  async function recoverNode(mode: "lookup" | "stop" | "retry" | "read") {
    if (composing.current || !startAction("recover-node")) return;
    setMessage(""); setMessageState("pending");
    try {
      if (mode === "retry") {
        if (!command.canRetry) return;
        const saved = await command.save<KnowledgeNode>("", "{}", {}, "POST");
        if (!mounted.current) return;
        applyRecoveredNode(saved); setMessage("原请求已完成，当前保存版本已重新读取。");
      } else {
        let id = knownSavedId;
        if (mode !== "read") {
          const receipt = await command.lookup(mode === "stop");
          if (!receipt || !mounted.current) return;
          if (receipt.state === "cancelled") { setMessage("未执行的保存已停止，当前输入仍保留。"); setMessageState("success"); return; }
          id = receipt.node_id || "";
          if (!id) throw Error("原请求缺少对象编号，请核对操作记录。");
          setKnownSavedId(id);
        }
        if (!id) return;
        const saved = await apiRequest<KnowledgeNode>(`/catalog/admin/theory-system/nodes/${id}/`, { cache:"no-store" }, getServerSessionCredential());
        if (!mounted.current) return;
        applyRecoveredNode(saved); setMessage("原保存已完成，已返回同一个理论或概念；不会再次新建。");
      }
      setMessageState("success");
    } catch (reason) { if (mounted.current) { setMessage(reason instanceof Error ? reason.message : "原请求暂不可读取。"); setMessageState("error"); } }
    finally { finishAction("recover-node"); }
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
    if (!pendingRevision || composing.current || command.recovery || knownSavedId) return;
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = "publish-node-revision";
    if (!startAction(actionKey)) return;
    setMessageState("pending");
    try {
      if (pendingRevision.has_conflict) throw new Error("正式内容已经变化，请刷新后重新建立草稿。");
      if (nodeDirty) { setMessage("还有未保存的填写，请先保存本页，再发布已保存的修改。"); setMessageState("error"); return; }
      if (!(await confirmAction("发布已保存的修改？相关理论、学科页面将更新，尚未保存的输入不会发布。"))) {
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

  async function reloadMergedNode() {
    if (!editing) return;
    const current = await apiRequest<KnowledgeNode>(`/catalog/admin/theory-system/nodes/${editing.id}/`, { cache: "no-store" }, getServerSessionCredential());
    if (!mounted.current) return;
    setEditing(current); setDraft(nodeToDraft(current)); setPendingRevision(current.editorial_revision ?? null);
    setEditConflict(false); nodes.refresh(); allNodes.refresh(); requestedNode.refresh();
  }

  const visibleNodes = nodes.data?.results ?? [];
  const openingNode = Boolean(requestedNodeId && !requestedNodeOpened) || Boolean(legacyId && !legacyOpened);
  const disciplineName = (id: string) => disciplines.data?.results.find((item) => item.id === id)?.name || entityLabels[id] || "已选择学科";
  const subdisciplineName = (id: string) => editing?.subdiscipline_links?.find((item) => item.subdiscipline.id === id)?.subdiscipline.name || entityLabels[id] || "已选择子学科";
  const topicName = (id: string) => editing?.topic_links?.find((item) => item.topic.id === id)?.topic.name || entityLabels[id] || "已选择主题";
  const nodeName = (id: string) => allNodes.data?.results.find((item) => item.id === id)?.canonical_name_zh || entityLabels[id] || "已选择理论或概念";
  return (
    <AdminFrame
      eyebrow="学者与知识　›　理论、概念与关系编辑"
      title="理论、概念与关系编辑"

      actions={<details className="node-page-tools" data-action-menu><summary aria-label="更多页面操作">···</summary><div data-menu-panel><Link className="admin-outline-button" href="/admin/theories/timeline">查看全部理论事件</Link><button className="admin-outline-button" type="button" onClick={() => { nodes.refresh(); allNodes.refresh(); }}><RefreshCw size={15} />刷新</button></div></details>}
    >
      {command.recovery || knownSavedId || command.error ? <section className="admin-panel" aria-label="核对理论与概念保存">
        <h2>核对原保存</h2><p>{knownSavedId ? "原保存已完成，但原记录尚未重新读取。请先核对原对象，不要再次创建。" : "保存结果尚未确认。输入与原请求编号已保留，请查询结果后继续。"}</p>
        {command.error ? <p role="alert">{command.error}</p> : null}{message ? <p role="status">{message}</p> : null}
        {command.recovery ? <><button type="button" disabled={Boolean(pendingAction)} onClick={() => void recoverNode("lookup")}>查询原请求</button><button type="button" disabled={Boolean(pendingAction)} onClick={() => void recoverNode("stop")}>停止未执行的保存</button>{command.canRetry ? <button type="button" disabled={Boolean(pendingAction)} onClick={() => void recoverNode("retry")}>重试同一请求</button> : null}</> : null}
        {knownSavedId ? <button type="button" disabled={Boolean(pendingAction)} onClick={() => void recoverNode("read")}>重新读取原对象</button> : null}
      </section> : null}
      <div className="theory-node-admin-grid knowledge-object-host-layout" inert={Boolean(command.recovery) || Boolean(pendingAction) || Boolean(knownSavedId)} onCompositionStartCapture={() => { composing.current = true; }} onCompositionEndCapture={() => { composing.current = false; }}>
        <section data-content-section className="admin-panel theory-node-table-panel"><header data-section-heading>选择已有条目或新建理论、概念</header>
          <nav className="theory-node-tabs">
            {editableNodeTypeEntries.map(([value, label]) => <button className={nodeType === value ? "active" : ""} type="button" key={value} onClick={async () => { if((await start())){ theoryLocation.update({ page: 1, node_type: value }); setNodeType(value); setDraft(current=>({...current,node_type:value})); } }}>{label}</button>)}
          </nav>
          <div className="theory-admin-filters">
            <ResearchEntityPicker label="所属学科筛选" endpoint="/catalog/admin/disciplines/" entityType="discipline" step="maintenance_theory_nodes" field="filter_discipline" values={onePickerValue(disciplineFilter, disciplineName(disciplineFilter))} onChange={(next) => { const selected = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDisciplineFilter(selected?.id ?? ""); theoryLocation.update({ page: 1, discipline: selected?.id ?? "" }); }} />
            <label><span>状态</span><select data-stl-select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); theoryLocation.update({ page: 1, status: event.target.value }); }}><option value="">全部</option><option value="draft">草稿</option><option value="pending">待审核</option><option value="published">已发布</option><option value="rejected">已拒绝</option><option value="archived">已下线</option></select></label>
            <label className="theory-admin-search"><span>名称或别名</span><div><Search size={15} /><input value={query} onChange={(event) => { setQuery(event.target.value); theoryLocation.update({ page: 1, q: event.target.value }); }} placeholder="搜索理论或概念……" /></div></label>
            <button className="button" type="button" onClick={() => start()}><Plus size={15} />新建理论或概念</button>
          </div>
          <ErrorNotice message={nodes.error || disciplines.error} retry={nodes.refresh} />
          {nodes.loading ? <div className="theory-admin-loading">正在读取理论或概念……</div> : null}
          <div className="theory-admin-table-wrap">
            <table className="theory-admin-table">
              <thead><tr><th>标准中文名</th><th>资料类型</th><th>主要学科</th><th>关联学科</th><th>别名</th><th>馆藏</th><th>关系</th><th>状态</th><th>最后编辑</th></tr></thead>
              <tbody>{visibleNodes.map((node) => <tr className={editing?.id === node.id ? "selected" : ""} key={node.id}>
                <td data-label="名称"><button type="button" aria-label={`编辑 ${node.canonical_name_zh}`} onClick={() => start(node)}><strong>{node.canonical_name_zh}</strong><small>{node.canonical_name_en}</small></button></td>
                <td data-label="类型">{nodeTypeLabels[node.node_type]}</td>
                <td data-label="主要学科">{node.primary_discipline_data?.name || "未指定"}</td>
                <td data-label="关联学科">{node.discipline_links.filter((item) => item.relation_type !== "primary").map((item) => item.discipline.name).join("、") || "—"}</td>
                <td data-label="别名">{node.aliases.length}</td><td data-label="馆藏">{node.work_count}</td><td data-label="关系">{node.relation_count}</td>
                <td data-label="状态"><StatusBadge value={node.status} /></td><td data-label="最后编辑">{asDate(node.updated_at)}</td>
              </tr>)}</tbody>
            </table>
          </div>
          {!nodes.loading && !visibleNodes.length ? <div className="theory-admin-empty"><FileText size={22} /><strong>当前筛选下没有理论或概念</strong><button type="button" onClick={() => start()}>建立第一个理论或概念</button></div> : null}
          <EditorListPages data={nodes.data} page={nodePage} pageKey="page" label="理论与概念分页" ordering="按排序值、名称及编号稳定排序" busy={nodes.loading} href={(updates) => theoryLocation.href({ node_type: nodeType, status: statusFilter, discipline: disciplineFilter, q: query, ...updates })} />
        </section>

        <KnowledgeVisualEditor onRelationGuardChange={value=>{relationGuard.current=value;}} objectType={knowledgeStudioNodeType(editing?.node_type || draft.node_type)} objectId={editing?.id} savedRecord={editing} onPublished={() => {nodes.refresh();allNodes.refresh();requestedNode.refresh();setEditConflict(true);setMessage("发布操作已提交，请打开最新资料后继续编辑。");}} draft={{...draft,preview_labels:{...entityLabels,...Object.fromEntries((disciplines.data?.results || []).map(row=>[row.id,row.name]))}}} dirty={nodeDirty} refreshKey={`${editing?.updated_at}:${imageRevision}`}>
        {openingNode ? <div role="status"><LoadingState>正在读取指定理论或概念，载入后即可编辑。</LoadingState><ErrorNotice message={requestedNode.error || nodes.error} retry={requestedNodeId ? requestedNode.refresh : nodes.refresh} /></div> : null}
        <form className="admin-panel theory-node-editor" onSubmit={(event) => void saveNode(event, true)} inert={openingNode} aria-busy={openingNode}>
          <p data-editor-section="publication">保存本页名称、说明、分类和关联，不跳转。已有公开内容的修改需另行发布。时间线在当前理论的次级页面维护。</p>
          <EditorialPrefillNotice state={prefills} />
          <fieldset disabled={openingNode || !canEdit || !command.ready || !editing && !canCreate} style={{ display: "contents" }}>
          <header data-editor-section="publication"><div><h2>{editing ? `编辑 ${editing.canonical_name_zh}` : "新建条目"}</h2><p>{editing ? `相关文献 ${editing.work_count} · 关联 ${editing.relation_count}` : "先填写名称和简介，其他资料可以稍后补充。"}</p></div>{editing ? <div className="theory-editor-preview-links"><Link href={`/admin/preview/knowledge/${knowledgeStudioNodeType(editing.node_type)}/${editing.id}`} target="_blank">预览已保存内容 <ExternalLink size={14} /></Link><Link href={`/admin/theories/${editing.id}?section=timeline&returnTo=${encodeURIComponent(theoryLocation.href({ node: editing.id }))}`}>管理此理论的时间线</Link><Link href={`/theories/graph?center=${encodeURIComponent(editing.slug)}`} target="_blank">查看公开关系图 <ExternalLink size={14} /></Link></div> : null}</header>
          <div data-editor-section="identity" className="node-basic-fields"><label><span>节点类型</span><select data-stl-select value={draft.node_type} onChange={(event) => setDraft({ ...draft, node_type: event.target.value })}>{editableNodeTypeEntries.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label><span>名称</span><input autoComplete="off" required value={draft.canonical_name_zh} onChange={(event) => setDraft({ ...draft, canonical_name_zh: event.target.value })} /></label>
          <NodeAliasFields value={draft.aliases} onChange={aliases=>setDraft({...draft,aliases})}/>
          <div className="node-explanatory-object"><span aria-hidden="true">解释对象</span><KnowledgeProseEditor label="解释对象" value={draft.summary} format={draft.editorial_details.prose.summary} recommendedLength={300} maxLength={30000} disabled={!canEdit||!editing&&!canCreate||Boolean(pendingAction)||!command.ready||Boolean(command.recovery)||Boolean(knownSavedId)} onChange={(text,format)=>changeNodeProse("summary",text,format)}/></div>
          <label><span>编辑说明（仅内部可见）</span><textarea rows={3} maxLength={500} value={draft.editorial_details.internal_note} onChange={event=>setDraft(current=>({...current,editorial_details:{...current.editorial_details,internal_note:event.target.value}}))}/><small>{draft.editorial_details.internal_note.length}/500</small></label></div>
          <section data-content-section data-editor-section="identity" className="node-more-fields"><header data-section-heading>名称建议、外文与分类</header>
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
          <label><span>外文名称</span><input value={draft.canonical_name_en} onChange={(event) => setDraft({ ...draft, canonical_name_en: event.target.value })} /></label>
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
          <div className="inline-fields three"><ResearchEntityPicker label="主要学科" endpoint="/catalog/admin/disciplines/" entityType="discipline" step="maintenance_theory_nodes" field="primary_discipline" values={onePickerValue(draft.primary_discipline, disciplineName(draft.primary_discipline))} onChange={(next) => { const selected = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, primary_discipline: selected?.id ?? "", related_disciplines: draft.related_disciplines.filter((id) => id !== selected?.id) }); }} /><ResearchEntityPicker label="所属理论或概念" endpoint="/catalog/admin/theory-system/nodes/" entityType="knowledge_node" step="maintenance_theory_nodes" field="parent" values={onePickerValue(draft.parent, nodeName(draft.parent))} onChange={(next) => { const selected = next.at(-1); if (selected?.id === editing?.id) return; setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, parent: selected?.id ?? "" }); }} /><label><span>固定链接</span><input required value={draft.slug} onChange={(event) => setDraft({ ...draft, slug: event.target.value })} placeholder="symbolic-interactionism" /></label></div>
          <section data-content-section className="theory-editor-group"><header data-section-heading>更多学科和主题关联</header>
          <ResearchEntityPicker label="关联学科" endpoint="/catalog/admin/disciplines/" entityType="discipline" step="maintenance_theory_nodes" field="related_disciplines" multiple values={manyPickerValues(draft.related_disciplines, disciplineName)} onChange={(next) => { setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, related_disciplines: next.flatMap((value) => value.id && value.id !== draft.primary_discipline ? [value.id] : []) }); }} />
          <div className="inline-fields">
            <ResearchEntityPicker label="子学科" endpoint="/catalog/admin/subdisciplines/" entityType="subdiscipline" step="maintenance_theory_nodes" field="subdiscipline_links" multiple values={manyPickerValues(draft.subdisciplines, subdisciplineName)} onChange={(next) => { setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, subdisciplines: next.flatMap((value) => value.id ? [value.id] : []) }); }} />
            <ResearchEntityPicker label="主题" endpoint="/catalog/admin/topics/" entityType="topic" step="maintenance_theory_nodes" field="topic_links" multiple values={manyPickerValues(draft.topics, topicName)} onChange={(next) => { setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, topics: next.flatMap((value) => value.id ? [value.id] : []) }); }} />
          </div>
          <div className="workflow-field-assistant-row"><strong>学科分类</strong><CurationFieldAssistant label="学科分类" targetType="knowledge_node" targetId={editing?.id} fieldName="discipline" currentValue={{ primary: draft.primary_discipline, related: draft.related_disciplines }} onFillSuggestion={async (candidateId, value, label) => {
            const row = asRecord(value), id = asString(row.discipline_id);
            if (!id) return false;
            if (row.relation_type === "primary") {
              if (draft.primary_discipline && draft.primary_discipline !== id && !(await confirmAction(`将主要学科从“${disciplineName(draft.primary_discipline)}”改为“${label}”？这一步只填写表单，尚未保存。`))) return false;
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
          </section>
          </section>
          <section data-content-section data-editor-section="identity" className="node-more-fields"><header data-section-heading>定义、问题、命题与发展时期</header>
          <KnowledgeProseEditor label="完整定义" value={draft.definition} format={draft.editorial_details.prose.definition} recommendedLength={1000} maxLength={30000} disabled={!canEdit||!editing&&!canCreate||Boolean(pendingAction)||!command.ready||Boolean(command.recovery)||Boolean(knownSavedId)} onChange={(text,format)=>changeNodeProse("definition",text,format)}/>
          <StringListEditor label="核心问题" itemLabel="问题" value={editorLines(draft.core_questions)} onChange={(value) => setDraft({ ...draft, core_questions: value.join("\n") })} addLabel="添加问题" />
          <StringListEditor label="基本命题" itemLabel="命题" value={editorLines(draft.basic_propositions)} onChange={(value) => setDraft({ ...draft, basic_propositions: value.join("\n") })} addLabel="添加命题" />
          <KnowledgeProseEditor label="理论边界" value={draft.theoretical_boundary} format={draft.editorial_details.prose.theoretical_boundary} recommendedLength={1000} maxLength={30000} disabled={!canEdit||!editing&&!canCreate||Boolean(pendingAction)||!command.ready||Boolean(command.recovery)||Boolean(knownSavedId)} onChange={(text,format)=>changeNodeProse("theoretical_boundary",text,format)}/>
          <div className="inline-fields three"><label><span>开始年份</span><input type="number" value={draft.start_year} onChange={(event) => setDraft({ ...draft, start_year: event.target.value })} /></label><label><span>结束年份</span><input type="number" value={draft.end_year} onChange={(event) => setDraft({ ...draft, end_year: event.target.value })} /></label><label><span>显示时期</span><input value={draft.period_label} onChange={(event) => setDraft({ ...draft, period_label: event.target.value })} /></label></div>
          </section>
          <div data-editor-section="publication" className="inline-fields"><label><span>审核状态</span><select data-stl-select disabled title="状态通过发布或下线操作更新" value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}><option value="draft">草稿</option><option value="pending">提交审核</option><option value="published">发布</option><option value="rejected">拒绝</option><option value="archived">下线</option></select></label><label><span>显示顺序</span><input type="number" min={0} value={draft.sort_order} onChange={(event) => setDraft({ ...draft, sort_order: Number(event.target.value) })} /></label></div>
          <p>页面图片在媒体面板中选择。请先保存其他未保存内容。</p>
          {editing ? <div className="theory-node-secondary-actions"><ActionButton type="button" state={pendingAction === "load-node-versions" ? "pending" : "idle"} pendingLabel="读取中" disabled={Boolean(pendingAction) && pendingAction !== "load-node-versions"} onClick={() => void loadVersions()}><History size={14} />历史版本</ActionButton></div> : null}
          {versions ? <section className="theory-version-list"><header><strong>历史版本</strong><button type="button" aria-label="关闭历史版本" onClick={() => setVersions(null)}><X size={14} /></button></header>{versions.map((version) => <article key={version.id}><strong>第 {version.version_number} 版</strong><span>{version.change_note || "内容更新"}</span><small>{version.created_by_name || "系统"} · {asDate(version.created_at)}</small></article>)}</section> : null}
          {pendingRevision?.status === "draft" ? <section className="theory-editorial-revision"><div><strong>待发布编辑草稿</strong><p>第 {pendingRevision.revision} 版修改 {pendingRevision.changed_fields.join("、")}。当前公开页仍使用正式内容。</p></div><KnowledgePublishEntry disabled={Boolean(pendingAction) || pendingRevision.has_conflict || nodeDirty} onFallback={() => void publishRevision()}/></section> : null}
          {editing ? <div data-editor-section="impact"><NodeMergeWorkspace key={`${owner}:${editing.id}`} owner={owner} nodeId={editing.id} disabled={nodeDirty || Boolean(command.recovery) || Boolean(knownSavedId) || Boolean(pendingAction)} onChanged={reloadMergedNode}/></div> : null}
          {editing ? <EntityLifecycleActions kind="knowledge-node" id={editing.id} name={editing.canonical_name_zh} status={draft.status} previewHref={`/theories/nodes/${editing.slug}`} onChanged={(snapshot) => { setDraft((current) => ({ ...current, status: snapshot.status })); setEditing((current) => current ? { ...current, status: snapshot.status } : current); nodes.refresh(); allNodes.refresh(); }} onDeleted={() => { setEditing(null); setDraft({ ...emptyNodeDraft, node_type: nodeType, primary_discipline: disciplines.data?.results[0]?.id ?? "" }); nodes.refresh(); allNodes.refresh(); }} /> : null}
          <div className="theory-editor-footer"><ActionButton className="button" state={pendingAction === "save-theory-node" ? "pending" : "idle"} pendingLabel="正在保存本页资料" disabled={Boolean(pendingAction) && pendingAction !== "save-theory-node"} type="submit"><Save size={15} />{"保存本页草稿"}</ActionButton></div>
          {message ? <AsyncStatus state={messageState} message={message} /> : null}
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
  edit_version: string;
  deleted?: boolean;
  editorial_revision?: unknown;
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

export type AdminKnowledgeRelation = {
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
  source_anchor: components["schemas"]["RelationAnchorInput"] | null;
  source_material: components["schemas"]["RelationAnchorMaterial"] | null;
  confidence: number;
  status: string;
  updated_at: string;
  editorial_revision?: EditorialRevisionSummary;
  public_status?: string;
};

type KnowledgeRelation = AdminKnowledgeRelation;
// Manual input has no calibrated machine confidence. Keep existing values when editing.
const emptyRelationDraft = { source_node: "", target_node: "", relation_type: "criticizes", direction: "directed", description: "", evidence_source: "", source_anchor: null as AdminKnowledgeRelation["source_anchor"], confidence: 0, status: "pending" };
function relationToDraft(row: KnowledgeRelation) {
  return { source_node: row.source_node, target_node: row.target_node, relation_type: row.relation_type, direction: row.direction, description: row.description, evidence_source: row.evidence_source, source_anchor: row.source_anchor || null, confidence: row.confidence, status: row.status };
}

function RelationGraphPreview({relations,centerId,onSelect}:{relations:KnowledgeRelation[];centerId?:string;onSelect:(row:KnowledgeRelation)=>void}) {
 const visible=relations.filter(row=>!centerId || row.source_node===centerId || row.target_node===centerId);
 const nodes=[...new Map(visible.flatMap(row=>[{id:row.source_node,name:row.source_name,kind:"knowledge_node" as const,node_type:"theory_tradition",summary:row.description},{id:row.target_node,name:row.target_name,kind:"knowledge_node" as const,node_type:"theory_tradition",summary:row.description}]).map(row=>[row.id,row])).values()];
 return <TheoryGraphExplorer graph={{center:centerId || null,nodes,edges:visible.map(row=>({id:row.id,source:row.source_node,target:row.target_node,relation_type:row.relation_type,relation_label:row.relation_label,direction:row.direction,description:row.description})),depth:1,limit:visible.length,truncated:false}} onSelectRelation={id=>{const row=relations.find(item=>item.id===id);if(row)onSelect(row);}}/>;
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
  const search = useSearchParams();
  return <AcademicRelations legacyType={search.get("node") ? "node" : undefined} legacyId={search.get("node") || undefined} />;
}

type InlineRelation = RelationSourceRequest & {nodeId:string;onGuardChange:(value:{dirty:boolean;pending:boolean;composing:boolean})=>void;onSaved:()=>void};
export function NodeRelationEditor({nodeId}:{requestedId?:string} & InlineRelation) {
  return <AcademicRelations legacyType="node" legacyId={nodeId} />;
}
export type TimelineRelation = {
  participant_role?: string;
  participant_role_label?: string;
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

export type AdminTimelineEvent = {
  merged_into?: string|null;
  start_date?: string|null;
  end_date?: string|null;
  editorial_details?: TimelineEditorialDetails;
  id: string;
  title: string;
  description: string;
  event_type: string;
  start_year: number | null;
  end_year: number | null;
  date_label: string;
  date_precision?: "unknown" | "year" | "approximate" | "range" | "day" | "month";
  subject_edition?: string | null;
  orientation: string;
  source: string;
  evidence_asset: string | null;
  evidence_file?: TimelineEvidenceFile | null;
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
  editorial_revision?: EditorialRevisionSummary;
  public_status?: string;
};

type TimelineEvent = AdminTimelineEvent;

type TimelineDraft = {
  participants: TimelineRelation[];
  start_date: string;
  end_date: string;
  editorial_details: TimelineEditorialDetails;
  title: string;
  description: string;
  event_type: string;
  start_year: string;
  end_year: string;
  date_label: string;
  date_precision: "unknown" | "year" | "approximate" | "range" | "day" | "month";
  subject_edition: string;
  source: string;
  source_work: string;
  source_edition: string;
  evidence_asset: string;
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
  ["birth","人物出生"], ["death","人物去世"], ["appointment","任职任教"],
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
  participants: [],
  start_date:"",end_date:"",
  editorial_details: emptyTimelineDetails(),
  title: "",
  description: "",
  event_type: "publication",
  start_year: "",
  end_year: "",
  date_label: "",
  date_precision: "unknown",
  subject_edition: "",
  source: "",
  source_work: "",
  source_edition: "",
  evidence_asset: "",
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
    participants: event.relations.filter(row => row.scholar),
    start_date:event.start_date||"",end_date:event.end_date||"",
    editorial_details: { ...emptyTimelineDetails(), ...event.editorial_details },
    title: event.title,
    description: event.description,
    event_type: event.event_type,
    start_year: event.start_year?.toString() ?? "",
    end_year: event.end_year?.toString() ?? "",
    date_label: event.date_label,
    date_precision: event.date_precision || "unknown",
    subject_edition: event.subject_edition || "",
    source: event.source,
    source_work: event.evidence_file?.work_id ?? "",
    source_edition: event.evidence_file?.edition_id ?? "",
    evidence_asset: event.evidence_asset ?? "",
    evidence_page: event.evidence_page?.toString() ?? "",
    evidence_printed_label: event.evidence_printed_label,
    evidence_text: event.evidence_text,
    confidence: event.confidence,
    review_status: event.review_status,
    display_order: event.display_order,
    nodes: event.relations.filter((item) => item.node).map((item) => item.node as string),
    disciplines: event.relations.filter((item) => item.discipline).map((item) => item.discipline as string),
    scholar: event.scholar ?? "",
    // A related work is not automatically the event's subject publication.
    work: event.work ?? "",
  };
}

type TimelineEvidenceFile = {
  id: string; work_id: string; work_title: string; edition_id: string; edition_label: string;
  filename: string; version: number; page_count: number; reader_href: string | null; detail: string;
};

function TimelineWorkCard({data,editionId,preview,children}:{data:WorkFilesState;editionId:string;preview?:boolean;children?:ReactNode}) {
  const edition:WorkEdition|undefined=editionId?data.editions.find(row=>row.id===editionId):undefined;
  const cover=editionId?edition?.cover_url:data.work.cover_url;
  const authors=edition?edition.contributors.filter(row=>row.role==="author").map(row=>row.name):data.work.authors;
  return <div className={timelineStyles.workCard} data-preview={preview||undefined}>
    {cover?<img src={normalizePublicResourceUrl(cover)} alt={`${data.work.title}封面`}/>:<span className={timelineStyles.noCover}><BookOpen size={22}/></span>}
    <div><strong>{data.work.title}</strong><small>{authors.join("、")||"责任者待核对"}</small><small>{editionId?edition?.label||"所选出版版本尚未读回":data.work.original_publication_year||"出版年份待核对"}</small>{children}</div>
  </div>;
}

function TimelineSubjectEdition({ work, value, onChange }: {
  work: string; value: string; onChange: (edition: string) => void;
}) {
  const [page, setPage] = useState(1);
  const base = "/catalog/admin/library/works/?view=editions";
  const editions = useAdminData<CollectionPage<WorkLibraryRow>>(
    work ? `${base}&work_id=${encodeURIComponent(work)}&page=${page}` : null,
  );
  const listed = editions.data?.results.find(row => row.id === value);
  const selected = useAdminData<CollectionPage<WorkLibraryRow>>(
    value && !listed ? `${base}&edition_id=${encodeURIComponent(value)}` : null,
  );
  const chosen = listed || selected.data?.results.find(row => row.id === value);
  return <section className="timeline-evidence-fields" aria-label="事件涉及的出版版本">

    <ErrorNotice message={editions.error || selected.error} retry={() => { editions.refresh(); selected.refresh(); }} />
    <label><span>版本</span><select data-stl-select name="subject_edition" value={value}
      disabled={Boolean(work && editions.loading)} onChange={event => onChange(event.target.value)}>
      <option value="">版本未明确</option>
      {value && !listed ? <option value={value}>{chosen?.label || (selected.error ? "已保存版本，暂无法读取" : "已保存版本，正在核对")}</option> : null}
      {editions.data?.results.map(row => <option key={row.id} value={row.id}>{row.label || row.title || "出版信息待补"}{row.is_primary ? "（主版本）" : ""}</option>)}
    </select></label>

    {work && (editions.data?.next || editions.data?.previous) ? <nav aria-label="事件出版版本分页">
      <span>{editions.data ? `共 ${editions.data.count} 个版本，第 ${page} 页` : "正在读取版本…"}</span>
      <button type="button" disabled={editions.loading || !editions.data?.previous} onClick={() => setPage(current => current - 1)}>上一页事件版本</button>
      <button type="button" disabled={editions.loading || !editions.data?.next} onClick={() => setPage(current => current + 1)}>下一页事件版本</button>
    </nav> : null}
  </section>;
}

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
  return <section data-content-section className="timeline-evidence-fields timeline-file-picker" aria-label="馆藏出处">
    <header data-section-heading>证据文件与原文定位{draft.evidence_asset?" · 已关联":""}</header>
    <p>有馆内 PDF 时，选择出处文献、出版版本和阅读文件。出处可以不是上方关联的作品；没有 PDF 也可以只保存文字来源。不选文件时，请把出处书目写在上方“来源”中。</p>
    <EntityPicker label="出处馆藏" endpoint="/catalog/admin/library/works/" queryParam="q" nameField="title" placeholder="搜索馆内出处文献…" values={onePickerValue(draft.source_work, workName)} onChange={(values) => {
      onLabels(values);
      const picked = values.at(-1)?.id ?? "";
      if (picked !== draft.source_work) { setPage(1); changeSource({ source_work: picked, source_edition: "", evidence_asset: "" }); }
    }} />
    {draft.source_work ? <>
      <ErrorNotice message={editions.error || selected.error} retry={() => { editions.refresh(); selected.refresh(); }} />
      <label><span>出处出版版本</span><select data-stl-select name="evidence_edition" value={draft.source_edition} disabled={editions.loading} onChange={(event) => changeSource({ source_edition: event.target.value, evidence_asset: "" })}>
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
        <label><span>出处阅读文件</span><select data-stl-select name="evidence_asset" value={draft.evidence_asset} disabled={!edition || Boolean(editions.error || selected.error)} onChange={(event) => changeSource({ evidence_asset: event.target.value })}>
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

    </div>
    <p id="timeline-page-help">PDF 页序从文件第一页算起，用于阅读定位；印刷页码是书页上标注的页码，可以不同。{file || savedFile ? `所选文件共 ${file?.page_count ?? savedFile?.page_count} 页。` : "选择文件后可生成阅读链接。"}</p>
    {file || savedFile ? <p className="timeline-source-file">{file?.original_filename || savedFile?.filename} · 文件版本 {file?.version ?? savedFile?.version}</p> : null}
    {notice ? <p role="status">{notice}</p> : null}
    {savedPageMatches ? <p>{savedFile.detail}{savedFile.reader_href ? <> <Link href={savedFile.reader_href} target="_blank" rel="noopener noreferrer">打开已保存的出处页</Link></> : null}</p> : draft.evidence_asset ? <p>保存事件后可检查阅读链接。文件仍需单独发布。</p> : null}
  </section>;
}

export function NormalizedTimelineAdmin() {
  const account = useEditorAccountKey();
  const search = useSearchParams();
  return <TimelineEditor key={`${account}:${search.get("node") || "all"}:${search.get("event") || "list"}`} nodeId={search.get("node") || ""} requestedId={search.get("event") || ""} />;
}

function timelineConfirmationKey(value:TimelineDraft) {
  const content=Object.fromEntries(Object.entries(value).filter(([name])=>!["review_status","display_order","confidence","editorial_details"].includes(name)));
  const {editorial_details}=value;
  return JSON.stringify({...content,sources:editorial_details.sources,primary_kind:editorial_details.primary_kind,primary_image_rendition_id:editorial_details.primary_image_rendition_id,time_note:editorial_details.time_note,conflict_note:editorial_details.conflict_note});
}

export type TimelineEditorGuard = {dirty:boolean;pending:boolean;composing:boolean};
type ScholarTimelineContext = {scholarId:string;onSelect:(id:string)=>void;onGuardChange:(value:TimelineEditorGuard)=>void;onSaved:()=>void};
export function ScholarTimelineEditor({scholarId,eventId,onGuardChange,onSaved}:{scholarId:string;eventId:string;onGuardChange:(value:TimelineEditorGuard)=>void;onSaved:()=>void}) {
  const account=useEditorAccountKey(),[selected,setSelected]=useState(eventId);
  return <TimelineEditor key={`${account}:${selected}`} requestedId={selected} embedded={{scholarId,onSelect:setSelected,onGuardChange,onSaved}}/>;
}

function TimelineEditor({ requestedId, nodeId = "", embedded }: { requestedId: string; nodeId?: string; embedded?:ScholarTimelineContext }) {
  const session=useAdminSession(), owner=String(session?.id||"");
  const command=useScholarSave(owner,"timeline");
  const composing=useRef(false),[ime,setIme]=useState(false);
  const scopeScholarId=embedded?.scholarId||"";
  const [mergeTarget,setMergeTarget]=useState(""),[mergeBusy,setMergeBusy]=useState(false);
  const canEdit=hasAdminCapability(session,"can_edit_draft_authority");
  const canCreate=hasAdminCapability(session,"can_create_authority");
  const previewRef=useRef<HTMLElement>(null);
  const panelId=useId(), [mobilePanel,setMobilePanel]=useState<"edit"|"sources"|"preview">("edit");
  const invalidFocus=useRef<HTMLInputElement|HTMLTextAreaElement|HTMLSelectElement|null>(null);
  function showPreview() {
    if (composing.current) return;
    setMobilePanel("preview");
    window.requestAnimationFrame(()=>{previewRef.current?.focus({preventScroll:true});previewRef.current?.scrollIntoView({block:"start"});});
  }
  function revealInvalid(event: FormEvent<HTMLFormElement>) {
    const field=event.target;
    if (!(field instanceof HTMLElement) || !event.currentTarget.contains(field)) return;
    if (!(field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement || field instanceof HTMLSelectElement) || field.checkVisibility()) return;
    event.preventDefault();
    if (invalidFocus.current) return;
    invalidFocus.current=field;
    const panel=field.closest<HTMLElement>("[data-timeline-panel]")?.dataset.timelinePanel;
    if(panel==="edit"||panel==="sources")setMobilePanel(panel);
    let parent=field.parentElement;
    while(parent && parent!==event.currentTarget){if(parent instanceof HTMLDetailsElement)parent.open=true;parent=parent.parentElement;}
    window.requestAnimationFrame(()=>{invalidFocus.current=null;if(field.isConnected){if(!field.checkVisibility()){setMessage("有未完成的必填项，请展开对应栏目后继续填写。");setMessageState("error");return;}field.focus();field.reportValidity();}});
  }
  const opened = useRef(false);
  const apiRequest = useEditorRequest();
  const routeLocation = useEditorListLocation();
  const location=embedded?{...routeLocation,search:new URLSearchParams(),update:(updates:Record<string,string|number|null>)=>{if("event" in updates)embedded.onSelect(String(updates.event||""));}}:routeLocation;
  const page = adminPageNumber(location.search.get("page"));
  const [editConflict, setEditConflict] = useState(false);
  const canPublish = hasAdminCapability(useAdminSession(), "can_publish_authority");
  const [editing, setEditing] = useState<TimelineEvent | null>(null);
  const initialDraft = useMemo(() => ({ ...emptyTimelineDraft, nodes: nodeId ? [nodeId] : [], scholar:scopeScholarId }), [nodeId,scopeScholarId]);
  const [draft, setSavedDraft] = useState<TimelineDraft>(initialDraft);
  const setDraft=useCallback((next:SetStateAction<TimelineDraft>)=>setSavedDraft(previous=>{const value=typeof next === "function"?next(previous):next;return timelineConfirmationKey(previous)===timelineConfirmationKey(value)?value:{...value,editorial_details:{...value.editorial_details,confirmed:false}};}),[setSavedDraft]);
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
  useUnsavedForm(Boolean(command.recovery)||Boolean(pendingAction),false);
  const notifyGuard=useEffectEvent((value:TimelineEditorGuard)=>embedded?.onGuardChange(value));
  useEffect(()=>{notifyGuard({dirty:timelineDirty,pending:Boolean(pendingAction)||Boolean(command.recovery)||mergeBusy,composing:ime});},[timelineDirty,pendingAction,command.recovery,ime,mergeBusy]);
  const [entityLabels, setEntityLabels] = useState<Record<string, string>>({});

  const params = useMemo(() => {
    const search = new URLSearchParams();
    search.set("page", String(page));
    if (nodeId) search.set("node", nodeId);
    if (scopeScholarId) search.set("scholar",scopeScholarId);
    if (disciplineFilter) search.set("discipline", disciplineFilter);
    if (typeFilter) search.set("event_type", typeFilter);
    if (statusFilter) search.set("review_status", statusFilter);
    if (appliedQuery.trim()) search.set("q", appliedQuery.trim());
    return search.toString();
  }, [disciplineFilter, typeFilter, statusFilter, appliedQuery, page, nodeId, scopeScholarId]);
  const selectedNode = useAdminData<KnowledgeNode>(nodeId ? `/catalog/admin/theory-system/nodes/${nodeId}/` : null);
  const events = useAdminData<Page<TimelineEvent>>(nodeId && !selectedNode.data ? null : `/catalog/admin/theory-timeline/?${params}`);
  const nodes = useAdminData<Page<KnowledgeNode>>("/catalog/admin/theory-system/nodes/");
  const disciplines = useAdminData<Page<Discipline>>("/catalog/admin/disciplines/");
  const works = useAdminData<Page<WorkCompact>>("/catalog/works/");
  const scholars = useAdminData<Page<ScholarCompact>>("/catalog/admin/scholars/");
  const relatedPreview=useAdminData<Page<import("@/lib/api/knowledge.types").NormalizedTimelineEvent>>(draft.scholar||nodeId?`/catalog/theory-system/timeline/?${new URLSearchParams(draft.scholar?{author:draft.scholar}:{node:nodeId})}`:null);
  const subjectWork=useAdminData<WorkFilesState>(draft.work?workFilesPath(draft.work,draft.subject_edition):null);
  const previewScholar=useAdminData<{preferred_name:string;portrait:string;birth_year:number|null;death_year:number|null;summary:string}>(draft.scholar?`/catalog/admin/scholars/${draft.scholar}/`:null);
  const requested = useAdminData<TimelineEvent>(requestedId ? `/catalog/admin/theory-timeline/${requestedId}/${embedded?`?scholar=${encodeURIComponent(embedded.scholarId)}`:""}` : null);
  const wrongNode = Boolean(nodeId && requested.data && !requested.data.relations.some((row) => row.node === nodeId));
  useEffect(() => {
    if (!requested.data || wrongNode || opened.current) return;
    const selected=requested.data;
    const timer=window.setTimeout(()=>{opened.current=true;setEditing(selected);setSavedDraft(timelineToDraft(selected));},0);
    return()=>window.clearTimeout(timer);
  }, [requested.data, wrongNode]);

  async function start(event?: TimelineEvent) {
    if (composing.current || mergeBusy || pendingAction || command.recovery || (timelineDirty && !(await confirmAction("当前输入尚未保存，放弃这些输入并打开另一个事件吗？")))) return;
    if ((event?.id || "") !== requestedId) { location.update({ event: event?.id ?? null }); return; }
    setEditing(event ?? null);
    setSavedDraft(event ? timelineToDraft(event) : { ...initialDraft });
    setMessage("");
    setMessageState("idle");
    setEntityLabels({});
    setEditConflict(false);
  }

  async function saveEvent(event: FormEvent) {
    event.preventDefault();event.stopPropagation();
    if (composing.current || mergeBusy || editing?.merged_into || !canEdit || (!editing && !canCreate) || wrongNode || (nodeId && !selectedNode.data)) return;
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = editing ? `save-timeline-event:${editing.id}` : "create-timeline-event";
    if (!startAction(actionKey)) return;
    setMessage(editing ? "正在保存时间轴事件……" : "正在创建时间轴事件……");
    setMessageState("pending");
    const relations: TimelineRelation[] = [
      ...draft.nodes.map((node, index) => ({ relation_type: "subject", node, discipline: null, scholar: null, work: null, evidence: null, description: "", ...editing?.relations.find((row) => row.node === node), sort_order: index })),
      ...draft.disciplines.map((discipline, index) => ({ relation_type: "context", node: null, discipline, scholar: null, work: null, evidence: null, description: "", ...editing?.relations.find((row) => row.discipline === discipline), sort_order: draft.nodes.length + index })),
      ...draft.participants.map((row,index)=>({...row,sort_order:draft.nodes.length+draft.disciplines.length+index})),
      ...(editing?.relations.filter((row) => !row.node && !row.discipline && !row.scholar) ?? []),
    ];
    const payload = {
      editorial_details: draft.editorial_details,
      start_date: draft.start_date||null, end_date:draft.end_date||null,
      title: draft.title,
      description: draft.description,
      event_type: draft.event_type,
      start_year: draft.start_year ? Number(draft.start_year) : null,
      end_year: draft.end_year ? Number(draft.end_year) : null,
      date_label: draft.date_label,
      date_precision: draft.date_precision,
      subject_edition: draft.subject_edition || null,
      // Placement is not edited by this form. Keep it when changing text.
      orientation: editing?.orientation ?? "neutral",
      source: draft.source,
      evidence_asset: draft.evidence_asset || null,
      evidence_work_id: draft.source_work || null,
      evidence_edition_id: draft.source_edition || null,
      evidence_page: draft.evidence_page ? Number(draft.evidence_page) : null,
      evidence_printed_label: draft.evidence_printed_label,
      evidence_text: draft.evidence_text,
      confidence: draft.confidence,
      review_status: draft.review_status,
      display_order: draft.display_order,
      discipline: editing?.discipline ?? null,
      theory_school: editing?.theory_school ?? null,
      subdiscipline: editing?.subdiscipline ?? null,
      scholar: draft.scholar || null,
      work: draft.work || null,
      relations,
    };
    try {
      const saved = await command.save<TimelineEvent>(`/catalog/admin/theory-timeline/${editing ? `${editing.id}/` : ""}`, JSON.stringify(payload), editing ? editorialHeaders(editing) : {}, editing ? "PATCH" : "POST");
      setEditing(saved);
      setSavedDraft(timelineToDraft(saved));
      setMessage(saved.editorial_revision ? "修改已保存，尚未公开。核对事件预览后，再确认发布。" : "事件已保存，尚未公开。选择准备公开并保存后，可确认发布。");
      setEditConflict(false);
      setMessageState("success");
      events.refresh();embedded?.onSaved();
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
    if (composing.current || !revision || command.recovery || timelineDirty || !canPublish || !(await confirmAction("确认发布此事件的已保存修改？公开时间线和关联页面会使用这些内容。"))) return;
    if (!startAction("publish-timeline")) return;
    try {
      await apiRequest(revision.publish_url, { method: "POST", body: "{}" }, getServerSessionCredential());
      const saved = await apiRequest<TimelineEvent>(`/catalog/admin/theory-timeline/${editing!.id}/`, {}, getServerSessionCredential());
      setEditing(saved);
      setSavedDraft(timelineToDraft(saved));
      setMessage(saved.review_status === "approved" ? "事件修改已发布。相关搜索的后台更新可能尚未完成。" : "事件已下线，公开时间线不再展示。后台更新可能尚未完成。");
      setMessageState("success");
      events.refresh();embedded?.onSaved();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "发布失败，可重试同一份已保存修改。");
      setMessageState("error");
    } finally { finishAction("publish-timeline"); }
  }

  async function removeEvent() {
    if (composing.current || !editing || command.recovery || timelineDirty || !(await confirmAction(`删除“${editing.title}”吗？`))) return;
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
      events.refresh();embedded?.onSaved();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "删除失败");
      setMessageState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  async function recoverSave(cancel=false) {
    if(composing.current||pendingAction)return;
    try { const receipt=await command.lookup(cancel); if(!receipt)return;
    if(receipt.exists && receipt.timeline_id) { location.update({event:receipt.timeline_id}); if(receipt.timeline_id===requestedId) { const saved=await apiRequest<TimelineEvent>(`/catalog/admin/theory-timeline/${receipt.timeline_id}/`);setEditing(saved);setSavedDraft(timelineToDraft(saved)); } }
    setMessage(receipt.state==="cancelled"?"原请求已停止，当前输入保留，可重新保存。":receipt.exists?"已找回原保存。请核对已保存内容。":"原保存已完成，但事件后来已删除，不会重复创建。");setMessageState("success");events.refresh();
    }catch(reason){setMessage(reason instanceof Error?reason.message:"原保存已完成，但当前详情暂未读到，请重新打开原事件。");setMessageState("error");}
  }

  const timelineNodeName = (id: string) => entityLabels[id] || (selectedNode.data?.id === id ? selectedNode.data.canonical_name_zh : "") || nodes.data?.results.find((item) => item.id === id)?.canonical_name_zh || editing?.relations.find((row) => row.node === id)?.node_name || "已选择理论";
  const timelineDisciplineName = (id: string) => entityLabels[id] || disciplines.data?.results.find((item) => item.id === id)?.name || editing?.relations.find((row) => row.discipline === id)?.discipline_name || "已选择学科";
  const timelineScholarName = (id: string) => scholars.data?.results.find((item) => item.id === id)?.preferred_name || entityLabels[id] || "已选择学者";
  const timelineWorkName = (id: string) => works.data?.results.find((item) => item.id === id)?.title || entityLabels[id] || "已选择馆藏";

  return (
    <div data-scholar-timeline={Boolean(embedded)} onCompositionStartCapture={()=>{composing.current=true;setIme(true);}} onCompositionEndCapture={()=>{composing.current=false;setIme(false);}}><AdminFrame eyebrow={`页面编排 › ${previewScholar.data?.preferred_name || selectedNode.data?.canonical_name_zh || "时间线"} › 时间线事件编辑`} title="时间线事件编辑" description="出版、翻译与上传时间请分别填写。">
      {!embedded?<nav aria-label="时间线返回位置"><Link href={safeAdminHref(location.search.get("returnTo"), nodeId ? `/admin/theories/${nodeId}` : "/admin/theories")}>返回{selectedNode.data?.canonical_name_zh || "理论管理"}</Link>{nodeId ? <> · <Link href="/admin/theories/timeline">查看全部理论事件</Link></> : null}</nav>:null}
      <ErrorNotice message={selectedNode.error} retry={selectedNode.refresh} />
      {nodeId && !selectedNode.data ? <p>所选理论加载失败，请刷新后再新建事件。</p> : null}
      {wrongNode ? <p role="alert">这个事件不属于当前理论。请返回事件所属理论，或从全部理论事件中查看。</p> : null}
      <section data-content-section className={timelineStyles.contextHelp}><header data-section-heading>编辑说明与关联范围</header><p>同一事件可以关联多个理论，修改会影响所有关联理论。关联学者或馆藏用于说明事件涉及谁、哪部作品，不会自动替代学者生平或主题发展内容。</p></section>
      <div className={timelineStyles.workspace}><div className="timeline-admin-grid">
        <div className={timelineStyles.toolbar}><small data-dirty={timelineDirty||!editing}>{timelineDirty||!editing?"未保存":"已保存草稿"}{editing?.editorial_revision?.updated_at?<span>上次修改：{new Date(editing.editorial_revision.updated_at).toLocaleString("zh-CN",{month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"})}</span>:null}</small><div><button className="admin-outline-button" type="button" disabled={ime} onClick={showPreview}>预览</button><button className="admin-outline-button" type="submit" form="timeline-editor-form" disabled={ime||mergeBusy||Boolean(editing?.merged_into)||!canEdit||Boolean(pendingAction)||!command.ready||Boolean(command.recovery)}>保存草稿</button><button className="button" type="button" disabled={ime||mergeBusy||Boolean(editing?.merged_into)||!canPublish||timelineDirty||Boolean(pendingAction)||Boolean(command.recovery)||!editing?.editorial_revision} onClick={()=>void publishEvent()}>发布</button></div></div>
        {command.recovery?<div role="status"><p>原保存结果尚未确认，请先核对这次请求。</p><button type="button" onClick={()=>void recoverSave()}>查询原请求</button>{command.canRetry?<button type="submit" form="timeline-editor-form">重试原保存</button>:null}<button type="button" onClick={()=>void recoverSave(true)}>停止未完成请求</button></div>:null}{command.error?<p role="alert">{command.error}</p>:null}
        <details data-disclosure="collection" hidden={Boolean(embedded)} className={timelineStyles.directory}><summary>查找与切换事件 · {events.data?.count ?? "正在读取"}</summary>
        <section className="admin-panel normalized-timeline-list">
          <form className="theory-admin-filters timeline" onSubmit={(event) => { event.preventDefault(); location.update({ q: query.trim(), page: 1 }); }}>
            <ResearchEntityPicker label="学科筛选" endpoint="/catalog/admin/disciplines/" entityType="discipline" step="maintenance_theory_timeline" field="filter_discipline" values={onePickerValue(disciplineFilter, timelineDisciplineName(disciplineFilter))} onChange={(next) => { const picked = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDisciplineFilter(picked?.id ?? ""); }} />
            <label><span>事件类型</span><select data-stl-select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}><option value="">全部</option>{timelineTypes.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
            <label><span>当前公开状态</span><select data-stl-select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">全部</option><option value="suggested">待核对</option><option value="approved">已公开</option><option value="rejected">不采用或已下线</option></select></label>
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
        </section></details>

        <nav className={timelineStyles.mobileTabs} aria-label="时间线编辑栏目">{([["edit","编辑内容"],["sources","出处与证据"],["preview","时间线预览"]] as const).map(([key,label])=><button key={key} type="button" disabled={ime} aria-pressed={mobilePanel===key} aria-controls={`${panelId}-${key}`} onClick={()=>setMobilePanel(key)}>{label}</button>)}</nav>
        {editing?.merged_into?<p role="status">此事件已合并，原记录及历史保留。<Link href={`/admin/theories/timeline?event=${editing.merged_into}`}>打开保留事件</Link>，或从合并记录核对回退。</p>:null}
        {editing?<TimelineMergeWorkspace key={`${owner}:${editing.id}`} owner={owner} eventId={editing.id} targetId={mergeTarget} onTargetChange={setMergeTarget} onPendingChange={setMergeBusy} disabled={timelineDirty||Boolean(pendingAction)||Boolean(command.recovery)||ime} onChanged={()=>{opened.current=false;requested.refresh();events.refresh();relatedPreview.refresh();embedded?.onSaved();}}/>:null}
        <div className="timeline-focused-editor" data-mobile-panel={mobilePanel}><form id="timeline-editor-form" className="admin-panel timeline-event-editor" onSubmit={saveEvent} onInvalidCapture={revealInvalid}>
          <ErrorNotice message={requested.error} retry={requested.refresh} />
          {requestedId && !requested.data ? <LoadingState>正在读取所选事件。</LoadingState> : null}
          <fieldset className="dedicated-editor-fields" disabled={mergeBusy || Boolean(editing?.merged_into) || !canEdit || (!editing && !canCreate) || !command.ready || Boolean(command.recovery) || Boolean(pendingAction) || Boolean(requestedId && !requested.data) || wrongNode || Boolean(nodeId && !selectedNode.data)}>
          <header className={timelineStyles.eventManagement}><section data-content-section><header data-section-heading>事件管理</header><div><h2>{editing ? "编辑事件" : "新建事件"}</h2><p>标题、时间、说明、关联理论和来源会用于公开时间线。证据原文用于复核；有有效阅读文件和页码时，读者可打开馆藏出处。</p></div>{editing ? <ActionButton type="button" state={pendingAction === `delete-timeline-event:${editing.id}` ? "pending" : "idle"} pendingLabel="删除中" disabled={Boolean(pendingAction) && pendingAction !== `delete-timeline-event:${editing.id}`} onClick={() => void removeEvent()}><Trash2 size={14} />删除</ActionButton> : null}</section></header>
          <section id={`${panelId}-edit`} data-timeline-panel="edit" className={timelineStyles.column}><section data-content-section className={timelineStyles.group}><header data-section-heading><h2>基本信息</h2></header>
          <label><span>事件类型</span><select data-stl-select value={draft.event_type} onChange={event=>setDraft({...draft,event_type:event.target.value})}>{timelineTypes.map(([value,label])=><option value={value} key={value}>{label}</option>)}</select><small>请选择最符合的事件类型，以保证时间线的准确性。</small></label>
          <div className={timelineStyles.dateFields}><div><span>日期或时间区间</span><div className={timelineStyles.dateRange}>
          {draft.date_precision==="day"||draft.date_precision==="month"?<><input aria-label="开始日期" required type={draft.date_precision==="month"?"month":"date"} value={draft.date_precision==="month"?draft.start_date.slice(0,7):draft.start_date} onChange={event=>{const value=event.target.value;setDraft({...draft,start_date:value?(draft.date_precision==="month"?`${value}-01`:value):"",start_year:value.slice(0,4),editorial_details:{...draft.editorial_details,confirmed:false}});}}/><span>–</span><input aria-label="结束日期，可留空" type={draft.date_precision==="month"?"month":"date"} value={draft.date_precision==="month"?draft.end_date.slice(0,7):draft.end_date} onChange={event=>{const value=event.target.value;setDraft({...draft,end_date:value?(draft.date_precision==="month"?`${value}-01`:value):"",end_year:value.slice(0,4),editorial_details:{...draft.editorial_details,confirmed:false}});}}/></>:<><input aria-label="开始年份" type="number" value={draft.start_year} onChange={event=>setDraft({...draft,start_year:event.target.value})}/>{draft.date_precision==="range"||draft.date_precision==="approximate"||draft.end_year?<><span>–</span><input aria-label="结束年份" type="number" value={draft.end_year} onChange={event=>setDraft({...draft,end_year:event.target.value})}/></>:null}</>}
          </div></div><label><span>精度</span><select data-stl-select name="date_precision" value={draft.date_precision} onChange={event=>setDraft({...draft,start_date:"",end_date:"",date_precision:event.target.value as TimelineDraft["date_precision"],editorial_details:{...draft.editorial_details,confirmed:false}})}><option value="unknown">未明确</option><option value="year">年份</option><option value="month">月份</option><option value="day">日期</option><option value="approximate">约略年份</option><option value="range">年份区间</option></select></label></div>
          <section data-content-section className={timelineStyles.extraFields}><header data-section-heading>时间说明与显示时期</header><label>时间说明<textarea rows={2} maxLength={2000} value={draft.editorial_details.time_note} onChange={event=>setDraft({...draft,editorial_details:{...draft.editorial_details,time_note:event.target.value,confirmed:false}})}/></label><label>显示时期<input value={draft.date_label} onChange={event=>setDraft({...draft,date_label:event.target.value})}/></label><p>时间不确定时，请填写区间并说明依据。</p></section>
          </section><section data-content-section className={timelineStyles.group}><header data-section-heading><h2>关联内容</h2></header>
          {draft.work?<><div className={timelineStyles.workLabel}>关联作品</div>{subjectWork.data?.work.id===draft.work?<TimelineWorkCard data={subjectWork.data} editionId={draft.subject_edition}/>:<p>{subjectWork.loading?"正在读取关联作品…":"关联作品资料暂未读回。"}</p>}<ErrorNotice message={subjectWork.error} retry={subjectWork.refresh}/></>:null}
          <details data-disclosure="collection" className={timelineStyles.workPicker} open={!draft.work}><summary>{draft.work?"更换关联作品":"选择关联作品"}</summary>
          <ResearchEntityPicker label="关联作品" endpoint="/catalog/admin/library/works/" entityType="work" step="maintenance_theory_timeline" field="work" values={onePickerValue(draft.work, timelineWorkName(draft.work))} onChange={(next) => { const picked = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft(current => ({ ...current, work: picked?.id ?? "", subject_edition: current.work === (picked?.id ?? "") ? current.subject_edition : "" })); }} />
          </details>
          <TimelineSubjectEdition key={`${editing?.id || "new"}:${draft.work}`} work={draft.work} value={draft.subject_edition} onChange={subject_edition => setDraft(current => ({ ...current, subject_edition }))} />
          <ResearchEntityPicker label="关联人物" endpoint="/catalog/admin/scholars/" entityType="person" step="maintenance_theory_timeline" field="scholar" values={onePickerValue(draft.scholar, timelineScholarName(draft.scholar))} onChange={(next) => { const picked = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, scholar: picked?.id ?? "" }); }} />
          <ResearchEntityPicker label="关联概念" endpoint="/catalog/admin/theory-system/nodes/" entityType="knowledge_node" step="maintenance_theory_timeline" field="nodes" multiple values={manyPickerValues(draft.nodes, timelineNodeName)} onChange={(next) => { setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, nodes: next.flatMap((value) => value.id ? [value.id] : []) }); }} />
          <section data-content-section className={timelineStyles.extraFields}><header data-section-heading>事件标题</header><label>事件标题<input required value={draft.title} onChange={event=>setDraft({...draft,title:event.target.value})}/></label></section>
          <label><span>事件描述</span><textarea rows={4} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
          <section data-content-section className={timelineStyles.extraFields}><header data-section-heading>学科与参与关系</header>
          <ResearchEntityPicker label="关联学科，可多选" endpoint="/catalog/admin/disciplines/" entityType="discipline" step="maintenance_theory_timeline" field="disciplines" multiple values={manyPickerValues(draft.disciplines, timelineDisciplineName)} onChange={(next) => { setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, disciplines: next.flatMap((value) => value.id ? [value.id] : []) }); }} />
          <TimelineParticipants owner={owner} editionId={draft.subject_edition} value={draft.participants} onChange={participants=>setDraft({...draft,participants})}/>
          </section>
          <TimelineSimilarCheck owner={owner} onMerge={setMergeTarget} mergeDisabled={!editing||timelineDirty||Boolean(pendingAction)||Boolean(command.recovery)||ime} input={{title:draft.title,event_type:draft.event_type,start_year:draft.start_year?Number(draft.start_year):null,work:draft.work||null,scholar:draft.scholar||null,exclude:editing?.id||null}} reason={draft.editorial_details.duplicate_reason} onReason={value=>setDraft({...draft,editorial_details:{...draft.editorial_details,duplicate_reason:value}})}/>
          </section></section><section id={`${panelId}-sources`} data-timeline-panel="sources" className={timelineStyles.column}><section data-content-section className={timelineStyles.group}><header data-section-heading><h2>出处与证据</h2></header>
          <label><span>来源类型</span><select data-stl-select value={draft.editorial_details.primary_kind||"other"} onChange={event=>setDraft({...draft,editorial_details:{...draft.editorial_details,primary_kind:event.target.value as NonNullable<TimelineEditorialDetails["primary_kind"]>,confirmed:false}})}><option value="other">其他或待标注</option><option value="book">图书</option><option value="article">论文</option><option value="archive">档案</option></select></label><label><span>书目信息</span><textarea rows={2} maxLength={1000} value={draft.source} onChange={event=>setDraft({...draft,source:event.target.value})} placeholder="填写实际书目、论文或档案来源"/></label><label><span>引用位置</span><input name="evidence_printed_label" maxLength={240} value={draft.evidence_printed_label} onChange={event=>setDraft({...draft,evidence_printed_label:event.target.value})}/></label>
          <TimelineEvidenceFields draft={draft} saved={editing} workName={entityLabels[draft.source_work] || editing?.evidence_file?.work_title || "已选择出处馆藏"} onLabels={(values) => setEntityLabels((current) => ({ ...current, ...pickerLabels(values) }))} onChange={(patch) => setDraft((current) => ({ ...current, ...patch }))} />
          <label><span>原文摘录</span><textarea rows={4} value={draft.evidence_text} onChange={(event) => setDraft({ ...draft, evidence_text: event.target.value })} /></label>
          <TimelineEvidenceImage key={`${owner}:${editing?.id || "new"}`} owner={owner} primary value={draft.editorial_details.primary_image_rendition_id} onChange={primary_image_rendition_id=>setDraft({...draft,editorial_details:{...draft.editorial_details,primary_image_rendition_id,confirmed:false}})}/>
          <TimelineSupplementalSources owner={owner} value={draft.editorial_details} onChange={editorial_details=>setDraft({...draft,editorial_details})}/>
          </section><section data-content-section className={timelineStyles.group}><header data-section-heading><h2>人工确认与发布状态</h2></header><span className={timelineStyles.confirmationLabel}>人工确认来源</span><div className={timelineStyles.confirmationChoices}>{[false,true].map(confirmed=><label key={String(confirmed)}><input type="radio" name={`${panelId}-confirmed`} checked={draft.editorial_details.confirmed===confirmed} onChange={()=>setDraft({...draft,editorial_details:{...draft.editorial_details,confirmed}})}/>{confirmed?"已核实":"待核实"}</label>)}</div><p>仅确认上述证据是否准确，不代表作品的学术评价。</p><p className={timelineStyles.publicationState}>发布状态 <span>{editing?.review_status==="approved"?editing.editorial_revision?"公开版有新草稿":"已公开":"草稿未发布"}</span></p><section data-content-section className={timelineStyles.extraFields}><header data-section-heading>编辑备注与发布安排</header><label>内部编辑备注<textarea rows={2} maxLength={2000} value={draft.editorial_details.editor_note} onChange={event=>setDraft({...draft,editorial_details:{...draft.editorial_details,editor_note:event.target.value}})}/></label>
          <div className="inline-fields"><label><span>保存后的安排</span><select data-stl-select value={draft.review_status} onChange={(event) => setDraft({ ...draft, review_status: event.target.value })}><option value="suggested">留待核对</option><option value="approved" disabled={!canPublish && editing?.review_status !== "approved"}>准备公开</option><option value="rejected">不采用或准备下线</option></select></label><label><span>排序</span><input type="number" value={draft.display_order} onChange={(event) => setDraft({ ...draft, display_order: Number(event.target.value) })} /></label></div>
          <ActionButton className="button" type="submit" state={pendingAction?.startsWith("save-timeline-event:") || pendingAction === "create-timeline-event" ? "pending" : "idle"} pendingLabel="正在保存事件" disabled={Boolean(pendingAction)}><Save size={15} />保存事件</ActionButton></section>
          </section></section></fieldset>
          <SavedDraftActions revision={editing?.editorial_revision} dirty={timelineDirty} busy={Boolean(pendingAction)} impact="请核对上方的事件预览与关联对象。确认发布后，公开时间线和关联页面会更新。" publish={() => void publishEvent()} />
          <EditorialConflictHelp visible={!embedded&&editConflict} href={location.href({ event: editing?.id ?? null })} />
          {embedded&&editConflict&&editing&&!command.recovery?<button type="button" disabled={Boolean(pendingAction)||ime} onClick={async ()=>{if((await confirmAction("放弃当前未保存输入并重新读取事件？")))void apiRequest<TimelineEvent>(`/catalog/admin/theory-timeline/${editing.id}/`).then(value=>{setEditing(value);setSavedDraft(timelineToDraft(value));setEditConflict(false);},reason=>setMessage(reason instanceof Error?reason.message:"重新读取失败，输入保留。"));}}>重新读取已保存事件</button>:null}
          {message ? <AsyncStatus state={messageState} message={message} /> : null}
        </form><aside id={`${panelId}-preview`} data-timeline-panel="preview" ref={previewRef} className="timeline-current-preview" tabIndex={-1}><header><strong>在时间线中的预览</strong><Link href={`/theories/timeline?${new URLSearchParams(draft.scholar?{author:draft.scholar}:nodeId?{node:nodeId}:{})}`} target="_blank">查看完整时间线 →</Link></header>{previewScholar.data?<div className={timelineStyles.scholar}>{previewScholar.data.portrait?<img src={normalizePublicResourceUrl(previewScholar.data.portrait)} alt=""/>:null}<div><h3>{previewScholar.data.preferred_name}</h3><p>{previewScholar.data.birth_year??"生年待核"} — {previewScholar.data.death_year??""}</p><p>{previewScholar.data.summary}</p></div></div>:null}<ErrorNotice message={previewScholar.error} retry={previewScholar.refresh}/><h3>时间线（节选）</h3>{draft.title||relatedPreview.data?.results.length?<TheoryTimelinePublicList detailLinks={false} currentEventId={editing?.id||"draft"} events={[...(relatedPreview.data?.results||[]).filter(row=>row.id!==editing?.id).slice(0,5),{id:editing?.id || "draft",start_date:draft.start_date||null,end_date:draft.end_date||null,title:draft.title,description:draft.description,event_type:draft.event_type,start_year:draft.start_year === "" ? null : Number(draft.start_year),end_year:draft.end_year === "" ? null : Number(draft.end_year),date_label:draft.date_label,date_precision:draft.date_precision,source:draft.source,evidence_page:Number(draft.evidence_page)||null,evidence_printed_label:draft.evidence_printed_label,evidence_text:draft.evidence_text,relations:draft.nodes.map(id=>({relation_type:"subject",type:"node",id,name:timelineNodeName(id)})),reader_href:null}].sort((a,b)=>(a.start_year??Number.POSITIVE_INFINITY)-(b.start_year??Number.POSITIVE_INFINITY))}/>:<p>填写事件与关联内容后，预览其在时间线中的位置。</p>}{subjectWork.data?.work.id===draft.work?<section className={timelineStyles.previewDetail}><h3>预览详情</h3><TimelineWorkCard data={subjectWork.data} editionId={draft.subject_edition} preview><p>{draft.title}</p><p>{draft.description}</p></TimelineWorkCard></section>:null}{draft.editorial_details.primary_image_rendition_id?<figure className={timelineStyles.imagePreview}><img src={timelineEvidenceImageUrl(draft.editorial_details.primary_image_rendition_id)} alt={draft.source||"主要出处展示图片"}/><figcaption>{draft.source||"主要出处展示图片"}</figcaption></figure>:null}<ErrorNotice message={relatedPreview.error} retry={relatedPreview.refresh}/>{relatedPreview.loading?<LoadingState>正在读取关联时间线…</LoadingState>:null}</aside></div>
      </div></div>
    </AdminFrame></div>
  );
}
