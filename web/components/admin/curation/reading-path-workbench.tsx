"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AdminListPages, useAdminListPage } from "@/components/admin/knowledge/list-pages";
import { ArrowDown, ArrowRight, ArrowUp, ExternalLink, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import type { ApiWork } from "@/lib/api/public-catalog";
import { loadLibraryWorkPreview } from "../knowledge/scholar-essential-works";
import { editorialHeaders, isEditorialConflict } from "@/lib/editorial-version";
import { EditorialConflictHelp } from "@/components/admin/knowledge/editorial-conflict-help";
import { useActionGuard } from "@/lib/use-action-guard";
import { ActionButton, AsyncStatus, type ActionState } from "@/components/action-feedback";
import { EmptyState, PageHeader, StatusBadge } from "@/components/admin-ui";
import { EntityPicker } from "../forms/workflow-fields";
import { asArray, asRecord, asString } from "../workflow/workflow-types";
import { CurationFieldAssistant } from "./curation-field-assistant";
import { EditorialPrefillNotice, useEditorialPrefills } from "./editorial-prefills";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { KnowledgeImagePanel } from "../media/knowledge-image-panel";
import { KnowledgeVisualEditor } from "../knowledge/knowledge-visual-editor";
import { KnowledgeObjectContextPanel } from "../knowledge/knowledge-object-context-panel";

type PathItemDraft = {
  key: string;
  id?: string;
  node: string | null;
  node_name: string;
  work: string | null;
  work_name: string;
  recommendation_reason: string;
  prerequisite: string;
  is_required: boolean;
  editorial_note: string;
};
type StageDraft = {
  key: string;
  id?: string;
  name: string;
  description: string;
  items: PathItemDraft[];
};
type ReadingPathRow = {
  id: string;
  edit_version: string;
  title: string;
  slug: string;
  introduction: string;
  learning_goal: string;
  primary_discipline: string | null;
  primary_discipline_name: string;
  audience: string;
  difficulty: string;
  estimated_reading: string;
  cover_url: string;
  status: string;
  sort_order: number;
  stages: Array<{ id: string; name: string; description: string; position: number }>;
  items: Array<Record<string, unknown>>;
  draft_stage_groups: Array<Record<string, unknown>>;
  editorial_revision: { id: string; revision: number; status: string } | null;
  updated_at: string;
};

const emptyPath = {
  title: "",
  slug: "",
  introduction: "",
  learning_goal: "",
  primary_discipline: "",
  audience: "",
  difficulty: "beginner",
  estimated_reading: "",
  status: "draft",
  sort_order: 0,
};

function key(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function emptyItem(): PathItemDraft {
  return { key: key("item"), node: null, node_name: "", work: null, work_name: "", recommendation_reason: "", prerequisite: "", is_required: false, editorial_note: "" };
}

function emptyStage(position: number): StageDraft {
  return { key: key("stage"), name: `第 ${position + 1} 阶段`, description: "", items: [emptyItem()] };
}

function normalizePath(value: unknown): ReadingPathRow {
  const row = asRecord(value);
  const primaryDiscipline = asRecord(row.primary_discipline_data);
  return {
    id: asString(row.id),
    edit_version: asString(row.edit_version),
    title: asString(row.title),
    slug: asString(row.slug),
    introduction: asString(row.introduction),
    learning_goal: asString(row.learning_goal),
    primary_discipline: asString(row.primary_discipline) || null,
    primary_discipline_name: asString(primaryDiscipline.name),
    audience: asString(row.audience),
    difficulty: asString(row.difficulty, "beginner"),
    estimated_reading: asString(row.estimated_reading),
    cover_url: asString(row.cover_url),
    status: asString(row.status, "draft"),
    sort_order: Number(row.sort_order ?? 0),
    stages: asArray(row.stages).map((entry, position) => {
      const stage = asRecord(entry);
      return { id: asString(stage.id), name: asString(stage.name, `第 ${position + 1} 阶段`), description: asString(stage.description), position: Number(stage.position ?? position) };
    }),
    items: asArray(row.items).map(asRecord),
    draft_stage_groups: asArray(row.draft_stage_groups).map(asRecord),
    editorial_revision: asString(asRecord(row.editorial_revision).id) ? {
      id: asString(asRecord(row.editorial_revision).id),
      revision: Number(asRecord(row.editorial_revision).revision ?? 0),
      status: asString(asRecord(row.editorial_revision).status),
    } : null,
    updated_at: asString(row.updated_at),
  };
}

function pathStages(path: ReadingPathRow): StageDraft[] {
  if (path.draft_stage_groups.length) {
    const canonicalItems = new Map(
      path.items.map((item) => [asString(item.id), item]),
    );
    return path.draft_stage_groups.map((entry, stageIndex) => {
      const stage = asRecord(entry);
      return {
        key: asString(stage.id, key("draft-stage")),
        id: asString(stage.id) || undefined,
        name: asString(stage.name, `第 ${stageIndex + 1} 阶段`),
        description: asString(stage.description),
        items: asArray(stage.items).map((value) => {
          const item = asRecord(value);
          const canonical = canonicalItems.get(asString(item.id)) ?? path.items.find((row) =>
            (item.work && asString(row.work) === asString(item.work)) ||
            (item.node && asString(row.node) === asString(item.node)),
          ) ?? {};
          const nodeData = asRecord(canonical.node_data);
          const workData = asRecord(canonical.work_data);
          return {
            key: asString(item.id, key("draft-item")),
            id: asString(item.id) || undefined,
            node: asString(item.node) || null,
            node_name: asString(nodeData.canonical_name_zh ?? nodeData.name),
            work: asString(item.work) || null,
            work_name: asString(workData.title ?? workData.name),
            recommendation_reason: asString(item.recommendation_reason),
            prerequisite: asString(item.prerequisite),
            is_required: item.is_required === true,
            editorial_note: asString(item.editorial_note),
          };
        }),
      };
    });
  }
  const stages: StageDraft[] = path.stages.map((stage) => ({ key: stage.id, id: stage.id, name: stage.name, description: stage.description, items: [] as PathItemDraft[] }));
  const byId = new Map(stages.map((stage) => [stage.id, stage]));
  path.items.forEach((item) => {
    const stageId = asString(item.stage);
    const nodeData = asRecord(item.node_data);
    const workData = asRecord(item.work_data);
    let stage = byId.get(stageId);
    if (!stage) {
      const legacyStage: StageDraft = { key: key("legacy-stage"), name: asString(item.stage_name, "未命名阶段"), description: asString(item.stage_description), items: [] };
      stages.push(legacyStage);
      stage = legacyStage;
    }
    stage.items.push({
      key: asString(item.id, key("item")),
      id: asString(item.id) || undefined,
      node: asString(item.node) || null,
      node_name: asString(nodeData.canonical_name_zh ?? nodeData.name ?? item.node_name),
      work: asString(item.work) || null,
      work_name: asString(workData.title ?? workData.name ?? item.work_title),
      recommendation_reason: asString(item.recommendation_reason),
      prerequisite: asString(item.prerequisite),
      is_required: item.is_required === true,
      editorial_note: asString(item.editorial_note),
    });
  });
  return stages.length ? stages : [emptyStage(0)];
}

export function moveReadingPathEntry<T>(values: T[], from: number, to: number) {
  if (from < 0 || from >= values.length || to < 0 || to >= values.length || from === to) return values;
  const next = [...values];
  const [value] = next.splice(from, 1);
  next.splice(to, 0, value);
  return next;
}

export function readingPathStageGroups(stages: StageDraft[]) {
  return stages.map((stage, stagePosition) => {
    stage.items.forEach((item, itemPosition) => {
      if (!item.work && !item.node && (item.recommendation_reason || item.prerequisite || item.editorial_note || item.is_required)) {
        throw new Error(`第 ${stagePosition + 1} 阶段的第 ${itemPosition + 1} 本尚未选择阅读内容，填写的说明已保留。`);
      }
    });
    return {
      id: stage.id, name: stage.name, description: stage.description, position: stagePosition,
      items: stage.items.filter(item => item.work || item.node).map((item, position) => ({
        id:item.id, node:item.node, work:item.work, recommendation_reason:item.recommendation_reason,
        prerequisite:item.prerequisite, position, is_required:item.is_required, editorial_note:item.editorial_note,
      })),
    };
  });
}

function editablePath(path?: ReadingPathRow) {
  return path ? {
    title: path.title, slug: path.slug, introduction: path.introduction,
    learning_goal: path.learning_goal, primary_discipline: path.primary_discipline ?? "",
    audience: path.audience, difficulty: path.difficulty, estimated_reading: path.estimated_reading,
    status: path.status, sort_order: path.sort_order,
  } : { ...emptyPath };
}

function pathFormValue(draft: typeof emptyPath, stages: StageDraft[]) {
  return { draft, stages: stages.map((stage) => ({ name: stage.name, description: stage.description,
    items: stage.items.map(item => ({node:item.node,node_name:item.node_name,work:item.work,work_name:item.work_name,
      recommendation_reason:item.recommendation_reason,prerequisite:item.prerequisite,is_required:item.is_required,editorial_note:item.editorial_note})),
  })) };
}

export function ReadingPathWorkbench() {
  const paging = useAdminListPage();
  const page = paging.page;
  const [collection, setCollection] = useState<{ count: number; next?: string | null; previous?: string | null } | null>(null);
  const listRequest = useRef<AbortController | null>(null);
  const [editConflict, setEditConflict] = useState(false);
  const searchParams = useSearchParams();
  const requestedPath = searchParams.get("path")?.trim() ?? "";
  const [openedPath, setOpenedPath] = useState("");
  const [paths, setPaths] = useState<ReadingPathRow[]>([]);
  const [editing, setEditing] = useState<ReadingPathRow | null>(null);
  const [draft, setDraft] = useState({ ...emptyPath });
  const [primaryDisciplineName, setPrimaryDisciplineName] = useState("");
  const [activeStage, setActiveStage] = useState(0);
  const [activeItem, setActiveItem] = useState(0);
  const [stages, setStages] = useState<StageDraft[]>([emptyStage(0)]);
  const [pickerItem, setPickerItem] = useState<string | null>(null);
  const [previewWorks, setPreviewWorks] = useState<ApiWork[]>([]);
  const [workError, setWorkError] = useState("");
  const [workRetry, setWorkRetry] = useState(0);
  const workCache = useRef(new Map<string, ApiWork | null>());
  const dragging = useRef<{ stage: string; item: string } | null>(null);
  const currentStageIndex = Math.min(activeStage, Math.max(0, stages.length - 1));
  const visibleStage = stages[currentStageIndex];
  const visibleWorkIds = [...new Set((visibleStage?.items || []).flatMap(item => item.work ? [item.work] : []))].sort().join(",");
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      let failed = "";
      for (const id of visibleWorkIds ? visibleWorkIds.split(",") : []) {
        if (controller.signal.aborted) return;
        if (workCache.current.has(id)) continue;
        try {
          const resolved = await loadLibraryWorkPreview(id, controller.signal);
          if (!controller.signal.aborted) workCache.current.set(id, resolved.work);
        } catch (error) { if (!controller.signal.aborted) failed = error instanceof Error ? error.message : "书目读取失败"; }
      }
      if (controller.signal.aborted) return;
      setPreviewWorks([...workCache.current.values()].filter((work): work is ApiWork => Boolean(work)));
      setWorkError(failed ? `${failed}。原有选择、顺序和推荐理由仍保留。` : "");
    })();
    return () => controller.abort();
  }, [visibleWorkIds, workRetry]);
  const [savedContent, setSavedContent] = useState(() => pathFormValue(emptyPath, [emptyStage(0)]));
  const dirty = useUnsavedForm(pathFormValue(draft, stages), savedContent);
  const dirtyRef = useRef(dirty);
  useEffect(() => { dirtyRef.current = dirty; }, [dirty]);
  const prefills = useEditorialPrefills(editing?.id || "new-path", { stages }, (update) => setStages((current) => (
    typeof update === "function" ? update({ stages: current }) : update
  ).stages));
  const [imageRevision, setImageRevision] = useState(0);
  const [query, setQuery] = useState(searchParams.get("q") || "");
  const [message, setMessage] = useState("");
  const [messageState, setMessageState] = useState<ActionState>("idle");
  const [loading, setLoading] = useState(true);
  const { pendingAction, startAction, finishAction } = useActionGuard();

  const loadPaths = useCallback(async () => {
    const token = getServerSessionCredential();
    if (!token) return;
    listRequest.current?.abort();
    const request = new AbortController();
    listRequest.current = request;
    setLoading(true);
    try {
      const suffix = `?page=${page}&q=${encodeURIComponent(query.trim())}`;
      const pathPage = await apiRequest<{ results?: unknown[]; count: number; next?: string | null; previous?: string | null }>(`/catalog/admin/theory-system/reading-paths/${suffix}`, { signal: request.signal }, token);
      if (request.signal.aborted) return false;
      setCollection(pathPage);
      setPaths((pathPage.results ?? []).map(normalizePath));
      return true;
    } catch (error) {
      if (request.signal.aborted) return false;
      setCollection(null); setPaths([]);
      setMessage(error instanceof Error ? error.message : "阅读路径读取失败。");
      setMessageState("error");
      return false;
    } finally {
      if (!request.signal.aborted) setLoading(false);
    }
  }, [query, page, setMessage, setMessageState]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadPaths(), 0);
    return () => { window.clearTimeout(timer); listRequest.current?.abort(); };
  }, [loadPaths]);

  useEffect(() => {
    if (!requestedPath || requestedPath === openedPath) return;
    let active = true;
    const token = getServerSessionCredential();
    if (!token) return;
    void apiRequest(
      `/catalog/admin/theory-system/reading-paths/${encodeURIComponent(requestedPath)}/`,
      {},
      token,
    ).then((payload) => {
      if (!active) return;
      if (dirtyRef.current) { setMessage("当前填写已保留，请先保存，再打开另一条阅读路径。"); return; }
      const path = normalizePath(payload);
      setEditing(path);
      setDraft({
        title: path.title,
        slug: path.slug,
        introduction: path.introduction,
        learning_goal: path.learning_goal,
        primary_discipline: path.primary_discipline ?? "",
        audience: path.audience,
        difficulty: path.difficulty,
        estimated_reading: path.estimated_reading,
        status: path.status,
        sort_order: path.sort_order,
      });
      setPrimaryDisciplineName(path.primary_discipline_name);
      setStages(pathStages(path));
      setActiveStage(0); setActiveItem(0);
      setSavedContent(pathFormValue(editablePath(path), pathStages(path)));
      setMessage("已打开当前阅读路径。");
      setMessageState("success");
      setOpenedPath(requestedPath);
    }).catch((error) => {
      if (!active) return;
      setMessage(error instanceof Error ? error.message : "阅读路径读取失败。");
      setMessageState("error");
    });
    return () => {
      active = false;
    };
  }, [requestedPath, openedPath]);

  function start(path?: ReadingPathRow, saved = false) {
    if (!saved && dirty && !window.confirm("阅读路径还有未保存的安排。放弃填写并切换吗？")) return;
    prefills.clear();
    setPickerItem(null);
    if (!saved) { setActiveStage(0); setActiveItem(0); }
    setEditing(path ?? null);
    setDraft(path ? {
      title: path.title,
      slug: path.slug,
      introduction: path.introduction,
      learning_goal: path.learning_goal,
      primary_discipline: path.primary_discipline ?? "",
      audience: path.audience,
      difficulty: path.difficulty,
      estimated_reading: path.estimated_reading,
      status: path.status,
      sort_order: path.sort_order,
    } : { ...emptyPath });
    setStages(path ? pathStages(path) : [emptyStage(0)]);
    setSavedContent(pathFormValue(editablePath(path), path ? pathStages(path) : [emptyStage(0)]));
    setPrimaryDisciplineName(path?.primary_discipline_name ?? "");
    setOpenedPath(path?.id || "");
    const url = new URL(window.location.href);
    if (path) url.searchParams.set("path", path.id); else url.searchParams.delete("path");
    if (!saved) url.searchParams.delete("section");
    window.history.replaceState(null,"",url.pathname+url.search);
    setMessage("");
    setMessageState("idle");
  }

  function patchStage(stageIndex: number, patch: Partial<StageDraft>) {
    setStages((current) => current.map((stage, index) => index === stageIndex ? { ...stage, ...patch } : stage));
  }

  function patchItem(stageIndex: number, itemIndex: number, patch: Partial<PathItemDraft>) {
    setStages((current) => current.map((stage, index) => index === stageIndex ? {
      ...stage,
      items: stage.items.map((item, position) => position === itemIndex ? { ...item, ...patch } : item),
    } : stage));
  }

  useEffect(() => {
    const choose = (event: Event) => {
      const index = Number((event as CustomEvent).detail);
      if (!Number.isInteger(index) || index < 0) return;
      const targets = stages.flatMap((stage,stageIndex) => stage.items.flatMap((item,itemIndex) => item.work || item.node ? [{stageIndex,itemIndex,key:item.key}] : []));
      const target = targets[index];
      if (!target) return;
      setActiveStage(target.stageIndex); setActiveItem(target.itemIndex);
      window.requestAnimationFrame(() => document.querySelector<HTMLTextAreaElement>(`[data-reading-item="${CSS.escape(target.key)}"] textarea`)?.focus());
    };
    window.addEventListener("knowledge-row-select", choose);
    return () => window.removeEventListener("knowledge-row-select", choose);
  }, [stages]);

  const itemCount = useMemo(() => stages.reduce((count, stage) => count + stage.items.length, 0), [stages]);

  async function save(event?: FormEvent, draftOnly = false) {
    event?.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return false;
    let stageGroups;
    try { stageGroups = readingPathStageGroups(stages); }
    catch (error) { setMessage(error instanceof Error ? error.message : "请先选择阅读内容。"); setMessageState("error"); return false; }
    if (!draftOnly && draft.status === "published" && editing?.status !== "published" && !window.confirm("保存并公开这条阅读路径？确认后读者就能看到它。")) return false;
    const actionKey = "save-reading-path";
    if (!startAction(actionKey)) return false;
    setEditConflict(false);
    setMessage("正在保存阅读路径……");
    setMessageState("pending");
    try {
      const payload = {
        ...draft,
        assisted_candidates: prefills.ids,
        assisted_candidate_decisions: prefills.decisions,
        status: draftOnly ? (editing?.status ?? "draft") : draft.status,
        primary_discipline: draft.primary_discipline || null,
        expected_updated_at: editing?.updated_at,
        stage_groups: stageGroups,
      };
      const saved = normalizePath(await apiRequest(
        `/catalog/admin/theory-system/reading-paths/${editing ? `${editing.id}/` : ""}`,
        { method: editing ? "PATCH" : "POST", headers: editing ? editorialHeaders(editing) : undefined, body: JSON.stringify(payload) },
        token,
      ));
      start(saved, true);
      setMessage(saved.editorial_revision
        ? "阅读路径的编辑草稿已保存，确认发布后更新公开页面。"
        : saved.status === "published"
          ? "阅读路径已公开。可以在预览中核对阶段顺序和作品安排。"
          : "阅读路径已保存，尚未公开。阶段顺序和作品安排已保留。");
      setMessageState("success");
      await loadPaths();
      return true;
    } catch (error) {
      setEditConflict(isEditorialConflict(error));
      setMessage(error instanceof Error ? error.message : "阅读路径保存失败。");
      setMessageState("error");
      return false;
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
      const response = asRecord(await apiRequest(`/catalog/admin/theory-system/reading-paths/${editing.id}/`, { method: "DELETE", headers: editorialHeaders(editing) }, token));
      const revision = asRecord(response.editorial_revision);
      if (asString(revision.id)) {
        setMessage("已保存撤回草稿，确认发布后从公开页面撤回。");
      } else {
        start();
        setMessage("阅读路径已删除。");
      }
      await loadPaths();
      setMessageState("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "阅读路径删除失败。");
      setMessageState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  async function refreshPaths() {
    const actionKey = "refresh-reading-paths";
    if (!startAction(actionKey)) return;
    setMessage("正在刷新阅读路径……");
    setMessageState("pending");
    try {
      const refreshed = await loadPaths();
      if (refreshed) {
        setMessage("阅读路径已刷新。");
        setMessageState("success");
      }
    } finally {
      finishAction(actionKey);
    }
  }

  return (
    <div className="admin-page reading-path-v280-page">
      <PageHeader title={editing ? `编辑阅读路径：${draft.title}` : "新建阅读路径"} description="为读者提供一条从基础到深入的阅读路线，帮助理解相关理论的核心问题、代表人物与当代意义。" />
      {message ? <div className={messageState === "success" ? "sr-only" : undefined}><AsyncStatus state={messageState} message={message}/></div> : null}
      <div className="reading-path-v280-layout">
        <details className="admin-panel reading-path-v280-list"><summary>选择已保存的路径</summary>
          <header><h2>路径</h2><button type="button" onClick={() => start()}><Plus size={14} />新建路径</button><ActionButton type="button" state={pendingAction === "refresh-reading-paths" ? "pending" : "idle"} pendingLabel="刷新中" disabled={Boolean(pendingAction) && pendingAction !== "refresh-reading-paths"} onClick={() => void refreshPaths()}><RefreshCw size={13} />刷新</ActionButton></header>
          <label><span className="sr-only">搜索阅读路径</span><input type="search" value={query} onChange={(event) => { setQuery(event.target.value); paging.reset({ q: event.target.value }); }} placeholder="搜索路径" /></label>
          {paths.map((path) => <button className={editing?.id === path.id ? "selected" : ""} type="button" key={path.id} onClick={() => start(path)}><span><strong>{path.title}</strong><small>{path.stages.length} 阶段 · {path.items.length} 项阅读内容</small></span><StatusBadge label={path.status} /><ArrowRight size={13} /></button>)}
          {!loading && !paths.length ? <EmptyState compact title="尚无阅读路径" description="建立路径后，也可以从文献的编辑页面加入阅读内容。" /> : null}
          <AdminListPages data={collection} paging={paging} loading={loading} filters={{ q: query }} />
        </details>
        <KnowledgeVisualEditor key={editing?.id || "new"} objectType="reading_path" objectId={editing?.id} savedRecord={editing} onPublished={() => {void loadPaths();setEditConflict(true);setMessage("发布操作已提交，请打开最新阅读路径后继续编辑。");}} draft={{...draft, stages, previewWorks, preview_active_stage:currentStageIndex}} dirty={dirty} refreshKey={`${editing?.updated_at}:${imageRevision}`}>{requestedPath && openedPath !== requestedPath ? <p role="status">正在读取指定阅读路径，载入后即可编辑。</p> : null}<form id="reading-path-form" className="admin-panel reading-path-v280-editor" onSubmit={(event) => void save(event, true)} aria-busy={Boolean(requestedPath && openedPath !== requestedPath)}>
          <p>保存这条路径的说明、全部阶段、书目顺序和推荐理由，不跳转。已公开路径的修改需另行发布。</p>
          <EditorialPrefillNotice state={prefills} />
          <fieldset disabled={Boolean(requestedPath && openedPath !== requestedPath) || pendingAction === "save-reading-path"} style={{ display: "contents" }}>
          <header><div><h2>{editing ? `编辑 ${editing.title}` : "新建阅读路径"}</h2><p>{stages.length} 个阶段 · {itemCount} 个项目</p></div>{editing ? <div><Link href={`/admin/preview/knowledge/reading_path/${editing.id}`} target="_blank">预览已保存内容 <ExternalLink size={12} /></Link><ActionButton type="button" state={pendingAction === `delete-reading-path:${editing.id}` ? "pending" : "idle"} disabled={Boolean(pendingAction) && pendingAction !== `delete-reading-path:${editing.id}`} aria-label="删除阅读路径" onClick={() => void removePath()}><Trash2 size={14} /></ActionButton></div> : null}</header>
          <div className="inline-fields"><label><span>标题</span><input required value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label><span>固定链接</span><input required value={draft.slug} onChange={(event) => setDraft({ ...draft, slug: event.target.value })} /></label></div>
          <label data-editor-section="identity"><span>路径介绍</span><textarea rows={4} value={draft.introduction} onChange={(event) => setDraft({ ...draft, introduction: event.target.value })} /></label>
          <label><span>学习目标</span><textarea rows={3} value={draft.learning_goal} onChange={(event) => setDraft({ ...draft, learning_goal: event.target.value })} /></label>
          <div className="inline-fields three"><EntityPicker label="主要学科" endpoint="/catalog/admin/disciplines/" queryParam="q" nameField="name" values={draft.primary_discipline ? [{ id: draft.primary_discipline, name: primaryDisciplineName || "已选择主要学科" }] : []} onChange={(next) => { const selected = next.at(-1); setDraft({ ...draft, primary_discipline: selected?.id ?? "" }); setPrimaryDisciplineName(selected?.name ?? ""); }} /><label><span>适合人群</span><input value={draft.audience} onChange={(event) => setDraft({ ...draft, audience: event.target.value })} /></label><label><span>难度</span><select value={draft.difficulty} onChange={(event) => setDraft({ ...draft, difficulty: event.target.value })}><option value="beginner">入门</option><option value="intermediate">进阶</option><option value="advanced">深入</option></select></label></div>
          <div className="inline-fields three"><label><span>预计阅读量</span><input value={draft.estimated_reading} onChange={(event) => setDraft({ ...draft, estimated_reading: event.target.value })} /></label><label><span>状态</span><select disabled title="状态通过发布或下线操作更新" value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}><option value="draft">草稿</option><option value="pending">提交审核</option><option value="published">发布</option><option value="archived">归档</option></select></label><label data-editor-section="identity"><span>路径排序</span><input type="number" value={draft.sort_order} onChange={(event) => setDraft({ ...draft, sort_order: Number(event.target.value) })} /></label></div>
          {editing ? <KnowledgeImagePanel objectType="reading_path" objectId={editing.id} refreshKey={`${editing.updated_at}:${imageRevision}`} onChanged={() => setImageRevision((value) => value + 1)} /> : <p>先保存阅读路径，再选择页面图片。</p>}
          <section className="reading-path-v280-stages" data-editor-section="paths">
            <header className="reading-path-reference-heading"><h2>{visibleStage?.name || "阅读内容"}（{visibleStage?.items.filter(item => item.work || item.node).length || 0} 本）</h2><p>选择最能代表该流派的关键著作，并说明推荐理由与阅读顺序。</p></header>
            {workError ? <p role="alert">{workError}<button type="button" onClick={() => setWorkRetry(value => value + 1)}>重试</button></p> : null}
            {stages.map((stage, stageIndex) => <div className="reading-path-v280-stage" key={stage.key} hidden={stageIndex !== Math.min(activeStage, stages.length - 1)}>
              <div className="reading-path-v280-items">{stage.items.map((item, itemIndex) => {
                const work = previewWorks.find(row => row.id === item.work);
                const savedWork = asRecord(editing?.items.find(row => row.work === item.work)?.work_data);
                const title = work?.title || item.work_name || asString(savedWork.title) || item.node_name;
                const cover = work?.cover || work?.recommendation_image;
                const authors = work?.edition?.contributors.filter(row => row.role === "author").map(row => row.person.preferred_name).join("、") || asString(savedWork.author);
                const publisher = work?.edition?.publisher || asString(savedWork.publisher);
                const year = work?.edition?.publication_year || savedWork.year;
                return <article key={item.key} data-reading-item={item.key} data-selected={itemIndex === activeItem} onFocusCapture={() => setActiveItem(itemIndex)} onDragOver={event => { if (dragging.current?.stage === stage.key) event.preventDefault(); }} onDrop={event => {
                  event.preventDefault();
                  if (dragging.current?.stage !== stage.key || event.currentTarget.closest("fieldset")?.matches(":disabled")) return;
                  const from = stage.items.findIndex(row => row.key === dragging.current?.item);
                  patchStage(stageIndex, {items:moveReadingPathEntry(stage.items, from, itemIndex)}); setActiveItem(itemIndex); dragging.current = null;
                }}>
                  <h3><button className="reading-path-order-handle" type="button" draggable aria-label={`调整第 ${itemIndex + 1} 本阅读内容顺序`} title="拖动或按上下方向键调整顺序" onDragStart={event => { dragging.current = {stage:stage.key,item:item.key}; event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain",item.key); }} onDragEnd={() => {dragging.current = null;}} onKeyDown={event => {
                    if (!["ArrowUp","ArrowDown"].includes(event.key)) return;
                    event.preventDefault(); const target = itemIndex + (event.key === "ArrowUp" ? -1 : 1);
                    patchStage(stageIndex, {items:moveReadingPathEntry(stage.items,itemIndex,target)}); if (target >= 0 && target < stage.items.length) setActiveItem(target);
                  }}>第{["一","二","三","四","五","六","七","八","九","十"][itemIndex] || itemIndex + 1}本（顺序 {itemIndex + 1}）</button></h3>
                  <div className="reading-path-reference-book"><span className="reading-path-reference-cover">{cover ? <img src={normalizePublicResourceUrl(cover)} alt={`${title}封面`}/> : null}</span><div><strong>{title ? item.work ? `《${title}》` : title : ""}</strong>{authors ? <p>{authors} 著</p> : null}<p>{[publisher,year ? `${year} 年版` : ""].filter(Boolean).join(" · ")}</p></div><button type="button" onClick={() => setPickerItem(pickerItem === item.key ? null : item.key)}>{item.work || item.node ? "更换书目" : "选择书目"}</button></div>
                  {pickerItem === item.key ? <div className="inline-fields reading-path-v292-entity-fields"><EntityPicker label="馆藏作品" endpoint="/catalog/admin/library/works/" queryParam="q" nameField="title" values={item.work ? [{id:item.work,name:item.work_name || title}] : []} onChange={next => {const selected = next.at(-1); patchItem(stageIndex,itemIndex,{work:selected?.id ?? null,work_name:selected?.name ?? "",node:null,node_name:""}); setPickerItem(null);}}/><EntityPicker label="理论或概念" endpoint="/catalog/admin/theory-system/nodes/" queryParam="q" nameField="canonical_name_zh" values={item.node ? [{id:item.node,name:item.node_name}] : []} onChange={next => {const selected = next.at(-1); patchItem(stageIndex,itemIndex,{node:selected?.id ?? null,node_name:selected?.name ?? "",work:null,work_name:""}); setPickerItem(null);}}/></div> : null}
                  <label className="reading-path-reference-reason"><span>推荐理由 <b>*</b></span><textarea aria-label={`第 ${itemIndex + 1} 本阅读内容的推荐理由`} aria-required={Boolean(item.work || item.node)} maxLength={Math.max(300,item.recommendation_reason.length)} rows={3} value={item.recommendation_reason} onChange={event => patchItem(stageIndex,itemIndex,{recommendation_reason:event.target.value})}/><small>{item.recommendation_reason.length} / 300</small></label>
                </article>;
              })}</div>
            </div>)}
            <details className="reading-path-reference-settings"><summary>其他设置</summary>
              <nav className="structured-row-index" aria-label="阅读阶段">{stages.map((stage,index) => <button key={stage.key} type="button" aria-current={index === Math.min(activeStage,stages.length - 1) ? "true" : undefined} onClick={() => {setActiveStage(index);setActiveItem(0);setPickerItem(null);}}>{index + 1} · {stage.name}</button>)}</nav>
              {visibleStage ? <><label><span>阶段名称</span><input value={visibleStage.name} onChange={event => patchStage(currentStageIndex,{name:event.target.value})}/></label><label><span>阶段说明</span><textarea rows={2} value={visibleStage.description} onChange={event => patchStage(currentStageIndex,{description:event.target.value})}/></label><div className="reading-path-reference-controls"><button type="button" disabled={currentStageIndex === 0} onClick={() => {setStages(current => moveReadingPathEntry(current,currentStageIndex,currentStageIndex - 1));setActiveStage(currentStageIndex - 1);}}><ArrowUp size={12}/>上移阶段</button><button type="button" disabled={currentStageIndex >= stages.length - 1} onClick={() => {setStages(current => moveReadingPathEntry(current,currentStageIndex,currentStageIndex + 1));setActiveStage(currentStageIndex + 1);}}><ArrowDown size={12}/>下移阶段</button><button type="button" onClick={() => {setStages(current => current.filter(row => row.key !== visibleStage.key));setActiveStage(Math.max(0,currentStageIndex - 1));setActiveItem(0);}}><Trash2 size={12}/>删除阶段</button></div>
              {visibleStage.items.map((item,index) => <div className="reading-path-reference-item-settings" key={item.key}><strong>第 {index + 1} 本 · {item.work_name || item.node_name || "未选择书目"}</strong><div className="reading-path-reference-controls"><button type="button" disabled={index === 0} onClick={() => patchStage(currentStageIndex,{items:moveReadingPathEntry(visibleStage.items,index,index - 1)})}>上移书目</button><button type="button" disabled={index === visibleStage.items.length - 1} onClick={() => patchStage(currentStageIndex,{items:moveReadingPathEntry(visibleStage.items,index,index + 1)})}>下移书目</button><button type="button" onClick={() => patchStage(currentStageIndex,{items:visibleStage.items.filter(row => row.key !== item.key)})}>移除书目</button></div><label><span>前置要求</span><textarea rows={2} value={item.prerequisite} onChange={event => patchItem(currentStageIndex,index,{prerequisite:event.target.value})}/></label><label><span>编辑备注（仅后台）</span><textarea rows={2} value={item.editorial_note} onChange={event => patchItem(currentStageIndex,index,{editorial_note:event.target.value})}/></label><label className="workflow-checkbox"><input type="checkbox" checked={item.is_required} onChange={event => patchItem(currentStageIndex,index,{is_required:event.target.checked})}/><span>设为必读</span></label></div>)}
              <button className="button secondary" type="button" onClick={() => {const item = emptyItem();setActiveItem(visibleStage.items.length);setPickerItem(item.key);patchStage(currentStageIndex,{items:[...visibleStage.items,item]});}}><Plus size={12}/>在本阶段添加阅读内容</button></> : null}
              <button type="button" onClick={() => {setActiveStage(stages.length);setActiveItem(0);setStages(current => [...current,emptyStage(current.length)]);}}><Plus size={13}/>添加阶段</button>
              <CurationFieldAssistant label="阅读内容" targetType="reading_path" targetId={editing?.id} fieldName="item" query={draft.title} currentValue={stages.flatMap(stage => stage.items.map(item => ({work_id:item.work,node_id:item.node})))} formContext={{language:"zh",learning_goal:draft.learning_goal}} lookupLabel="推荐阅读内容" onFillSuggestion={(candidateId,value,label) => {
                const row = asRecord(value),work = asString(row.work_id) || null,node = asString(row.node_id) || null;
                if (!work && !node) return false;
                return prefills.fill(candidateId,current => {
                  if (current.stages.some(stage => stage.items.some(item => item.work === work && item.node === node))) return current;
                  const name = asString(row.stage_name,"建议阅读"),item = {...emptyItem(),work,node,work_name:work ? label : "",node_name:node ? label : "",recommendation_reason:asString(row.recommendation_reason),is_required:row.is_required === true};
                  const found = current.stages.findIndex(stage => stage.name === name);
                  return {stages:found < 0 ? [...current.stages,{key:key("stage"),name,description:asString(row.stage_description),items:[item]}] : current.stages.map((stage,index) => index === found ? {...stage,items:[...stage.items.filter(entry => entry.work || entry.node),item]} : stage)};
                });
              }}/>
            </details>
          </section>
          <footer><ActionButton className="button secondary" form="reading-path-form" type="submit" state={pendingAction === "save-reading-path" ? "pending" : "idle"} pendingLabel="正在保存路径" disabled={Boolean(requestedPath && openedPath !== requestedPath) || Boolean(pendingAction) && pendingAction !== "save-reading-path"}>保存草稿</ActionButton></footer>
          <EditorialConflictHelp visible={editConflict} href={`/admin/theories/reading-paths?path=${editing?.id}`} />
          </fieldset>
        </form>
        {editing ? <KnowledgeObjectContextPanel hasUnsavedChanges={dirty} objectType="reading_path" objectId={editing.id} refreshKey={`${editing.updated_at}:${imageRevision}`} onChanged={() => { void loadPaths(); setImageRevision((value) => value + 1); setEditConflict(true); setMessage("公开内容已更新。继续修改前，请打开最新内容；本页输入仍保留。"); setMessageState("success"); }} /> : null}</KnowledgeVisualEditor>
      </div>
    </div>
  );
}
