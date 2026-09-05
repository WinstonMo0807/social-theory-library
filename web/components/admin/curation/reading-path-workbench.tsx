"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowDown, ArrowRight, ArrowUp, ExternalLink, ImagePlus, Plus, RefreshCw, Save, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useActionGuard } from "@/lib/use-action-guard";
import { ActionButton, AsyncStatus, type ActionState } from "@/components/action-feedback";
import { EmptyState, PageHeader, StatusBadge } from "@/components/admin-ui";
import { EntityPicker } from "../forms/workflow-fields";
import { asArray, asRecord, asString } from "../workflow/workflow-types";
import { CurationFieldAssistant } from "./curation-field-assistant";

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

function move<T>(values: T[], from: number, to: number) {
  if (to < 0 || to >= values.length || from === to) return values;
  const next = [...values];
  const [value] = next.splice(from, 1);
  next.splice(to, 0, value);
  return next;
}

export function ReadingPathWorkbench() {
  const searchParams = useSearchParams();
  const requestedPath = searchParams.get("path")?.trim() ?? "";
  const [paths, setPaths] = useState<ReadingPathRow[]>([]);
  const [editing, setEditing] = useState<ReadingPathRow | null>(null);
  const [draft, setDraft] = useState({ ...emptyPath });
  const [primaryDisciplineName, setPrimaryDisciplineName] = useState("");
  const [stages, setStages] = useState<StageDraft[]>([emptyStage(0)]);
  const [cover, setCover] = useState<File | null>(null);
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [messageState, setMessageState] = useState<ActionState>("idle");
  const [loading, setLoading] = useState(true);
  const { pendingAction, startAction, finishAction } = useActionGuard();

  const loadPaths = useCallback(async () => {
    const token = getServerSessionCredential();
    if (!token) return;
    setLoading(true);
    try {
      const suffix = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
      const pathPage = await apiRequest<{ results?: unknown[] }>(`/catalog/admin/theory-system/reading-paths/${suffix}`, {}, token);
      setPaths((pathPage.results ?? []).map(normalizePath));
      return true;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "阅读路径读取失败。");
      setMessageState("error");
      return false;
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadPaths(), 0);
    return () => window.clearTimeout(timer);
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
      setCover(null);
      setMessage("已打开当前阅读路径。");
      setMessageState("success");
    }).catch((error) => {
      if (!active) return;
      setMessage(error instanceof Error ? error.message : "阅读路径读取失败。");
      setMessageState("error");
    });
    return () => {
      active = false;
    };
  }, [requestedPath]);

  function start(path?: ReadingPathRow) {
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
    setPrimaryDisciplineName(path?.primary_discipline_name ?? "");
    setCover(null);
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

  const itemCount = useMemo(() => stages.reduce((count, stage) => count + stage.items.length, 0), [stages]);

  async function save(event?: FormEvent, draftOnly = false) {
    event?.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return false;
    const actionKey = "save-reading-path";
    if (!startAction(actionKey)) return false;
    setMessage("正在保存阅读路径……");
    setMessageState("pending");
    try {
      const payload = {
        ...draft,
        status: draftOnly ? (editing?.status ?? "draft") : draft.status,
        primary_discipline: draft.primary_discipline || null,
        expected_updated_at: editing?.updated_at,
        stage_groups: stages.map((stage, stagePosition) => ({
          id: stage.id,
          name: stage.name,
          description: stage.description,
          position: stagePosition,
          items: stage.items.map((item, position) => ({
            node: item.node,
            work: item.work,
            recommendation_reason: item.recommendation_reason,
            prerequisite: item.prerequisite,
            position,
            is_required: item.is_required,
            editorial_note: item.editorial_note,
          })),
        })),
      };
      let saved = normalizePath(await apiRequest(
        `/catalog/admin/theory-system/reading-paths/${editing ? `${editing.id}/` : ""}`,
        { method: editing ? "PATCH" : "POST", body: JSON.stringify(payload) },
        token,
      ));
      if (cover) {
        const body = new FormData();
        body.append("cover_asset", cover);
        body.append("expected_updated_at", saved.updated_at);
        saved = normalizePath(await apiRequest(`/catalog/admin/theory-system/reading-paths/${saved.id}/`, { method: "PATCH", body }, token));
      }
      start(saved);
      setMessage(saved.editorial_revision
        ? "阅读路径的编辑草稿已保存，确认发布后更新公开页面。"
        : "阅读路径草稿已保存。阶段顺序和作品安排已保留。");
      setMessageState("success");
      await loadPaths();
      return true;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "阅读路径保存失败。");
      setMessageState("error");
      return false;
    } finally {
      finishAction(actionKey);
    }
  }

  async function refreshAcceptedItems() {
    if (!editing) return;
    const result = await apiRequest(`/catalog/admin/theory-system/reading-paths/${editing.id}/`, {}, getServerSessionCredential());
    start(normalizePath(result));
    await loadPaths();
    setMessage("阅读内容建议已保存到当前编辑草稿，发布后生效。");
    setMessageState("success");
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
      const response = asRecord(await apiRequest(`/catalog/admin/theory-system/reading-paths/${editing.id}/`, { method: "DELETE" }, token));
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
      <PageHeader eyebrow="策展" title="阅读路径工作台" description="阶段是稳定结构，作品在阶段内独立排序。单项馆藏 workflow 只修改当前 Work 的 placement。" actions={<button className="button" type="button" onClick={() => start()}><Plus size={14} />新建路径</button>} />
      {message ? <AsyncStatus state={messageState} message={message} /> : null}
      <div className="reading-path-v280-layout">
        <aside className="admin-panel reading-path-v280-list">
          <header><h2>路径</h2><ActionButton type="button" state={pendingAction === "refresh-reading-paths" ? "pending" : "idle"} pendingLabel="刷新中" disabled={Boolean(pendingAction) && pendingAction !== "refresh-reading-paths"} onClick={() => void refreshPaths()}><RefreshCw size={13} />刷新</ActionButton></header>
          <label><span className="sr-only">搜索阅读路径</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索路径" /></label>
          {paths.map((path) => <button className={editing?.id === path.id ? "selected" : ""} type="button" key={path.id} onClick={() => start(path)}><span><strong>{path.title}</strong><small>{path.stages.length} 阶段 · {path.items.length} 项作品或节点</small></span><StatusBadge label={path.status} /><ArrowRight size={13} /></button>)}
          {!loading && !paths.length ? <EmptyState compact title="尚无阅读路径" description="建立路径后，可从单项馆藏工作流加入现有阶段。" /> : null}
        </aside>
        <form className="admin-panel reading-path-v280-editor" onSubmit={save}>
          <header><div><h2>{editing ? `编辑 ${editing.title}` : "新建阅读路径"}</h2><p>{stages.length} 个阶段 · {itemCount} 个项目</p></div>{editing ? <div><Link href={`/theories/reading-paths/${editing.slug}`} target="_blank">预览 <ExternalLink size={12} /></Link><ActionButton type="button" state={pendingAction === `delete-reading-path:${editing.id}` ? "pending" : "idle"} disabled={Boolean(pendingAction) && pendingAction !== `delete-reading-path:${editing.id}`} aria-label="删除阅读路径" onClick={() => void removePath()}><Trash2 size={14} /></ActionButton></div> : null}</header>
          <div className="inline-fields"><label><span>标题</span><input required value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label><span>固定链接</span><input required value={draft.slug} onChange={(event) => setDraft({ ...draft, slug: event.target.value })} /></label></div>
          <label><span>路径介绍</span><textarea rows={4} value={draft.introduction} onChange={(event) => setDraft({ ...draft, introduction: event.target.value })} /></label>
          <label><span>学习目标</span><textarea rows={3} value={draft.learning_goal} onChange={(event) => setDraft({ ...draft, learning_goal: event.target.value })} /></label>
          <div className="inline-fields three"><EntityPicker label="主要学科" endpoint="/catalog/admin/disciplines/" queryParam="q" nameField="name" values={draft.primary_discipline ? [{ id: draft.primary_discipline, name: primaryDisciplineName || "已选择主要学科" }] : []} onChange={(next) => { const selected = next.at(-1); setDraft({ ...draft, primary_discipline: selected?.id ?? "" }); setPrimaryDisciplineName(selected?.name ?? ""); }} /><label><span>适合人群</span><input value={draft.audience} onChange={(event) => setDraft({ ...draft, audience: event.target.value })} /></label><label><span>难度</span><select value={draft.difficulty} onChange={(event) => setDraft({ ...draft, difficulty: event.target.value })}><option value="beginner">入门</option><option value="intermediate">进阶</option><option value="advanced">深入</option></select></label></div>
          <div className="inline-fields three"><label><span>预计阅读量</span><input value={draft.estimated_reading} onChange={(event) => setDraft({ ...draft, estimated_reading: event.target.value })} /></label><label><span>状态</span><select value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}><option value="draft">草稿</option><option value="pending">提交审核</option><option value="published">发布</option><option value="archived">归档</option></select></label><label><span>路径排序</span><input type="number" value={draft.sort_order} onChange={(event) => setDraft({ ...draft, sort_order: Number(event.target.value) })} /></label></div>
          <label className="knowledge-image-upload"><ImagePlus size={17} /><span>{editing?.status === "published" ? "已发布路径的封面暂不支持草稿修改" : cover?.name || "更新路径封面"}</span><input type="file" accept="image/jpeg,image/png,image/webp" disabled={editing?.status === "published"} onChange={(event) => setCover(event.target.files?.[0] ?? null)} /></label>
          <section className="reading-path-v280-stages">
            <div className="workflow-field-assistant-row"><strong>阅读内容</strong><CurationFieldAssistant label="阅读内容" targetType="reading_path" targetId={editing?.id} fieldName="item" query={draft.title} currentValue={stages.flatMap((stage) => stage.items.map((item) => ({ work_id: item.work, node_id: item.node })))} formContext={{ language: "zh", learning_goal: draft.learning_goal }} lookupLabel="推荐关联" beforeAction={() => save(undefined, true)} onAccepted={refreshAcceptedItems} /></div>
            <header><div><h3>阶段与项目</h3><p>先排阶段，再在每个阶段内排作品。空阶段可以保留。</p></div><button type="button" onClick={() => setStages((current) => [...current, emptyStage(current.length)])}><Plus size={13} />添加阶段</button></header>
            {stages.map((stage, stageIndex) => <article className="reading-path-v280-stage" key={stage.key}>
              <header><span>{stageIndex + 1}</span><input aria-label={`第 ${stageIndex + 1} 阶段名称`} value={stage.name} onChange={(event) => patchStage(stageIndex, { name: event.target.value })} /><div><button type="button" aria-label="上移阶段" disabled={stageIndex === 0} onClick={() => setStages((current) => move(current, stageIndex, stageIndex - 1))}><ArrowUp size={12} /></button><button type="button" aria-label="下移阶段" disabled={stageIndex === stages.length - 1} onClick={() => setStages((current) => move(current, stageIndex, stageIndex + 1))}><ArrowDown size={12} /></button><button type="button" aria-label="删除阶段" onClick={() => setStages((current) => current.filter((_row, index) => index !== stageIndex))}><Trash2 size={12} /></button></div></header>
              <textarea aria-label={`${stage.name}阶段说明`} rows={2} value={stage.description} onChange={(event) => patchStage(stageIndex, { description: event.target.value })} />
              <div className="reading-path-v280-items">{stage.items.map((item, itemIndex) => <section key={item.key}>
                <header><strong>项目 {itemIndex + 1}</strong><div><button type="button" aria-label="上移项目" disabled={itemIndex === 0} onClick={() => patchStage(stageIndex, { items: move(stage.items, itemIndex, itemIndex - 1) })}><ArrowUp size={12} /></button><button type="button" aria-label="下移项目" disabled={itemIndex === stage.items.length - 1} onClick={() => patchStage(stageIndex, { items: move(stage.items, itemIndex, itemIndex + 1) })}><ArrowDown size={12} /></button><button type="button" aria-label="移除项目" onClick={() => patchStage(stageIndex, { items: stage.items.filter((_row, index) => index !== itemIndex) })}><Trash2 size={12} /></button></div></header>
                <div className="inline-fields reading-path-v292-entity-fields"><EntityPicker label="馆藏作品" endpoint="/catalog/admin/library/works/" queryParam="q" nameField="title" values={item.work ? [{ id: item.work, name: item.work_name || "已选择馆藏作品" }] : []} onChange={(next) => { const selected = next.at(-1); patchItem(stageIndex, itemIndex, { work: selected?.id ?? null, work_name: selected?.name ?? "", node: null, node_name: "" }); }} /><EntityPicker label="知识节点" endpoint="/catalog/admin/theory-system/nodes/" queryParam="q" nameField="canonical_name_zh" values={item.node ? [{ id: item.node, name: item.node_name || "已选择知识节点" }] : []} onChange={(next) => { const selected = next.at(-1); patchItem(stageIndex, itemIndex, { node: selected?.id ?? null, node_name: selected?.name ?? "", work: null, work_name: "" }); }} /></div>
                <label><span>推荐理由</span><textarea rows={2} value={item.recommendation_reason} onChange={(event) => patchItem(stageIndex, itemIndex, { recommendation_reason: event.target.value })} /></label>
                <label><span>前置要求</span><textarea rows={2} value={item.prerequisite} onChange={(event) => patchItem(stageIndex, itemIndex, { prerequisite: event.target.value })} /></label>
                <label><span>编辑备注（仅后台）</span><textarea rows={2} value={item.editorial_note} onChange={(event) => patchItem(stageIndex, itemIndex, { editorial_note: event.target.value })} /></label>
                <label className="workflow-checkbox"><input type="checkbox" checked={item.is_required} onChange={(event) => patchItem(stageIndex, itemIndex, { is_required: event.target.checked })} /><span>设为必读</span></label>
              </section>)}</div>
              <button className="button secondary" type="button" onClick={() => patchStage(stageIndex, { items: [...stage.items, emptyItem()] })}><Plus size={12} />在本阶段添加作品或节点</button>
            </article>)}
          </section>
          <footer><ActionButton className="button" type="submit" state={pendingAction === "save-reading-path" ? "pending" : "idle"} pendingLabel="正在保存路径" disabled={Boolean(pendingAction) && pendingAction !== "save-reading-path"}><Save size={14} />{draft.status === "published" ? "保存并发布路径" : "保存阅读路径"}</ActionButton></footer>
        </form>
      </div>
    </div>
  );
}
