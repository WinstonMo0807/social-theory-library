"use client";

import Link from "next/link";
import { ArrowDown, ArrowRight, ArrowUp, ExternalLink, ImagePlus, Plus, RefreshCw, Save, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { EmptyState, PageHeader, StatusBadge } from "@/components/admin-ui";
import { asArray, asRecord, asString } from "../workflow/workflow-types";

type EntityOption = { id: string; name: string };
type PathItemDraft = {
  key: string;
  id?: string;
  node: string | null;
  work: string | null;
  recommendation_reason: string;
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
  primary_discipline: string | null;
  audience: string;
  difficulty: string;
  estimated_reading: string;
  cover_url: string;
  status: string;
  sort_order: number;
  stages: Array<{ id: string; name: string; description: string; position: number }>;
  items: Array<Record<string, unknown>>;
  updated_at: string;
};

const emptyPath = {
  title: "",
  slug: "",
  introduction: "",
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
  return { key: key("item"), node: null, work: null, recommendation_reason: "", is_required: false, editorial_note: "" };
}

function emptyStage(position: number): StageDraft {
  return { key: key("stage"), name: `第 ${position + 1} 阶段`, description: "", items: [emptyItem()] };
}

function normalizePath(value: unknown): ReadingPathRow {
  const row = asRecord(value);
  return {
    id: asString(row.id),
    title: asString(row.title),
    slug: asString(row.slug),
    introduction: asString(row.introduction),
    primary_discipline: asString(row.primary_discipline) || null,
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
    updated_at: asString(row.updated_at),
  };
}

function pathStages(path: ReadingPathRow): StageDraft[] {
  const stages: StageDraft[] = path.stages.map((stage) => ({ key: stage.id, id: stage.id, name: stage.name, description: stage.description, items: [] as PathItemDraft[] }));
  const byId = new Map(stages.map((stage) => [stage.id, stage]));
  path.items.forEach((item) => {
    const stageId = asString(item.stage);
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
      work: asString(item.work) || null,
      recommendation_reason: asString(item.recommendation_reason),
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
  const [paths, setPaths] = useState<ReadingPathRow[]>([]);
  const [disciplines, setDisciplines] = useState<EntityOption[]>([]);
  const [works, setWorks] = useState<EntityOption[]>([]);
  const [nodes, setNodes] = useState<EntityOption[]>([]);
  const [editing, setEditing] = useState<ReadingPathRow | null>(null);
  const [draft, setDraft] = useState({ ...emptyPath });
  const [stages, setStages] = useState<StageDraft[]>([emptyStage(0)]);
  const [cover, setCover] = useState<File | null>(null);
  const [query, setQuery] = useState("");
  const [catalogQuery, setCatalogQuery] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const loadPaths = useCallback(async () => {
    const token = getServerSessionCredential();
    if (!token) return;
    setLoading(true);
    try {
      const suffix = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
      const [pathPage, disciplinePage] = await Promise.all([
        apiRequest<{ results?: unknown[] }>(`/catalog/admin/theory-system/reading-paths/${suffix}`, {}, token),
        apiRequest<{ results?: unknown[] }>("/catalog/admin/disciplines/", {}, token),
      ]);
      setPaths((pathPage.results ?? []).map(normalizePath));
      setDisciplines((disciplinePage.results ?? []).map((entry) => { const row = asRecord(entry); return { id: asString(row.id), name: asString(row.name) }; }).filter((row) => row.id && row.name));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "阅读路径读取失败。");
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadPaths(), 0);
    return () => window.clearTimeout(timer);
  }, [loadPaths]);

  useEffect(() => {
    const token = getServerSessionCredential();
    if (!token) return;
    let active = true;
    const timer = window.setTimeout(() => {
      const suffix = catalogQuery.trim() ? `?q=${encodeURIComponent(catalogQuery.trim())}` : "";
      void Promise.all([
        apiRequest<{ results?: unknown[] }>(`/catalog/admin/library/works/${suffix}`, {}, token),
        apiRequest<{ results?: unknown[] }>(`/catalog/admin/theory-system/nodes/${suffix}`, {}, token),
      ]).then(([workPage, nodePage]) => {
        if (!active) return;
        setWorks((workPage.results ?? []).map((entry) => { const row = asRecord(entry); return { id: asString(row.id), name: asString(row.title) }; }).filter((row) => row.id && row.name));
        setNodes((nodePage.results ?? []).map((entry) => { const row = asRecord(entry); return { id: asString(row.id), name: asString(row.canonical_name_zh ?? row.name) }; }).filter((row) => row.id && row.name));
      }).catch((error) => { if (active) setMessage(error instanceof Error ? error.message : "馆藏与节点搜索失败。"); });
    }, 220);
    return () => { active = false; window.clearTimeout(timer); };
  }, [catalogQuery]);

  function start(path?: ReadingPathRow) {
    setEditing(path ?? null);
    setDraft(path ? {
      title: path.title,
      slug: path.slug,
      introduction: path.introduction,
      primary_discipline: path.primary_discipline ?? "",
      audience: path.audience,
      difficulty: path.difficulty,
      estimated_reading: path.estimated_reading,
      status: path.status,
      sort_order: path.sort_order,
    } : { ...emptyPath });
    setStages(path ? pathStages(path) : [emptyStage(0)]);
    setCover(null);
    setMessage("");
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

  async function save(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return;
    setBusy(true);
    try {
      const payload = {
        ...draft,
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
      setMessage("阅读路径已保存。阶段和阶段内作品分别排序，单项策展 placement 已保留。");
      await loadPaths();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "阅读路径保存失败。");
    } finally {
      setBusy(false);
    }
  }

  async function removePath() {
    if (!editing || !window.confirm(`删除阅读路径“${editing.title}”吗？`)) return;
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      await apiRequest(`/catalog/admin/theory-system/reading-paths/${editing.id}/`, { method: "DELETE" }, token);
      start();
      await loadPaths();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "阅读路径删除失败。");
    }
  }

  return (
    <div className="admin-page reading-path-v280-page">
      <PageHeader eyebrow="策展" title="阅读路径工作台" description="阶段是稳定结构，作品在阶段内独立排序。单项馆藏 workflow 只修改当前 Work 的 placement。" actions={<button className="button" type="button" onClick={() => start()}><Plus size={14} />新建路径</button>} />
      {message ? <p className="form-message" role="status">{message}</p> : null}
      <div className="reading-path-v280-layout">
        <aside className="admin-panel reading-path-v280-list">
          <header><h2>路径</h2><button type="button" onClick={() => void loadPaths()}><RefreshCw size={13} />刷新</button></header>
          <label><span className="sr-only">搜索阅读路径</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索路径" /></label>
          {paths.map((path) => <button className={editing?.id === path.id ? "selected" : ""} type="button" key={path.id} onClick={() => start(path)}><span><strong>{path.title}</strong><small>{path.stages.length} 阶段 · {path.items.length} 项作品或节点</small></span><StatusBadge label={path.status} /><ArrowRight size={13} /></button>)}
          {!loading && !paths.length ? <EmptyState compact title="尚无阅读路径" description="建立路径后，可从单项馆藏工作流加入现有阶段。" /> : null}
        </aside>
        <form className="admin-panel reading-path-v280-editor" onSubmit={save}>
          <header><div><h2>{editing ? `编辑 ${editing.title}` : "新建阅读路径"}</h2><p>{stages.length} 个阶段 · {itemCount} 个项目</p></div>{editing ? <div><Link href={`/theories/reading-paths/${editing.slug}`} target="_blank">预览 <ExternalLink size={12} /></Link><button type="button" aria-label="删除阅读路径" onClick={() => void removePath()}><Trash2 size={14} /></button></div> : null}</header>
          <div className="inline-fields"><label><span>标题</span><input required value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label><span>固定链接</span><input required value={draft.slug} onChange={(event) => setDraft({ ...draft, slug: event.target.value })} /></label></div>
          <label><span>路径介绍</span><textarea rows={4} value={draft.introduction} onChange={(event) => setDraft({ ...draft, introduction: event.target.value })} /></label>
          <div className="inline-fields three"><label><span>主要学科</span><select value={draft.primary_discipline} onChange={(event) => setDraft({ ...draft, primary_discipline: event.target.value })}><option value="">跨学科</option>{disciplines.map((discipline) => <option value={discipline.id} key={discipline.id}>{discipline.name}</option>)}</select></label><label><span>适合人群</span><input value={draft.audience} onChange={(event) => setDraft({ ...draft, audience: event.target.value })} /></label><label><span>难度</span><select value={draft.difficulty} onChange={(event) => setDraft({ ...draft, difficulty: event.target.value })}><option value="beginner">入门</option><option value="intermediate">进阶</option><option value="advanced">深入</option></select></label></div>
          <div className="inline-fields three"><label><span>预计阅读量</span><input value={draft.estimated_reading} onChange={(event) => setDraft({ ...draft, estimated_reading: event.target.value })} /></label><label><span>状态</span><select value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}><option value="draft">草稿</option><option value="pending">提交审核</option><option value="published">发布</option><option value="archived">归档</option></select></label><label><span>路径排序</span><input type="number" value={draft.sort_order} onChange={(event) => setDraft({ ...draft, sort_order: Number(event.target.value) })} /></label></div>
          <label className="knowledge-image-upload"><ImagePlus size={17} /><span>{cover?.name || "更新路径封面"}</span><input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setCover(event.target.files?.[0] ?? null)} /></label>
          <label><span>搜索待加入的馆藏或知识节点</span><input type="search" value={catalogQuery} onChange={(event) => setCatalogQuery(event.target.value)} placeholder="题名或节点名称" /></label>
          <section className="reading-path-v280-stages">
            <header><div><h3>阶段与项目</h3><p>先排阶段，再在每个阶段内排作品。空阶段可以保留。</p></div><button type="button" onClick={() => setStages((current) => [...current, emptyStage(current.length)])}><Plus size={13} />添加阶段</button></header>
            {stages.map((stage, stageIndex) => <article className="reading-path-v280-stage" key={stage.key}>
              <header><span>{stageIndex + 1}</span><input aria-label={`第 ${stageIndex + 1} 阶段名称`} value={stage.name} onChange={(event) => patchStage(stageIndex, { name: event.target.value })} /><div><button type="button" aria-label="上移阶段" disabled={stageIndex === 0} onClick={() => setStages((current) => move(current, stageIndex, stageIndex - 1))}><ArrowUp size={12} /></button><button type="button" aria-label="下移阶段" disabled={stageIndex === stages.length - 1} onClick={() => setStages((current) => move(current, stageIndex, stageIndex + 1))}><ArrowDown size={12} /></button><button type="button" aria-label="删除阶段" onClick={() => setStages((current) => current.filter((_row, index) => index !== stageIndex))}><Trash2 size={12} /></button></div></header>
              <textarea aria-label={`${stage.name}阶段说明`} rows={2} value={stage.description} onChange={(event) => patchStage(stageIndex, { description: event.target.value })} />
              <div className="reading-path-v280-items">{stage.items.map((item, itemIndex) => <section key={item.key}>
                <header><strong>项目 {itemIndex + 1}</strong><div><button type="button" aria-label="上移项目" disabled={itemIndex === 0} onClick={() => patchStage(stageIndex, { items: move(stage.items, itemIndex, itemIndex - 1) })}><ArrowUp size={12} /></button><button type="button" aria-label="下移项目" disabled={itemIndex === stage.items.length - 1} onClick={() => patchStage(stageIndex, { items: move(stage.items, itemIndex, itemIndex + 1) })}><ArrowDown size={12} /></button><button type="button" aria-label="移除项目" onClick={() => patchStage(stageIndex, { items: stage.items.filter((_row, index) => index !== itemIndex) })}><Trash2 size={12} /></button></div></header>
                <div className="inline-fields"><label><span>馆藏作品</span><select value={item.work ?? ""} onChange={(event) => patchItem(stageIndex, itemIndex, { work: event.target.value || null, node: null })}><option value="">无</option>{works.map((work) => <option value={work.id} key={work.id}>{work.name}</option>)}</select></label><label><span>知识节点</span><select value={item.node ?? ""} onChange={(event) => patchItem(stageIndex, itemIndex, { node: event.target.value || null, work: null })}><option value="">无</option>{nodes.map((node) => <option value={node.id} key={node.id}>{node.name}</option>)}</select></label></div>
                <label><span>推荐理由</span><textarea rows={2} value={item.recommendation_reason} onChange={(event) => patchItem(stageIndex, itemIndex, { recommendation_reason: event.target.value })} /></label>
                <label><span>编辑备注</span><textarea rows={2} value={item.editorial_note} onChange={(event) => patchItem(stageIndex, itemIndex, { editorial_note: event.target.value })} /></label>
                <label className="workflow-checkbox"><input type="checkbox" checked={item.is_required} onChange={(event) => patchItem(stageIndex, itemIndex, { is_required: event.target.checked })} /><span>设为必读</span></label>
              </section>)}</div>
              <button className="button secondary" type="button" onClick={() => patchStage(stageIndex, { items: [...stage.items, emptyItem()] })}><Plus size={12} />在本阶段添加作品或节点</button>
            </article>)}
          </section>
          <footer><button className="button" type="submit" disabled={busy}><Save size={14} />{draft.status === "published" ? "保存并发布路径" : "保存阅读路径"}</button></footer>
        </form>
      </div>
    </div>
  );
}
