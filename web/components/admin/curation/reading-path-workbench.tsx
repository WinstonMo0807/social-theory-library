"use client";

import { createRequestKey } from "../../../lib/request-key";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AdminListPages, useAdminListPage } from "@/components/admin/knowledge/list-pages";
import { ArrowDown, ArrowRight, ArrowUp, ExternalLink, Plus, RefreshCw, Save, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { apiRequest as baseApiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { editorialHeaders, isEditorialConflict } from "@/lib/editorial-version";
import { EditorialConflictHelp } from "@/components/admin/knowledge/editorial-conflict-help";
import { useActionGuard } from "@/lib/use-action-guard";
import { ActionButton, AsyncStatus, type ActionState } from "@/components/action-feedback";
import { EmptyState, PageHeader, StatusBadge } from "@/components/admin-ui";
import { EntityPicker, RepeatableField } from "../forms/workflow-fields";
import { PathRouteCandidates } from "./path-route-candidates";
import { movePathMaterial, movePathStage } from "./path-stage-order";
import { PathMaterialCards, PathStageIndex, type PathDrag } from "./path-material-cards";
import { useReadingPathPreview } from "./use-reading-path-preview";
import pathStyles from "../knowledge/path-editor.module.css";
import { PathDependencyEditor, PathDependencyValidation } from "./reading-path-dependencies";
import { emptyLearning, emptyMaterial, learningFields, materialFields, strings, PathLearningEditor, PathMaterialEditor, type PathLearningFields, type PathMaterialFields } from "./reading-path-fields";
import { asArray, asRecord, asString } from "../workflow/workflow-types";
import { CurationFieldAssistant } from "./curation-field-assistant";
import { EditorialPrefillNotice, useEditorialPrefills } from "./editorial-prefills";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { KnowledgeImagePanel } from "../media/knowledge-image-panel";
import { KnowledgeVisualEditor } from "../knowledge/knowledge-visual-editor";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useScholarSave } from "../knowledge/use-scholar-save";
import type { PreviewSelection } from "./fixed-page-editor";
import { KnowledgeObjectContextPanel } from "../knowledge/knowledge-object-context-panel";
import { CurationDiscoveryPreview } from "./curation-discovery-preview";

type PathItemDraft = PathMaterialFields & {
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
type StageDraft = PathLearningFields & {
  estimated_reading: string;
  key: string;
  id?: string;
  name: string;
  description: string;
  items: PathItemDraft[];
};
type ReadingPathRow = PathLearningFields & {
  topics: string[]; estimated_weeks: number | null; prerequisite: string; curator_note: string; credits: { name: string; role: string }[];
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
  stages: Array<PathLearningFields & { id: string; name: string; description: string; position: number; estimated_reading: string }>;
  items: Array<Record<string, unknown>>;
  draft_stage_groups: Array<Record<string, unknown>>;
  editorial_revision: { id: string; revision: number; status: string } | null;
  updated_at: string;
};

const emptyPath = {
  ...emptyLearning, topics: [] as string[], estimated_weeks: null as number | null, prerequisite: "", curator_note: "", credits: [] as { name: string; role: string }[],
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
  return { ...emptyMaterial, id:createRequestKey(), key: key("item"), node: null, node_name: "", work: null, work_name: "", recommendation_reason: "", prerequisite: "", is_required: false, editorial_note: "" };
}

function emptyStage(position: number): StageDraft {
  return { ...emptyLearning, id:createRequestKey(), estimated_reading: "", key: key("stage"), name: `第 ${position + 1} 阶段`, description: "", items: [emptyItem()] };
}

function normalizePath(value: unknown): ReadingPathRow {
  const row = asRecord(value);
  const primaryDiscipline = asRecord(row.primary_discipline_data);
  return {
    ...learningFields(row), topics: strings(row.topics), estimated_weeks: typeof row.estimated_weeks === "number" ? row.estimated_weeks : null,
    prerequisite: asString(row.prerequisite), curator_note: asString(row.curator_note),
    credits: asArray(row.credits).map(value => ({ name: asString(asRecord(value).name), role: asString(asRecord(value).role) })),
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
      return { ...learningFields(stage), estimated_reading: asString(stage.estimated_reading), id: asString(stage.id), name: asString(stage.name, `第 ${position + 1} 阶段`), description: asString(stage.description), position: Number(stage.position ?? position) };
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
        ...learningFields(stage), estimated_reading: asString(stage.estimated_reading),
        key: asString(stage.id, key("draft-stage")),
        id: asString(stage.id) || undefined,
        name: asString(stage.name, `第 ${stageIndex + 1} 阶段`),
        description: asString(stage.description),
        items: asArray(stage.items).map((value) => {
          const item = asRecord(value);
          const canonical = canonicalItems.get(asString(item.id)) ?? {};
          const nodeData = asRecord(canonical.node_data);
          const workData = asRecord(canonical.work_data);
          return {
            ...materialFields(item),
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
  const stages: StageDraft[] = path.stages.map((stage) => ({ ...learningFields(stage), estimated_reading: stage.estimated_reading, key: stage.id, id: stage.id, name: stage.name, description: stage.description, items: [] as PathItemDraft[] }));
  const byId = new Map(stages.map((stage) => [stage.id, stage]));
  path.items.forEach((item) => {
    const stageId = asString(item.stage);
    const nodeData = asRecord(item.node_data);
    const workData = asRecord(item.work_data);
    let stage = byId.get(stageId);
    if (!stage) {
      const legacyStage: StageDraft = { ...emptyLearning, estimated_reading: "", key: key("legacy-stage"), name: asString(item.stage_name, "未命名阶段"), description: asString(item.stage_description), items: [] };
      stages.push(legacyStage);
      stage = legacyStage;
    }
    stage.items.push({
      ...materialFields(item),
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

function move<T>(values: T[], from: number, to: number) {
  if (to < 0 || to >= values.length || from === to) return values;
  const next = [...values];
  const [value] = next.splice(from, 1);
  next.splice(to, 0, value);
  return next;
}

function editablePath(path?: ReadingPathRow) {
  return path ? {
    ...learningFields(path), topics: path.topics, estimated_weeks: path.estimated_weeks, prerequisite: path.prerequisite, curator_note: path.curator_note, credits: path.credits,
    title: path.title, slug: path.slug, introduction: path.introduction,
    learning_goal: path.learning_goal, primary_discipline: path.primary_discipline ?? "",
    audience: path.audience, difficulty: path.difficulty, estimated_reading: path.estimated_reading,
    status: path.status, sort_order: path.sort_order,
  } : { ...emptyPath };
}

function pathFormValue(draft: typeof emptyPath, stages: StageDraft[]) {
  return { draft, stages: stages.map((stage) => ({ name: stage.name, description: stage.description, ...learningFields(stage), estimated_reading: stage.estimated_reading,
    items: stage.items.map(item => Object.fromEntries(Object.entries(item).filter(([field]) => field !== "key" && field !== "id"))),
  })) };
}

function pathStageGroups(stages:StageDraft[]) {
  return stages.map((stage, stagePosition) => ({
          id: stage.id,
          name: stage.name,
          description: stage.description,
          ...learningFields(stage), estimated_reading: stage.estimated_reading,
          position: stagePosition,
          items: stage.items.map((item, position) => ({
            id: item.id, ...materialFields(item),
            node: item.node,
            work: item.work,
            recommendation_reason: item.recommendation_reason,
            prerequisite: item.prerequisite,
            position,
            is_required: item.is_required,
            editorial_note: item.editorial_note,
          })),
        }));
}

export function ReadingPathWorkbench() {
  const owner=String(useAdminSession()?.id||""),[epoch,setEpoch]=useState(0);
  useEffect(()=>subscribeToSessionChanges(()=>setEpoch(value=>value+1)),[]);
  return <ReadingPathEditor key={`${owner}:${epoch}`} owner={owner}/>;
}

function ReadingPathEditor({owner}:{owner:string}) {
  const session=useAdminSession(), canEdit=hasAdminCapability(session,"can_edit_draft_authority"),canCreate=hasAdminCapability(session,"can_create_authority");
  const command=useScholarSave(owner,"path");
  const [routeBusy,setRouteBusy]=useState(false);
  const life=useRef<AbortController|null>(null);
  useEffect(()=>{const controller=new AbortController();life.current=controller;return()=>controller.abort();},[]);
  const apiRequest=useCallback(<T,>(path:string,options:RequestInit={},token:string|null=getServerSessionCredential())=>{
    const lifetime=life.current;if(!lifetime||lifetime.signal.aborted)return Promise.reject<T>(Error("编辑会话已变化。"));
    const signal=AbortSignal.any([lifetime.signal,AbortSignal.timeout(60000),...(options.signal?[options.signal]:[])]);
    return withPrivateOwner(owner,()=>baseApiRequest<T>(path,{...options,signal,cache:"no-store",headers:{...options.headers,"X-Editor-Owner":owner}},token,false),signal);
  },[owner]);
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
  const dragRef = useRef<PathDrag>(null);
  const composing = useRef(false);
  const [stages, setStages] = useState<StageDraft[]>([emptyStage(0)]);
  const previewStage = stages[Math.min(activeStage, stages.length - 1)];
  function selectPreview({ stageId, itemId }: PreviewSelection) {
    const stageIndex = stages.findIndex(stage => (stage.id || stage.key) === stageId);
    if (stageIndex < 0) return;
    setActiveStage(stageIndex);
    const itemIndex = itemId ? stages[stageIndex].items.findIndex(item => (item.id || item.key) === itemId) : 0;
    setActiveItem(Math.max(0, itemIndex));
  }
  const [savedContent, setSavedContent] = useState(() => pathFormValue(emptyPath, [emptyStage(0)]));
  const dirty = useUnsavedForm(pathFormValue(draft, stages), savedContent);
  const dirtyRef = useRef(dirty);
  useEffect(() => { dirtyRef.current = dirty || routeBusy || Boolean(command.recovery); }, [dirty, routeBusy, command.recovery]);
  const prefills = useEditorialPrefills(editing?.id || "new-path", { stages }, (update) => setStages((current) => (
    typeof update === "function" ? update({ stages: current }) : update
  ).stages));
  const [imageRevision, setImageRevision] = useState(0);
  const { status: _previewStatus, sort_order: _previewSort, ...previewFields } = draft;
  const pathPreview = useReadingPathPreview(owner, JSON.stringify({
    ...previewFields, primary_discipline: draft.primary_discipline || null,
    path_id: editing?.id || null, edit_version: editing?.edit_version || "",
    stage_groups: pathStageGroups(stages).map(group => ({ ...group, name: group.name.trim() || "未命名阶段",
      items: group.items.filter(item => item.work || item.node) })),
  }), `${editing?.updated_at}:${imageRevision}`);
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
  }, [query, page, apiRequest]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadPaths(), 0);
    return () => { window.clearTimeout(timer); listRequest.current?.abort(); };
  }, [loadPaths]);

  useEffect(() => {
    if (!requestedPath) return;
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
      setDraft(editablePath(path));
      setPrimaryDisciplineName(path.primary_discipline_name);
      setStages(pathStages(path));
      setSavedContent(pathFormValue(editablePath(path), pathStages(path)));
      setMessage("已打开当前阅读路径。");
      setMessageState("success");
      setOpenedPath(requestedPath);
      setActiveStage(0); setActiveItem(0);
    }).catch((error) => {
      if (!active) return;
      setMessage(error instanceof Error ? error.message : "阅读路径读取失败。");
      setMessageState("error");
    });
    return () => {
      active = false;
    };
  }, [requestedPath, apiRequest]);

  function start(path?: ReadingPathRow, saved = false) {
    if (!saved && (command.recovery || pendingAction || routeBusy)) return;
    if (!saved && dirty && !window.confirm("阅读路径还有未保存的安排。放弃填写并切换吗？")) return;
    prefills.clear();
    setEditing(path ?? null);
    setActiveStage(0); setActiveItem(0); dragRef.current = null;
    setDraft(editablePath(path));
    setStages(path ? pathStages(path) : [emptyStage(0)]);
    setSavedContent(pathFormValue(editablePath(path), path ? pathStages(path) : [emptyStage(0)]));
    setPrimaryDisciplineName(path?.primary_discipline_name ?? "");
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

  function arrange(next: StageDraft[]) {
    const selectedStage = stages[Math.min(activeStage, stages.length - 1)];
    const selectedItem = selectedStage?.items[Math.min(activeItem, selectedStage.items.length - 1)];
    const itemStage = selectedItem ? next.findIndex(stage => stage.items.some(item => item.key === selectedItem.key)) : -1;
    const stageIndex = itemStage >= 0 ? itemStage : Math.max(0, next.findIndex(stage => stage.key === selectedStage?.key));
    setStages(next); setActiveStage(stageIndex);
    setActiveItem(Math.max(0, next[stageIndex]?.items.findIndex(item => item.key === selectedItem?.key) ?? 0));
  }
  function moveItem(itemKey: string, stageKey: string, beforeKey?: string) { arrange(movePathMaterial(stages, itemKey, stageKey, beforeKey)); }
  function removeItems(itemKeys: string[], stageKey?: string) {
    const removed = stages.flatMap(stage => stage.items).filter(item => itemKeys.includes(item.key));
    const ids = new Set(removed.map(item => item.id));
    const affected = stages.flatMap(stage => stage.items).filter(item => !ids.has(item.id)).reduce((count, item) => count + item.dependencies.filter(relation => ids.has(relation.item_id)).length, 0);
    if (!window.confirm(`${stageKey ? "移除这个阶段及其中" : "移除"}${removed.length} 项材料？${affected ? `同时从当前草稿中移除指向它们的 ${affected} 条关系。` : ""}原馆藏、读者进度与笔记不会删除；保存发布前不影响公开路线。`)) return;
    arrange(stages.filter(stage => stage.key !== stageKey).map(stage => ({ ...stage, items: stage.items.filter(item => !itemKeys.includes(item.key)).map(item => ({ ...item, dependencies: item.dependencies.filter(relation => !ids.has(relation.item_id)) })) })));
  }

  const itemCount = useMemo(() => stages.reduce((count, stage) => count + stage.items.length, 0), [stages]);

  async function save(event?: FormEvent, draftOnly = false) {
    event?.preventDefault();
    if ((event?.nativeEvent as Event & { isComposing?: boolean })?.isComposing || composing.current) return false;
    const token = getServerSessionCredential();
    if (!token || !canEdit || routeBusy || (!editing && !canCreate)) return false;
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
        stage_groups: pathStageGroups(stages),
      };
      const saved = normalizePath(await command.save(
        `/catalog/admin/theory-system/reading-paths/${editing ? `${editing.id}/` : ""}`,
        JSON.stringify(payload), editing ? editorialHeaders(editing) : {}, editing ? "PATCH" : "POST",
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

  async function recoverSave(cancel=false) {
    const receipt=await command.lookup(cancel);if(!receipt)return;
    try { if(receipt.exists&&receipt.path_id)start(normalizePath(await apiRequest(`/catalog/admin/theory-system/reading-paths/${receipt.path_id}/`)),true);
    setMessage(receipt.state==="cancelled"?"原请求已停止，当前输入保留。":receipt.exists?"已找回原保存，请核对内容。":"原保存已完成，但路径后来已删除，不会再次新建。");setMessageState("success");
    }catch(reason){setMessage(reason instanceof Error?reason.message:"已找到原保存，当前详情暂不可读取。");setMessageState("error");}
  }

  async function removePath() {
    if(command.recovery||routeBusy||!canEdit)return;
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
    <div className={`admin-page reading-path-v280-page ${pathStyles.workspace}`}>
      <PageHeader eyebrow="内容 › 页面编排 › 公共阅读路径编排" title="公共阅读路径编排"  actions={<details className={pathStyles.pageTools}><summary aria-label="更多路径操作">⋮</summary><button type="button" onClick={()=>start()}><Plus size={14}/>新建路径</button></details>} />
      {message ? <AsyncStatus state={messageState} message={message} /> : null}
      <div className="reading-path-v280-layout">
        <details className={pathStyles.directory}><summary>查找与切换阅读路径</summary><aside className="admin-panel reading-path-v280-list">
          <header><h2>路径</h2><ActionButton type="button" state={pendingAction === "refresh-reading-paths" ? "pending" : "idle"} pendingLabel="刷新中" disabled={Boolean(pendingAction) && pendingAction !== "refresh-reading-paths"} onClick={() => void refreshPaths()}><RefreshCw size={13} />刷新</ActionButton></header>
          <label><span className="sr-only">搜索阅读路径</span><input type="search" value={query} onChange={(event) => { setQuery(event.target.value); paging.reset({ q: event.target.value }); }} placeholder="搜索路径" /></label>
          {paths.map((path) => <button className={editing?.id === path.id ? "selected" : ""} type="button" key={path.id} onClick={() => start(path)}><span><strong>{path.title}</strong><small>{path.stages.length} 阶段 · {path.items.length} 项阅读内容</small></span><StatusBadge label={path.status} /><ArrowRight size={13} /></button>)}
          {!loading && !paths.length ? <EmptyState compact title="尚无阅读路径" description="建立路径后，也可以从文献的编辑页面加入阅读内容。" /> : null}
          <AdminListPages data={collection} paging={paging} loading={loading} filters={{ q: query }} />
        </aside></details>
        {command.recovery?<div role="status"><p>原保存结果尚未确认，请先查询。</p><button type="button" onClick={()=>void recoverSave()}>查询原请求</button>{command.canRetry?<button type="submit" form="reading-path-editor-form">重试原保存</button>:null}<button type="button" onClick={()=>void recoverSave(true)}>停止未完成请求</button></div>:null}{command.error?<p role="alert">{command.error}</p>:null}<KnowledgeVisualEditor readingPathCandidates={<PathRouteCandidates key={`${owner}:${editing?.id||"new"}`} owner={owner} pathId={editing?.id} version={editing?.edit_version||""} blocked={dirty||Boolean(command.recovery)||Boolean(pendingAction)||!canEdit} onPending={setRouteBusy} onApplied={async()=>{if(!editing)return;try{const value=normalizePath(await apiRequest(`/catalog/admin/theory-system/reading-paths/${editing.id}/`));start(value,true);await loadPaths();}catch(error){setEditConflict(true);throw error;}}}/>} readingPathPreview={pathPreview} objectType="reading_path" objectId={editing?.id} previewStageId={previewStage?.id || previewStage?.key || ""} onPreviewSelect={selectPreview} savedRecord={editing} onPublished={() => {void loadPaths();setEditConflict(true);setMessage("发布操作已提交，请打开最新阅读路径后继续编辑。");}} draft={{...draft, stages}} dirty={dirty||Boolean(command.recovery)||routeBusy} refreshKey={`${editing?.updated_at}:${imageRevision}`}>{requestedPath && openedPath !== requestedPath ? <p role="status">正在读取指定阅读路径，载入后即可编辑。</p> : null}<form onCompositionStart={()=>{composing.current=true;}} onCompositionEnd={()=>{composing.current=false;}} id="reading-path-editor-form" className="admin-panel reading-path-v280-editor" onSubmit={(event) => void save(event, true)} aria-busy={Boolean(requestedPath && openedPath !== requestedPath)}>
          <p data-editor-section="publication">保存这条路径的说明、全部阶段、书目顺序和推荐理由，不跳转。已公开路径的修改需另行发布。</p>
          <EditorialPrefillNotice state={prefills} />
          <fieldset disabled={!canEdit||(!editing&&!canCreate)||!command.ready||Boolean(command.recovery)||Boolean(requestedPath && openedPath !== requestedPath)||routeBusy} style={{ display: "contents" }}>
          <header data-editor-section="publication"><div><h2>{editing ? `编辑 ${editing.title}` : "新建阅读路径"}</h2><p>{stages.length} 个阶段 · {itemCount} 个项目</p></div>{editing ? <div><Link href={`/admin/preview/knowledge/reading_path/${editing.id}`} target="_blank">预览已保存内容 <ExternalLink size={12} /></Link><ActionButton type="button" state={pendingAction === `delete-reading-path:${editing.id}` ? "pending" : "idle"} disabled={Boolean(pendingAction) && pendingAction !== `delete-reading-path:${editing.id}`} aria-label="删除阅读路径" onClick={() => void removePath()}><Trash2 size={14} /></ActionButton></div> : null}</header>
          <section data-editor-section="identity" className={pathStyles.basicFields}><h2>一、路线基本信息</h2><div className={pathStyles.basicTitleRow}>
          <label><span>路线标题</span><input required value={draft.title} onChange={event=>setDraft({...draft,title:event.target.value})}/></label><label><span>路线目标</span><textarea rows={1} value={draft.learning_goal} onChange={event=>setDraft({...draft,learning_goal:event.target.value})}/></label></div>
          <div className={pathStyles.basicOptions}><label><span>读者基础</span><input list="path-reader-foundations" value={draft.prerequisite} onChange={event=>setDraft({...draft,prerequisite:event.target.value})}/><datalist id="path-reader-foundations"><option value="无前置要求"/><option value="本科及以上"/><option value="已有相关阅读基础"/></datalist></label><label><span>难度</span><select value={draft.difficulty} onChange={event=>setDraft({...draft,difficulty:event.target.value})}><option value="beginner">入门</option><option value="intermediate">中级</option><option value="advanced">进阶</option></select></label><label><span>预计时长</span><input value={draft.estimated_reading} onChange={event=>setDraft({...draft,estimated_reading:event.target.value})}/></label><label><span>适用人群</span><input value={draft.audience} onChange={event=>setDraft({...draft,audience:event.target.value})}/></label></div></section>
          <details data-editor-section="identity" className={pathStyles.extraFields}><summary>固定链接、路径介绍与分类</summary>
<label><span>固定链接</span><input required value={draft.slug} onChange={(event) => setDraft({ ...draft, slug: event.target.value })} /></label>          <label><span>路径介绍</span><textarea rows={4} value={draft.introduction} onChange={(event) => setDraft({ ...draft, introduction: event.target.value })} /></label><EntityPicker label="主要学科" endpoint="/catalog/admin/disciplines/" queryParam="q" nameField="name" values={draft.primary_discipline ? [{ id: draft.primary_discipline, name: primaryDisciplineName || "已选择主要学科" }] : []} onChange={(next) => { const selected = next.at(-1); setDraft({ ...draft, primary_discipline: selected?.id ?? "" }); setPrimaryDisciplineName(selected?.name ?? ""); }} /><label><span>状态</span><select disabled title="状态通过发布或下线操作更新" value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}><option value="draft">草稿</option><option value="pending">提交审核</option><option value="published">发布</option><option value="archived">归档</option></select></label><label><span>路径排序</span><input type="number" value={draft.sort_order} onChange={(event) => setDraft({ ...draft, sort_order: Number(event.target.value) })} /></label>
          </details>
          <details data-editor-section="identity" className={pathStyles.extraFields}><summary>路径主题、学习问题与策划说明</summary>
            <EntityPicker label="路径主题" endpoint="/catalog/admin/topics/" queryParam="q" nameField="name" values={draft.topics.map(id => ({ id, name: "已选择的主题" }))} onChange={rows => setDraft(current => ({ ...current, topics: rows.flatMap(row => row.id ? [row.id] : []) }))} />
            <div className="inline-fields"><label><span>明确建议周数（可空）</span><input type="number" min={1} max={520} value={draft.estimated_weeks ?? ""} onChange={event => setDraft({ ...draft, estimated_weeks: event.target.value ? Number(event.target.value) : null })} /></label></div>
            <section data-editor-section="learning"><PathLearningEditor label="路径" value={draft} onChange={patch => setDraft(current => ({ ...current, ...patch }))} /><p>新增争论名称在保存草稿后从真实关联核对。</p></section>
            <section data-editor-section="curation"><label><span>公开策划说明</span><textarea rows={4} value={draft.curator_note} onChange={event => setDraft({ ...draft, curator_note: event.target.value })} /></label>
            <RepeatableField label="公开策划署名" values={draft.credits} create={() => ({ name: "", role: "" })} onChange={credits => setDraft(current => ({ ...current, credits }))} render={(credit, index, update) => <div className="inline-fields"><label><span>署名 {index + 1}</span><input value={credit.name} maxLength={160} onChange={event => update({ ...credit, name: event.target.value })} /></label><label><span>承担工作</span><input value={credit.role} maxLength={100} onChange={event => update({ ...credit, role: event.target.value })} /></label></div>} />
            <p>署名由策划者明确填写，不从编辑账号自动公开个人资料。周数与阅读量属于建议，不代表系统预测。</p></section><section data-editor-section="versions"><p>历史版本来自正式发布记录。保存草稿不会新增公开版本；请在下方发布与记录中核对。</p></section>
          </details>
          <section data-editor-section="media">{editing ? <KnowledgeImagePanel objectType="reading_path" objectId={editing.id} refreshKey={`${editing.updated_at}:${imageRevision}`} onChanged={() => setImageRevision((value) => value + 1)} /> : <p>先保存阅读路径，再选择页面图片。</p>}</section>
          <section className="reading-path-v280-stages" data-editor-section="paths">
            <div className="workflow-field-assistant-row"><strong>阅读内容</strong><CurationFieldAssistant label="阅读内容" targetType="reading_path" targetId={editing?.id} fieldName="item" query={draft.title} currentValue={stages.flatMap((stage) => stage.items.map((item) => ({ work_id: item.work, node_id: item.node })))} formContext={{ language: "zh", learning_goal: draft.learning_goal }} lookupLabel="推荐阅读内容" onFillSuggestion={(candidateId, value, label) => {
              const row = asRecord(value), work = asString(row.work_id) || null, node = asString(row.node_id) || null;
              if (!work && !node) return false;
              return prefills.fill(candidateId, (current) => {
                if (current.stages.some((stage) => stage.items.some((item) => item.work === work && item.node === node))) return current;
                const name = asString(row.stage_name, "建议阅读");
                const item = { ...emptyItem(), work, node, work_name: work ? label : "", node_name: node ? label : "", recommendation_reason: asString(row.recommendation_reason), is_required: row.is_required === true };
                const found = current.stages.findIndex((stage) => stage.name === name);
                return { stages: found < 0 ? [...current.stages, { ...emptyLearning, estimated_reading: "", id: createRequestKey(), key: key("stage"), name, description: asString(row.stage_description), items: [item] }] : current.stages.map((stage, index) => index === found ? { ...stage, items: [...stage.items.filter((entry) => entry.work || entry.node), item] } : stage) };
              });
            }} /></div>
            <header><div><h3>二、阶段与阅读条目</h3><p>共 {stages.length} 个阶段 · {itemCount} 项阅读内容</p></div><button type="button" disabled={stages.length >= 60} onClick={() => {setActiveStage(stages.length);setActiveItem(0);setStages((current) => [...current, emptyStage(current.length)]);}}><Plus size={13} />添加阶段</button><button type="button" disabled={!stages.length||itemCount>=600} onClick={()=>{const index=Math.min(activeStage,stages.length-1),stage=stages[index];setActiveItem(stage.items.length);patchStage(index,{items:[...stage.items,emptyItem()]});}}>从馆藏选择条目</button></header>
            <PathStageIndex stages={stages} active={Math.min(activeStage, stages.length - 1)} onSelect={index => { setActiveStage(index); setActiveItem(0); }} onMoveStage={(key, before) => arrange(movePathStage(stages, key, before))} onMoveItem={moveItem} dragRef={dragRef}/>
            {stages.map((stage, stageIndex) => <article className="reading-path-v280-stage" style={{order:stageIndex*2+1}} key={stage.key} data-editor-stage-id={stage.id || stage.key} hidden={stageIndex!==Math.min(activeStage,stages.length-1)}>
              <div className={pathStyles.stageHeading}><strong>阶段 {stageIndex+1}：{stage.name}</strong><small>{stage.items.length} 项</small></div><details className={pathStyles.stageFields}><summary>编辑阶段 ···</summary>
              <header><span>{stageIndex + 1}</span><input aria-label={`第 ${stageIndex + 1} 阶段名称`} value={stage.name} onChange={(event) => patchStage(stageIndex, { name: event.target.value })} /><div><button type="button" aria-label="上移阶段" disabled={stageIndex === 0} onClick={() => arrange(move(stages, stageIndex, stageIndex - 1))}><ArrowUp size={12} /></button><button type="button" aria-label="下移阶段" disabled={stageIndex === stages.length - 1} onClick={() => arrange(move(stages, stageIndex, stageIndex + 1))}><ArrowDown size={12} /></button><button type="button" aria-label="删除阶段" onClick={() => removeItems(stage.items.map(item => item.key), stage.key)}><Trash2 size={12} /></button></div></header>
              <textarea aria-label={`${stage.name}阶段说明`} rows={2} value={stage.description} onChange={(event) => patchStage(stageIndex, { description: event.target.value })} />
              <label><span>阶段建议用时</span><input value={stage.estimated_reading} maxLength={120} onChange={event => patchStage(stageIndex, { estimated_reading: event.target.value })} placeholder="例如：1–2 周，可留空" /></label>
              <details><summary>本阶段学习问题与相关争论</summary><PathLearningEditor label={stage.name} value={stage} onChange={patch => patchStage(stageIndex, patch)} /></details>
              </details>
              <PathMaterialCards stage={stage} selected={Math.min(activeItem, stage.items.length - 1)} data={pathPreview.data} onSelect={setActiveItem} onMove={moveItem} dragRef={dragRef}/>
              <div className="reading-path-v280-items">{stage.items.map((item, itemIndex) => <section key={item.key} data-editor-item-id={item.id || item.key} hidden={itemIndex!==Math.min(activeItem,stage.items.length-1)}>
                <details className={pathStyles.itemFields} open={!item.work&&!item.node}><summary>编辑所选条目 · 推荐理由、阅读目标与先修依赖</summary><header><strong>项目 {itemIndex + 1}</strong><div><button type="button" aria-label="上移项目" disabled={itemIndex === 0} onClick={() => moveItem(item.key, stage.key, stage.items[itemIndex - 1]?.key)}><ArrowUp size={12} /></button><button type="button" aria-label="下移项目" disabled={itemIndex === stage.items.length - 1} onClick={() => moveItem(item.key, stage.key, stage.items[itemIndex + 2]?.key)}><ArrowDown size={12} /></button><button type="button" aria-label="移除项目" onClick={() => removeItems([item.key])}><Trash2 size={12} /></button></div></header>
                <div className="inline-fields"><label><span>移到阶段</span><select value={stage.key} onChange={event => moveItem(item.key, event.target.value)}>{stages.map(row => <option key={row.key} value={row.key}>{row.name || "未命名阶段"}</option>)}</select></label><label><span>本阶段位置</span><select value={itemIndex} onChange={event => { const position = Number(event.target.value), others = stage.items.filter(row => row.key !== item.key); moveItem(item.key, stage.key, others[position]?.key); }}>{stage.items.map((row, index) => <option key={row.key} value={index}>第 {index + 1} 项</option>)}</select></label></div>
                <div className="inline-fields reading-path-v292-entity-fields"><EntityPicker label="馆藏作品" endpoint="/catalog/admin/library/works/" queryParam="q" nameField="title" values={item.work ? [{ id: item.work, name: item.work_name || "已选择馆藏作品" }] : []} onChange={(next) => { const selected = next.at(-1); patchItem(stageIndex, itemIndex, { ...(selected?.id === item.work ? {} : emptyMaterial), work: selected?.id ?? null, work_name: selected?.name ?? "", node: null, node_name: "" }); }} /><EntityPicker label="理论或概念" endpoint="/catalog/admin/theory-system/nodes/" queryParam="q" nameField="canonical_name_zh" values={item.node ? [{ id: item.node, name: item.node_name || "已选择理论或概念" }] : []} onChange={(next) => { const selected = next.at(-1); patchItem(stageIndex, itemIndex, { ...emptyMaterial, material_kind: "node", node: selected?.id ?? null, node_name: selected?.name ?? "", work: null, work_name: "" }); }} /></div>
                <PathMaterialEditor key={`${item.key}:${item.work || item.node || "empty"}`} work={item.work} value={item} onChange={patch => patchItem(stageIndex, itemIndex, patch)} />
                <label><span>这份材料的阅读目标</span><textarea rows={2} maxLength={2000} value={item.learning_goal} onChange={event=>patchItem(stageIndex,itemIndex,{learning_goal:event.target.value})}/></label>
                <label><span>公开推荐理由</span><textarea rows={3} value={item.recommendation_reason} onChange={(event) => patchItem(stageIndex, itemIndex, { recommendation_reason: event.target.value })} placeholder="这份材料适合讨论什么问题，为什么值得在这里阅读？" /></label>
                <CurationDiscoveryPreview sourceTitle={draft.title} subjectTitle={item.work_name || item.node_name} reason={item.recommendation_reason} />
                <PathDependencyEditor itemId={item.id} value={item.dependencies} materials={stages.flatMap(stage=>stage.items)} onChange={dependencies=>patchItem(stageIndex,itemIndex,{dependencies})}/>
                <label><span>前置要求</span><textarea rows={2} value={item.prerequisite} onChange={(event) => patchItem(stageIndex, itemIndex, { prerequisite: event.target.value })} /></label>
                <label><span>编辑备注（仅后台）</span><textarea rows={2} value={item.editorial_note} onChange={(event) => patchItem(stageIndex, itemIndex, { editorial_note: event.target.value })} /></label>
                <label className="workflow-checkbox"><input type="checkbox" checked={item.is_required} onChange={(event) => patchItem(stageIndex, itemIndex, { is_required: event.target.checked })} /><span>设为必读</span></label></details>
              </section>)}</div>
              <button className="button secondary" type="button" disabled={itemCount >= 600} onClick={() => {setActiveItem(stage.items.length);patchStage(stageIndex, { items: [...stage.items, emptyItem()] });}}><Plus size={12} />在本阶段添加阅读内容</button>
            </article>)}
          </section>
          <div data-editor-section="dependencies"><PathDependencyValidation preview={pathPreview.data} owner={owner} pathId={editing?.id} groups={pathStageGroups(stages)} materials={stages.flatMap(stage=>stage.items)} onSelect={id=>{const index=stages.findIndex(stage=>stage.items.some(item=>item.id===id));if(index>=0){setActiveStage(index);setActiveItem(stages[index].items.findIndex(item=>item.id===id));}}}/></div>
          <footer data-editor-section="publication"><ActionButton className="button" type="submit" state={pendingAction === "save-reading-path" ? "pending" : "idle"} pendingLabel="正在保存路径" disabled={Boolean(pendingAction) && pendingAction !== "save-reading-path"}><Save size={14} />{"保存阅读路径草稿"}</ActionButton></footer>
          <EditorialConflictHelp visible={editConflict} href={`/admin/theories/reading-paths?path=${editing?.id}`} />
          </fieldset>
        </form>
        {editing ? <KnowledgeObjectContextPanel hasUnsavedChanges={dirty} objectType="reading_path" objectId={editing.id} refreshKey={`${editing.updated_at}:${imageRevision}`} onChanged={() => { void loadPaths(); setImageRevision((value) => value + 1); setEditConflict(true); setMessage("公开内容已更新。继续修改前，请打开最新内容；本页输入仍保留。"); setMessageState("success"); }} /> : null}</KnowledgeVisualEditor>
      </div>
    </div>
  );
}
