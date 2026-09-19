"use client";

import { editorialHeaders, isEditorialConflict } from "@/lib/editorial-version";
import { EditorialConflictHelp } from "@/components/admin/knowledge/editorial-conflict-help";
import { useActionGuard } from "@/lib/use-action-guard";

import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  Check,
  ImagePlus,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Trash2,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import type { ReactNode } from "react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { EntityLifecycleActions } from "@/components/entity-lifecycle-actions";
import { ResearchEntityPicker } from "@/components/admin/research/research-entity-picker";
import type { EntityValue } from "@/components/admin/forms/workflow-fields";
import { CurationFieldAssistant } from "@/components/admin/curation/curation-field-assistant";
import { StringListEditor } from "@/components/structured-editors";
import { KnowledgeObjectContextPanel } from "@/components/admin/knowledge/knowledge-object-context-panel";
import { KnowledgeImagePanel } from "@/components/admin/media/knowledge-image-panel";
import { ApiRequestError, apiRequest, getServerSessionCredential } from "@/lib/api";
import { createRequestKey } from "@/lib/request-key";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { AdminListPages, useAdminListPage } from "@/components/admin/knowledge/list-pages";
import { EditorialPrefillNotice, useEditorialPrefills } from "@/components/admin/curation/editorial-prefills";

type Page<T> = { count: number; results: T[]; next?: string | null; previous?: string | null };
function onePickerValue(id: string, name: string): EntityValue[] {
  return id ? [{ id, name: name || "已选择实体" }] : [];
}

function pickerLabels(values: EntityValue[]): Record<string, string> {
  return Object.fromEntries(values.flatMap((value) => value.id ? [[value.id, value.name]] : []));
}

function useResource<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [loadedPath, setLoadedPath] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => {
    setLoading(true);
    setRevision((value) => value + 1);
  }, []);
  useEffect(() => {
    if (!path) return;
    let active = true;
    const token = getServerSessionCredential();
    if (!token) return;
    apiRequest<T>(path, {}, token)
      .then((payload) => { if (active) { setData(payload); setLoadedPath(path); setError(""); } })
      .catch((reason) => { if (active) { setData(null); setLoadedPath(path); setError(reason instanceof Error ? reason.message : "读取失败"); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [path, revision]);
  // A list belongs to its request, never to the newly selected object/type.
  // Gate during render, before the effect runs, so even a fast click is safe.
  return { data: loadedPath === path ? data : null, error: loadedPath === path ? error : "", loading: Boolean(path) && (loading || loadedPath !== path), refresh };
}

function Frame({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children: ReactNode }) {
  return <div className="admin-page knowledge-admin-page"><header className="admin-page-title"><div><p>{eyebrow}</p><h1>{title}</h1><span>{description}</span></div></header>{children}</div>;
}

function Notice({ children }: { children?: string }) {
  return children ? <p className="form-message" role="status">{children}</p> : null;
}

type DisciplineRow = {
  id: string;
  code: string;
  name: string;
  foreign_name: string;
  slug: string;
  search_aliases?: string[];
  description: string;
  introduction: string;
  hero_image: string;
  sort_order: number;
  curation_level: number;
  editorial_status: string;
  counts: { theories: number; subdisciplines: number; topics: number; works: number; scholars: number };
  editorial_revision?: {
    id: string;
    revision: number;
    status: string;
    changed_fields: string[];
    publish_url: string;
  };
};

type DisciplineDraft = {
  code: string;
  name: string;
  foreign_name: string;
  slug: string;
  search_aliases: string;
  description: string;
  introduction: string;
  sort_order: number;
  curation_level: number;
  editorial_status: string;
};

const emptyDiscipline: DisciplineDraft = {
  code: "",
  name: "",
  foreign_name: "",
  slug: "",
  search_aliases: "",
  description: "",
  introduction: "",
  sort_order: 100,
  curation_level: 0,
  editorial_status: "draft",
};

function lineValues(value: string) {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

function editorLineValues(value: string) {
  return value === "" ? [] : value.split(/\r?\n/);
}

function motionAwareScrollBehavior(): ScrollBehavior {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
}

function disciplineToDraft(row: DisciplineRow): DisciplineDraft {
  return {
    code: row.code || "",
    name: row.name || "",
    foreign_name: row.foreign_name || "",
    slug: row.slug || "",
    search_aliases: (row.search_aliases || []).join("\n"),
    description: row.description || "",
    introduction: row.introduction || "",
    sort_order: row.sort_order ?? 100,
    curation_level: row.curation_level ?? 0,
    editorial_status: row.editorial_status || "draft",
  };
}

export function DisciplinesAdmin() {
  const paging = useAdminListPage();
  const requestedId = useSearchParams().get("discipline")?.trim() ?? "";
  const requested = useResource<DisciplineRow>(requestedId ? `/catalog/admin/disciplines/${encodeURIComponent(requestedId)}/` : null);
  const opened = useRef("");
  const [editConflict, setEditConflict] = useState(false);
  const { pendingAction, startAction, finishAction } = useActionGuard();
  const resource = useResource<Page<DisciplineRow>>(`/catalog/admin/disciplines/?page=${paging.page}`);
  const [editing, setEditing] = useState<DisciplineRow | null>(null);
  const [draft, setDraft] = useState(emptyDiscipline);
  const [savedDraft, setSavedDraft] = useState(emptyDiscipline);
  const [image, setImage] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const editorRef = useRef<HTMLFormElement | null>(null);
  const dirty = useUnsavedForm({ draft, image: image?.name ?? null }, { draft: savedDraft, image: null });
  const prefills = useEditorialPrefills(editing?.id || "new-discipline", draft, setDraft);
  async function refreshImage() {
    if (!editing) return;
    try {
      const updated = await apiRequest<DisciplineRow>(`/catalog/admin/disciplines/${editing.id}/`, {}, getServerSessionCredential());
      setEditing((current) => current?.id === updated.id ? updated : current);
      setMessage("图片修改已保存，当前文字填写保留。预览后可确认发布。"); resource.refresh();
    } catch (error) { setMessage(`图片操作后未能重新读取资料。请先重新打开当前学科。${error instanceof Error ? error.message : ""}`); }
  }

  function start(row?: DisciplineRow) {
    if (dirty && !window.confirm("本学科还有未保存的填写。放弃填写并切换吗？")) return;
    prefills.clear();
    setEditConflict(false);
    setEditing(row ?? null);
    setDraft(row ? disciplineToDraft(row) : { ...emptyDiscipline });
    setSavedDraft(row ? disciplineToDraft(row) : { ...emptyDiscipline });
    setImage(null);
    setMessage("");
    window.requestAnimationFrame(() => editorRef.current?.scrollIntoView({ behavior: motionAwareScrollBehavior(), block: "start" }));
  }

  useEffect(() => {
    if (!requested.data || requested.data.id !== requestedId || opened.current === requestedId) return;
    const selected = requested.data;
    const timer = window.setTimeout(() => {
      if (dirty) { setMessage("已保留尚未保存的学科填写。请先保存或从列表明确切换。"); return; }
      opened.current = requestedId;
      setEditing(selected);
      setDraft(disciplineToDraft(selected));
      setSavedDraft(disciplineToDraft(selected));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [requested.data, requestedId, dirty]);

  async function save(event?: FormEvent, draftOnly = false) {
    event?.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return false;
    if (!draftOnly && draft.editorial_status === "published" && editing?.editorial_status !== "published" && !window.confirm("保存并公开这个学科？读者将能看到本页资料。")) return false;
    if (!startAction("save-discipline")) return false;
    setEditConflict(false);
    let metadataSaved = false;
    try {
      let saved = await apiRequest<DisciplineRow>(
        `/catalog/admin/disciplines/${editing ? `${editing.id}/` : ""}`,
        {
          method: editing ? "PATCH" : "POST",
          headers: editing ? editorialHeaders(editing) : undefined,
          body: JSON.stringify({
            code: draft.code,
            name: draft.name,
            foreign_name: draft.foreign_name,
            slug: draft.slug,
            search_aliases: lineValues(draft.search_aliases),
            description: draft.description,
            introduction: draft.introduction,
            sort_order: draft.sort_order,
            curation_level: draft.curation_level,
            editorial_status: draftOnly ? (editing?.editorial_status ?? "draft") : draft.editorial_status,
          }),
        },
        token,
      );
      metadataSaved = true;
      setEditing(saved);
      setDraft(disciplineToDraft(saved));
      setSavedDraft(disciplineToDraft(saved));
      prefills.clear();
      if (image) {
        const imageBody = new FormData();
        imageBody.append("hero_image", image);
        saved = await apiRequest<DisciplineRow>(`/catalog/admin/disciplines/${saved.id}/`, { method: "PATCH", headers: editorialHeaders(saved), body: imageBody }, token);
      }
      setEditing(saved);
      setDraft(disciplineToDraft(saved));
      setSavedDraft(disciplineToDraft(saved));
      setImage(null);
      setMessage(saved.editorial_revision
        ? `学科修改已保存（${new Date().toLocaleTimeString("zh-CN")}），仍在本页。读者看到的内容未改变，发布后才会更新。`
        : `学科资料已保存（${new Date().toLocaleTimeString("zh-CN")}），仍在本页。${saved.editorial_status === "published" ? "此学科已公开。" : "尚未公开。"}`);
      resource.refresh();
      return true;
    } catch (reason) {
      setEditConflict(isEditorialConflict(reason));
      setMessage(`${metadataSaved ? "文字资料已保存，图片未能保存；图片仍保留在本页，可重试。" : "填写尚未保存，输入已保留。"}${reason instanceof Error ? reason.message : "请稍后重试。"}`);
    } finally {
      finishAction("save-discipline");
    }
    return false;
  }

  return (
    <Frame eyebrow="知识管理" title="学科" description="社会学、人类学和民族学是初始数据。新增学科后，同一套理论、子学科、主题和馆藏关系会自动形成新的学科入口。">
      <div className="knowledge-admin-layout knowledge-admin-workspace">
        <section className="admin-panel knowledge-admin-list">
          <header><h2>学科列表</h2><button type="button" onClick={() => start()}><Plus size={15} />新增学科</button></header>
          {resource.loading ? <p>正在读取……</p> : null}<Notice>{resource.error}</Notice>
          {resource.data?.results.map((row) => (
            <article key={row.id}>
              <div className="knowledge-admin-thumb" style={row.hero_image ? { backgroundImage: `url("${row.hero_image}")` } : undefined}>{!row.hero_image ? row.name.slice(0, 1) : null}</div>
              <div><strong>{row.name}</strong><small>{row.foreign_name || row.code}</small><p>{row.description || "尚未填写说明"}</p></div>
              <dl><span>{row.counts.theories} 个理论</span><span>{row.counts.subdisciplines} 个子学科</span><span>{row.counts.topics} 个主题</span></dl>
              <button type="button" onClick={() => start(row)}><Pencil size={14} />编辑</button>
            </article>
          ))}
          <AdminListPages data={resource.data} paging={paging} loading={resource.loading} />
        </section>
        <div className="knowledge-object-editor-workspace">
        <form ref={editorRef} className="admin-panel knowledge-admin-editor knowledge-wide-editor" onSubmit={save}>
          <Notice>{requested.error}</Notice>
          <fieldset disabled={Boolean(pendingAction) || Boolean(requestedId && opened.current !== requestedId)} style={{ display: "contents" }}>
          <header><div><h2>{editing ? `编辑 ${editing.name}` : "新增学科"}</h2><p>保存本页名称、介绍和展示设置，不跳转。已有公开内容的修改会先保存，确认发布后才更新读者页面。</p></div></header>
          <EditorialPrefillNotice state={prefills} />
          <fieldset>
            <legend>基本信息</legend>
            <div className="knowledge-form-grid three">
              <label><span>标准中文名</span><input autoComplete="off" required value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
              <label><span>外文名称</span><input value={draft.foreign_name} onChange={(event) => setDraft({ ...draft, foreign_name: event.target.value })} /></label>
              <label><span>学科代码</span><input value={draft.code} onChange={(event) => setDraft({ ...draft, code: event.target.value })} placeholder="留空自动生成" /></label>
              <label><span>固定链接</span><input value={draft.slug} onChange={(event) => setDraft({ ...draft, slug: event.target.value })} placeholder="留空自动生成" /></label>
            </div>
            <CurationFieldAssistant hasUnsavedChanges={dirty}
              label="外文名称"
              authorityType="discipline"
              query={draft.foreign_name.trim() || draft.name}
              targetType="discipline"
              targetId={editing?.id}
              fieldName="foreign_name"
              currentValue={draft.foreign_name}
              onApply={(value, suggestion) => prefills.fill("", (current) => ({
                ...current,
                foreign_name: suggestion?.originalName || (typeof value === "string" ? value : current.foreign_name),
              }))}
              onAccepted={async () => {
                if (!editing) return;
                const updated = await apiRequest<DisciplineRow>(`/catalog/admin/disciplines/${editing.id}/`, {}, getServerSessionCredential());
                setEditing((current) => current?.id === updated.id ? updated : current);
                resource.refresh();
              }}
            />
            <StringListEditor label="检索别名" itemLabel="别名" value={editorLineValues(draft.search_aliases)} onChange={(value) => setDraft({ ...draft, search_aliases: value.join("\n") })} addLabel="添加别名" />
          </fieldset>
          <fieldset><legend>前台内容</legend><div className="knowledge-form-grid two"><label><span>卡片说明</span><textarea rows={5} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label><label><span>学科介绍</span><textarea rows={5} value={draft.introduction} onChange={(event) => setDraft({ ...draft, introduction: event.target.value })} /></label></div></fieldset>
          <fieldset><legend>展示与发布</legend><div className="knowledge-form-grid three"><label className="knowledge-image-upload"><ImagePlus size={19} /><span>{image?.name || (editing?.hero_image ? "替换现有主视觉" : "上传学科主视觉")}</span><input type="file" accept="image/*" onChange={(event) => setImage(event.target.files?.[0] ?? null)} /></label><label><span>排序</span><input type="number" value={draft.sort_order} onChange={(event) => setDraft({ ...draft, sort_order: Number(event.target.value) })} /></label><label><span>状态</span><select value={draft.editorial_status} onChange={(event) => setDraft({ ...draft, editorial_status: event.target.value })}><option value="draft">草稿</option><option value="published">公开</option><option value="archived">下线</option></select></label></div></fieldset>
          {editing ? <EntityLifecycleActions kind="discipline" id={editing.id} name={editing.name} status={draft.editorial_status} previewHref={`/theories/disciplines/${editing.slug}`} onChanged={(snapshot) => { setDraft((current) => ({ ...current, editorial_status: snapshot.status })); setEditing((current) => current ? { ...current, editorial_status: snapshot.status } : current); resource.refresh(); }} onDeleted={() => { setEditing(null); setDraft({ ...emptyDiscipline }); resource.refresh(); }} /> : null}
          <footer className="knowledge-editor-actions"><button className="button" type="submit"><Save size={15} />{draft.editorial_status === "published" && editing?.editorial_status !== "published" ? "保存并公开学科" : "保存本页学科资料"}</button><Notice>{message}</Notice></footer>
          <EditorialConflictHelp visible={editConflict} href={`/admin/disciplines?discipline=${editing?.id}`} />
          </fieldset>
        </form>
        <div className="knowledge-object-editor-rail">
          {editing ? <KnowledgeImagePanel objectType="discipline" objectId={editing.id} refreshKey={message} onChanged={() => void refreshImage()} /> : null}
          <KnowledgeObjectContextPanel
            hasUnsavedChanges={dirty}
            objectType="discipline"
            objectId={editing?.id}
            refreshKey={message}
            onChanged={resource.refresh}
          />
        </div>
        </div>
      </div>
    </Frame>
  );
}

type SubdisciplineRow = {
  id: string;
  name: string;
  foreign_name: string;
  slug: string;
  search_aliases?: string[];
  description: string;
  hero_image: string;
  discipline: string;
  parent: string | null;
  research_object: string;
  core_questions: string[];
  formation_period: string;
  research_directions: string[];
  methods: string[];
  representative_issues: string[];
  curation_level: number;
  editorial_status: string;
  editorial_revision?: {
    id: string;
    revision: number;
    status: string;
    changed_fields: string[];
    publish_url: string;
  };
};

type SubdisciplineDraft = {
  name: string;
  foreign_name: string;
  slug: string;
  search_aliases: string;
  description: string;
  discipline: string;
  parent: string;
  research_object: string;
  core_questions: string;
  formation_period: string;
  research_directions: string;
  methods: string;
  representative_issues: string;
  curation_level: number;
  editorial_status: string;
};

function emptySubdiscipline(discipline = ""): SubdisciplineDraft {
  return { name: "", foreign_name: "", slug: "", search_aliases: "", description: "", discipline, parent: "", research_object: "", core_questions: "", formation_period: "", research_directions: "", methods: "", representative_issues: "", curation_level: 0, editorial_status: "draft" };
}

function subdisciplineToDraft(row: SubdisciplineRow): SubdisciplineDraft {
  return {
    name: row.name || "",
    foreign_name: row.foreign_name || "",
    slug: row.slug || "",
    search_aliases: (row.search_aliases || []).join("\n"),
    description: row.description || "",
    discipline: row.discipline || "",
    parent: row.parent || "",
    research_object: row.research_object || "",
    core_questions: (row.core_questions || []).join("\n"),
    formation_period: row.formation_period || "",
    research_directions: (row.research_directions || []).join("\n"),
    methods: (row.methods || []).join("\n"),
    representative_issues: (row.representative_issues || []).join("\n"),
    curation_level: row.curation_level ?? 0,
    editorial_status: row.editorial_status || "draft",
  };
}

export function SubdisciplinesAdmin() {
  const paging = useAdminListPage();
  const [editConflict, setEditConflict] = useState(false);
  const opened = useRef("");
  const { pendingAction, startAction, finishAction } = useActionGuard();
  const searchParams = useSearchParams();
  const requestedSubdiscipline = searchParams.get("subdiscipline")?.trim() ?? "";
  const rows = useResource<Page<SubdisciplineRow>>(`/catalog/admin/subdisciplines/?page=${paging.page}`);
  const disciplines = useResource<Page<DisciplineRow>>("/catalog/admin/disciplines/");
  const requested = useResource<SubdisciplineRow>(
    requestedSubdiscipline
      ? `/catalog/admin/subdisciplines/${encodeURIComponent(requestedSubdiscipline)}/`
      : null,
  );
  const [editing, setEditing] = useState<SubdisciplineRow | null>(null);
  const [draft, setDraft] = useState<SubdisciplineDraft>(emptySubdiscipline());
  const [savedDraft, setSavedDraft] = useState<SubdisciplineDraft>(emptySubdiscipline());
  const [image, setImage] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [entityLabels, setEntityLabels] = useState<Record<string, string>>({});
  const editorRef = useRef<HTMLFormElement | null>(null);
  const dirty = useUnsavedForm({ draft, image: image?.name ?? null }, { draft: savedDraft, image: null });
  const prefills = useEditorialPrefills(editing?.id || "new-subdiscipline", draft, setDraft);
  async function refreshImage() {
    if (!editing) return;
    try {
      const updated = await apiRequest<SubdisciplineRow>(`/catalog/admin/subdisciplines/${editing.id}/`, {}, getServerSessionCredential());
      setEditing((current) => current?.id === updated.id ? updated : current);
      setMessage("图片修改已保存，当前文字填写保留。预览后可确认发布。"); rows.refresh();
    } catch (error) { setMessage(`图片操作后未能重新读取资料。请先重新打开当前子学科。${error instanceof Error ? error.message : ""}`); }
  }

  function start(row?: SubdisciplineRow) {
    if (dirty && !window.confirm("本子学科还有未保存的填写。放弃填写并切换吗？")) return;
    prefills.clear();
    setEditConflict(false);
    setEditing(row ?? null);
    setDraft(row ? subdisciplineToDraft(row) : emptySubdiscipline(disciplines.data?.results[0]?.id ?? ""));
    setSavedDraft(row ? subdisciplineToDraft(row) : emptySubdiscipline(disciplines.data?.results[0]?.id ?? ""));
    setImage(null);
    setMessage("");
    setEntityLabels({});
    window.requestAnimationFrame(() => editorRef.current?.scrollIntoView({ behavior: motionAwareScrollBehavior(), block: "start" }));
  }

  useEffect(() => {
    if (!requested.data || requested.data.id !== requestedSubdiscipline || opened.current === requestedSubdiscipline) return;
    const selected = requested.data;
    const timer = window.setTimeout(() => {
      if (dirty) { setMessage("已保留尚未保存的子学科填写。请先保存或从列表明确切换。"); return; }
      opened.current = requestedSubdiscipline;
      setEditing(selected);
      setDraft(subdisciplineToDraft(selected));
      setSavedDraft(subdisciplineToDraft(selected));
      setImage(null);
      setMessage("已打开所选子学科。");
      setEntityLabels({});
      window.requestAnimationFrame(() => editorRef.current?.scrollIntoView({ behavior: motionAwareScrollBehavior(), block: "start" }));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [requested.data, requestedSubdiscipline, dirty]);

  async function save(event?: FormEvent, draftOnly = false) {
    event?.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return false;
    if (!startAction("save-subdiscipline")) return false;
    if (!draftOnly && draft.editorial_status === "published" && editing?.editorial_status !== "published" && !window.confirm("保存并公开这个子学科？读者将能看到本页资料。")) { finishAction("save-subdiscipline"); return false; }
    setEditConflict(false);
    let metadataSaved = false;
    try {
      let saved = await apiRequest<SubdisciplineRow>(
        `/catalog/admin/subdisciplines/${editing ? `${editing.id}/` : ""}`,
        {
          method: editing ? "PATCH" : "POST",
          headers: editing ? editorialHeaders(editing) : undefined,
          body: JSON.stringify({
            name: draft.name,
            foreign_name: draft.foreign_name,
            slug: draft.slug,
            search_aliases: lineValues(draft.search_aliases),
            description: draft.description,
            discipline: draft.discipline,
            parent: draft.parent || null,
            research_object: draft.research_object,
            formation_period: draft.formation_period,
            core_questions: lineValues(draft.core_questions),
            research_directions: lineValues(draft.research_directions),
            methods: lineValues(draft.methods),
            representative_issues: lineValues(draft.representative_issues),
            curation_level: draft.curation_level,
            editorial_status: draftOnly ? (editing?.editorial_status ?? "draft") : draft.editorial_status,
          }),
        },
        token,
      );
      metadataSaved = true;
      setEditing(saved);
      setDraft(subdisciplineToDraft(saved));
      setSavedDraft(subdisciplineToDraft(saved));
      prefills.clear();
      if (image) {
        const imageBody = new FormData();
        imageBody.append("hero_image", image);
        saved = await apiRequest<SubdisciplineRow>(`/catalog/admin/subdisciplines/${saved.id}/`, { method: "PATCH", headers: editorialHeaders(saved), body: imageBody }, token);
      }
      setEditing(saved);
      setDraft(subdisciplineToDraft(saved));
      setSavedDraft(subdisciplineToDraft(saved));
      setImage(null);
      setMessage(saved.editorial_revision
        ? `子学科修改已保存（${new Date().toLocaleTimeString("zh-CN")}），仍在本页。读者页面未改变，发布后才更新。`
        : `子学科资料已保存（${new Date().toLocaleTimeString("zh-CN")}），仍在本页。${saved.editorial_status === "published" ? "此子学科已公开。" : "尚未公开。"}`);
      rows.refresh();
      return true;
    } catch (reason) { setEditConflict(isEditorialConflict(reason)); setMessage(`${metadataSaved ? "文字已保存，图片未能保存；请重试图片保存。" : "填写尚未保存，输入已保留。"}${reason instanceof Error ? reason.message : "请稍后重试。"}`); }
    finally { finishAction("save-subdiscipline"); }
    return false;
  }

  const disciplineName = (id: string) => disciplines.data?.results.find((item) => item.id === id)?.name || "未归类";
  const subdisciplineName = (id: string) => rows.data?.results.find((item) => item.id === id)?.name || entityLabels[id] || "已选择子学科";
  return (
    <Frame eyebrow="知识管理" title="子学科" description="子学科属于学科，但不作为理论传统的上下级。理论与子学科通过经过审核的关系表连接。">
      <div className="knowledge-admin-layout knowledge-admin-workspace">
        <section className="admin-panel knowledge-admin-list"><header><h2>子学科列表</h2><button type="button" onClick={() => start()}><Plus size={15} />新增子学科</button></header><Notice>{rows.error}</Notice>{rows.data?.results.map((row) => <article key={row.id}><div className="knowledge-admin-thumb">{row.name.slice(0, 2)}</div><div><strong>{row.name}</strong><small>{disciplineName(row.discipline)}</small><p>{row.research_object || row.description || "研究对象待编辑"}</p></div><button type="button" onClick={() => start(row)}><Pencil size={14} />编辑</button></article>)}<AdminListPages data={rows.data} paging={paging} loading={rows.loading} /></section>
        <div className="knowledge-object-editor-workspace">
        <form ref={editorRef} className="admin-panel knowledge-admin-editor knowledge-wide-editor" onSubmit={save}>
          <header><div><h2>{editing ? `编辑 ${editing.name}` : "新增子学科"}</h2><p>保存本页名称、说明和所属学科，不跳转。与理论的关联在关系管理中维护。已有公开内容的修改需另行发布。</p></div></header>
          <EditorialPrefillNotice state={prefills} />
          <Notice>{requested.error}</Notice>
          <fieldset disabled={Boolean(pendingAction) || Boolean(requestedSubdiscipline && opened.current !== requestedSubdiscipline)} style={{ display: "contents" }}>
          <fieldset>
            <legend>基本信息</legend>
            <div className="knowledge-form-grid three">
              <label><span>标准名称</span><input autoComplete="off" required value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
              <label><span>外文名称</span><input value={draft.foreign_name} onChange={(event) => setDraft({ ...draft, foreign_name: event.target.value })} /></label>
              <label><span>固定链接</span><input value={draft.slug} onChange={(event) => setDraft({ ...draft, slug: event.target.value })} placeholder="留空自动生成" /></label>
              <ResearchEntityPicker label="所属学科" endpoint="/catalog/admin/disciplines/" entityType="discipline" step="maintenance_subdisciplines" field="discipline" values={onePickerValue(draft.discipline, entityLabels[draft.discipline] || disciplineName(draft.discipline))} onChange={(next) => { const selected = next.at(-1); setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, discipline: selected?.id ?? "", parent: "" }); }} />
              <ResearchEntityPicker label="上级子学科" endpoint="/catalog/admin/subdisciplines/" entityType="subdiscipline" step="maintenance_subdisciplines" field="parent" values={onePickerValue(draft.parent, subdisciplineName(draft.parent))} onChange={(next) => { const selected = next.at(-1); if (selected?.id === editing?.id) return; setEntityLabels((current) => ({ ...current, ...pickerLabels(next) })); setDraft({ ...draft, parent: selected?.id ?? "" }); }} />
              <label><span>形成时期</span><input value={draft.formation_period} onChange={(event) => setDraft({ ...draft, formation_period: event.target.value })} /></label>
            </div>
            <CurationFieldAssistant hasUnsavedChanges={dirty}
              label="外文名称"
              authorityType="subdiscipline"
              query={draft.foreign_name.trim() || draft.name}
              targetType="subdiscipline"
              targetId={editing?.id}
              fieldName="foreign_name"
              currentValue={draft.foreign_name}
              onApply={(value, suggestion) => prefills.fill("", (current) => ({
                ...current,
                foreign_name: suggestion?.originalName || (typeof value === "string" ? value : current.foreign_name),
              }))}
              onAccepted={async () => {
                if (!editing) return;
                const updated = await apiRequest<SubdisciplineRow>(`/catalog/admin/subdisciplines/${editing.id}/`, {}, getServerSessionCredential());
                setEditing((current) => current?.id === updated.id ? updated : current);
                rows.refresh(); disciplines.refresh();
              }}
            />
            <StringListEditor label="检索别名" itemLabel="别名" value={editorLineValues(draft.search_aliases)} onChange={(value) => setDraft({ ...draft, search_aliases: value.join("\n") })} addLabel="添加别名" />
          </fieldset>
          <fieldset>
            <legend>研究内容</legend>
            <div className="knowledge-form-grid two">
              <label><span>页面说明</span><textarea rows={4} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
              <label><span>研究对象</span><textarea rows={4} value={draft.research_object} onChange={(event) => setDraft({ ...draft, research_object: event.target.value })} /></label>
            </div>
            <div className="structured-editor-pair">
              <StringListEditor label="核心问题" itemLabel="问题" value={editorLineValues(draft.core_questions)} onChange={(value) => setDraft({ ...draft, core_questions: value.join("\n") })} addLabel="添加问题" />
              <StringListEditor label="主要研究方向" itemLabel="方向" value={editorLineValues(draft.research_directions)} onChange={(value) => setDraft({ ...draft, research_directions: value.join("\n") })} addLabel="添加方向" />
              <StringListEditor label="常用方法" itemLabel="方法" value={editorLineValues(draft.methods)} onChange={(value) => setDraft({ ...draft, methods: value.join("\n") })} addLabel="添加方法" />
              <StringListEditor label="代表性议题" itemLabel="议题" value={editorLineValues(draft.representative_issues)} onChange={(value) => setDraft({ ...draft, representative_issues: value.join("\n") })} addLabel="添加议题" />
            </div>
          </fieldset>
          <fieldset><legend>展示与发布</legend><div className="knowledge-form-grid three"><label className="knowledge-image-upload"><ImagePlus size={19} /><span>{image?.name || (editing?.hero_image ? "选择替换图片，发布后生效" : "上传子学科主视觉")}</span><input type="file" accept="image/*" onChange={(event) => setImage(event.target.files?.[0] ?? null)} /></label><label><span>人工整理等级</span><input type="number" min={0} value={draft.curation_level} onChange={(event) => setDraft({ ...draft, curation_level: Number(event.target.value) })} /></label><label><span>状态</span><select value={draft.editorial_status} onChange={(event) => setDraft({ ...draft, editorial_status: event.target.value })}><option value="draft">草稿</option><option value="published">公开</option><option value="archived">下线</option></select></label></div></fieldset>
          {editing ? <EntityLifecycleActions kind="subdiscipline" id={editing.id} name={editing.name} status={draft.editorial_status} previewHref={`/subdisciplines/${editing.slug}`} onChanged={(snapshot) => { setDraft((current) => ({ ...current, editorial_status: snapshot.status })); setEditing((current) => current ? { ...current, editorial_status: snapshot.status } : current); rows.refresh(); }} onDeleted={() => { setEditing(null); setDraft(emptySubdiscipline(disciplines.data?.results[0]?.id ?? "")); rows.refresh(); }} /> : null}
          <footer className="knowledge-editor-actions"><button className="button" type="submit" disabled={Boolean(pendingAction)}><Save size={15} />{draft.editorial_status === "published" && editing?.editorial_status !== "published" ? "保存并公开子学科" : "保存本页子学科资料"}</button><Notice>{message}</Notice></footer>
          <EditorialConflictHelp visible={editConflict} href={`/admin/subdisciplines?subdiscipline=${editing?.id}`} />
          </fieldset>
        </form>
        <div className="knowledge-object-editor-rail">
          {editing ? <KnowledgeImagePanel objectType="subdiscipline" objectId={editing.id} refreshKey={message} onChanged={() => void refreshImage()} /> : null}
          <KnowledgeObjectContextPanel hasUnsavedChanges={dirty} objectType="subdiscipline" objectId={editing?.id} refreshKey={message} onChanged={() => { rows.refresh(); setEditConflict(true); setMessage("公开内容已更新。继续编辑前，请重新打开本子学科；本页输入仍保留。"); }} />
        </div>
        </div>
      </div>
    </Frame>
  );
}

type Candidate = { id: string; title?: string; name?: string; preferred_name?: string; slug?: string; document_type?: string; editorial_status?: string };
type RecommendationPreview = { placement: string; source: string; preview_token: string; expected_updated_at: string; expected_snapshot_id: string | null; items: Array<{ id: string; name: string; target_type: string }> };
type RecommendationPolicy = { id: string; placement: string; title: string; item_count: number; rotation_days: number; enabled: boolean; updated_at: string; last_generated_at: string | null; next_refresh_at: string | null; current: null | { id: string; source: string; starts_at: string; expires_at: string; items: { id: string; reason: string; target: { id: string; title?: string; name?: string }; target_type: string }[] } };
const targetByPlacement: Record<string, "work" | "theory_school" | "topic" | "scholar"> = { home_featured: "work", home_random: "work", theory_weekly: "work", home_theories: "theory_school", home_topics: "topic", home_scholars: "scholar" };

export function RecommendationsAdmin() {
  const [preview, setPreview] = useState<RecommendationPreview | null>(null);
  const publishingRequest=useRef(false);
  const retryRequest = useRef<{ signature: string; body: Record<string, unknown> } | null>(null);
  const [publishing,setPublishing]=useState(false);
  const policies = useResource<RecommendationPolicy[]>("/catalog/admin/recommendations/");
  const [scholarSearchDraft, setScholarSearchDraft] = useState("");
  const [scholarSearch, setScholarSearch] = useState("");
  const [scholarPage, setScholarPage] = useState(1);
  const scholarQuery = new URLSearchParams({
    editorial_status: "published",
    page: String(scholarPage),
  });
  if (scholarSearch) scholarQuery.set("search", scholarSearch);
  const [selectedPolicy, setSelectedPolicy] = useState<string>("");
  const [manualSelections, setManualSelections] = useState<Record<string, string[]>>({});
  const [selectionLabels, setSelectionLabels] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const policy = policies.data?.find((item) => item.placement === selectedPolicy) ?? policies.data?.[0];
  const selectionKey = policy?.id ?? "";
  const currentSelection = policy?.current?.items
    .filter((item) => (
      policy.placement !== "home_scholars"
      || policy.current?.source !== "manual"
      || item.reason === "管理员策展"
    ))
    .map((item) => item.target.id) ?? [];
  const selected = manualSelections[selectionKey] ?? currentSelection;
  const updateSelected = (updater: (current: string[]) => string[]) => {
    if (!selectionKey) return;
    setManualSelections((current) => ({
      ...current,
      [selectionKey]: updater(current[selectionKey] ?? currentSelection),
    }));
  };
  const targetType = policy ? targetByPlacement[policy.placement] : "work";
  const candidateEndpoint = targetType === "work" ? "/catalog/works/" : targetType === "theory_school" ? "/catalog/admin/theory-schools/" : targetType === "topic" ? "/catalog/admin/topics/" : "/catalog/admin/scholars/";
  const candidateResource = useResource<Page<Candidate>>(`${candidateEndpoint}?${scholarQuery.toString()}`);
  const candidates = candidateResource.data?.results;
  const visibleCandidates = candidates?.filter((item) => !item.editorial_status || item.editorial_status === "published");
  const selectedSet = new Set(selected);
  const selectionNameById = new Map<string, string>();
  policy?.current?.items.forEach((item) => {
    selectionNameById.set(item.target.id, item.target.title || item.target.name || item.target.id);
  });
  visibleCandidates?.forEach((item) => {
    selectionNameById.set(item.id, item.title || item.name || item.preferred_name || item.id);
  });
  Object.entries(selectionLabels).forEach(([id, label]) => selectionNameById.set(id, label));

  function moveSelected(index: number, offset: -1 | 1) {
    updateSelected((current) => {
      const targetIndex = index + offset;
      if (targetIndex < 0 || targetIndex >= current.length) return current;
      const next = [...current];
      [next[index], next[targetIndex]] = [next[targetIndex], next[index]];
      return next;
    });
  }

  function submitScholarSearch(event: FormEvent) {
    event.preventDefault();
    setScholarPage(1);
    setScholarSearch(scholarSearchDraft.trim());
  }

  async function refresh(manual: boolean, confirmedPreview?: RecommendationPreview) {
    if (!policy || publishingRequest.current) return;
    const token = getServerSessionCredential();
    if (!token) return;
    if (!confirmedPreview) {
      publishingRequest.current = true; setPublishing(true); setPreview(null);
      try {
        const result = await apiRequest<RecommendationPreview>(`/catalog/admin/recommendations/${policy.placement}/preview/`, { method: "POST", body: JSON.stringify(manual ? { items: selected.map((id) => ({ target_type: targetType, id })) } : {}) }, token);
        setPreview(result); setMessage("新推荐已生成预览，读者页面没有改变。请核对下面的完整名单，再确认发布。");
      } catch (reason) { setMessage(reason instanceof Error ? reason.message : "预览未能生成，当前推荐未改变。"); }
      finally { publishingRequest.current = false; setPublishing(false); }
      return;
    }
    if (!window.confirm("发布下面预览的这一组推荐？确认后读者页面才会更新。")) return;
    publishingRequest.current=true;
    setPublishing(true);
    const items = manual ? selected.map((id) => ({ target_type: targetType, id })) : undefined;
    const signature = JSON.stringify({ placement: policy.placement, items, preview_token: confirmedPreview.preview_token });
    if (retryRequest.current?.signature !== signature) {
      retryRequest.current = { signature, body: {
        confirm: true, request_key: createRequestKey(),
        expected_snapshot_id: confirmedPreview.expected_snapshot_id, expected_updated_at: confirmedPreview.expected_updated_at,
        preview_token: confirmedPreview.preview_token,
        ...(manual ? { items } : {}),
      } };
    }
    try {
      const result = await apiRequest<RecommendationPolicy & { publication_effective: boolean }>(`/catalog/admin/recommendations/${policy.placement}/refresh/`, { method: "POST", body: JSON.stringify(retryRequest.current.body) }, token);
      retryRequest.current = null;
      setPreview(null);
      setMessage(result.publication_effective
        ? `推荐已发布，读者现在可以看到。下次自动更新：${result.next_refresh_at ? new Date(result.next_refresh_at).toLocaleString("zh-CN") : "尚未安排"}。`
        : "这次操作已完成，但当前推荐已发生后续变化。请查看读者现在看到的推荐。");
      policies.refresh();
      setManualSelections((current) => {
        const next = { ...current };
        delete next[selectionKey];
        return next;
      });
    } catch (reason) {
      if (reason instanceof ApiRequestError && reason.status >= 400 && reason.status < 500) {
        retryRequest.current = null;
        policies.refresh();
        setMessage(reason.message);
      } else {
        setMessage("暂时未能确认发布结果。网络恢复后可再次点击同一按钮，本次重试不会重复更换推荐。");
      }
    }
    finally { publishingRequest.current=false; setPublishing(false); }
  }

  return (
    <Frame eyebrow="公开展示" title="推荐管理" description="先选展示位置，再选择和排序推荐内容。所有读者看到同一组推荐，确认发布后生效。">
      {policies.error || candidateResource.error ? <p role="alert">{policies.error || candidateResource.error}<button type="button" onClick={() => { policies.refresh(); candidateResource.refresh(); }}>重新读取推荐</button></p> : null}
      <div className="recommendation-admin-layout">
        <nav className="admin-panel recommendation-policy-list">{policies.data?.map((item) => {
          const hasAutomaticFill = item.current?.items.some((entry) => entry.reason === "三天自动补足");
          const sourceLabel = item.current?.source === "manual"
            ? hasAutomaticFill ? "人工优先" : "人工选择"
            : "自动推荐";
          return <button className={item.placement === policy?.placement ? "active" : ""} type="button" disabled={publishing} onClick={() => { setSelectedPolicy(item.placement); setScholarPage(1); setScholarSearch(""); setScholarSearchDraft(""); }} key={item.id}><strong>{item.title}</strong><small>{sourceLabel} · {item.item_count} 项</small><ArrowRight size={15} /></button>;
        })}</nav>
        <section className="admin-panel recommendation-editor">
          <header><div><h2>{policy?.title || "推荐位置"}</h2><p>下一次自动更新 {policy?.next_refresh_at ? new Date(policy.next_refresh_at).toLocaleString("zh-CN") : "待生成"}</p></div><button type="button" disabled={publishing} onClick={() => void refresh(false)}><RefreshCw size={15} />预览新一组推荐</button></header>
          {preview?.placement === policy?.placement ? <section className="admin-panel" aria-label="待发布推荐预览"><h3>准备发布的推荐</h3><p>这份预览包含自动补足的内容，15分钟内有效。发布前不会改变读者页面。</p><ol>{preview?.items.map((item) => <li key={item.id}>{item.name}</li>)}</ol>{!preview?.items.length ? <p>没有符合当前规则的公开内容。</p> : null}<button className="button" type="button" disabled={publishing || !preview || preview.expected_updated_at !== policy?.updated_at} onClick={() => preview && void refresh(preview.source === "manual", preview)}>确认发布这一组</button>{preview?.expected_updated_at !== policy?.updated_at ? <p>推荐规则已改变，请重新预览。</p> : null}</section> : null}
          <details className="recommendation-current"><summary>查看读者现在看到的推荐</summary>{policy?.current?.items.map((item, index) => <div key={item.id}><span>{String(index + 1).padStart(2, "0")}</span><strong>{item.target.title || item.target.name}</strong><small>{item.reason === "管理员策展" ? "人工指定" : item.reason === "三天自动补足" ? "自动补位" : "自动轮换"}</small></div>)}{!policy?.current?.items.length ? <p>还没有推荐内容。</p> : null}</details>
          <h3>人工选择与排序</h3>
          <p className="admin-help">选择最多 {policy?.item_count || 4} 项。此处顺序就是公开展示顺序。{policy?.placement === "home_scholars" ? "不足数量由系统从公开学者中自动补足。" : ""}</p>
          <div className="recommendation-selected-order">
            {selected.map((id, index) => (
              <div key={id}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{selectionNameById.get(id) || id}</strong>
                <div>
                  <button type="button" aria-label={`上移${selectionNameById.get(id) || "推荐项"}`} disabled={publishing || index === 0} onClick={() => moveSelected(index, -1)}><ArrowUp size={14} /></button>
                  <button type="button" aria-label={`下移${selectionNameById.get(id) || "推荐项"}`} disabled={publishing || index === selected.length - 1} onClick={() => moveSelected(index, 1)}><ArrowDown size={14} /></button>
                  <button type="button" aria-label={`移除${selectionNameById.get(id) || "推荐项"}`} disabled={publishing} onClick={() => updateSelected((current) => current.filter((itemId) => itemId !== id))}><Trash2 size={14} /></button>
                </div>
              </div>
            ))}
            {!selected.length ? <p>尚未选择推荐项。</p> : null}
          </div>
            <form className="recommendation-candidate-search" onSubmit={submitScholarSearch}>
              <label><span>{targetType === "scholar" ? "搜索公开学者" : "搜索可推荐内容"}</span><input type="search" value={scholarSearchDraft} onChange={(event) => setScholarSearchDraft(event.target.value)} placeholder="输入名称查找…" /></label>
              <button type="submit">搜索</button>
            </form>
          {candidateResource.loading ? <p role="status">正在读取可推荐内容…</p> : null}
          <div className="recommendation-candidates" aria-busy={candidateResource.loading}>{visibleCandidates?.map((item) => {
            const checked = selectedSet.has(item.id);
            const label = item.title || item.name || item.preferred_name || item.id;
            return <label className={checked ? "selected" : ""} key={item.id}><input type="checkbox" checked={checked} disabled={publishing} onChange={() => {
              setSelectionLabels((current) => ({ ...current, [item.id]: label }));
              updateSelected((current) => checked ? current.filter((id) => id !== item.id) : current.length < (policy?.item_count || 4) ? current.concat(item.id) : current);
            }} /><span>{label}</span>{checked ? <Check size={15} /> : null}</label>;
          })}</div>
            <nav className="recommendation-candidate-pagination" aria-label={targetType === "scholar" ? "学者候选分页" : "可推荐内容分页"}>
              <button type="button" disabled={!candidateResource.data?.previous || scholarPage <= 1} onClick={() => setScholarPage((page) => Math.max(1, page - 1))}>上一页</button>
              <span>第 {scholarPage} 页，共 {candidateResource.data?.count ?? 0} 项</span>
              <button type="button" disabled={!candidateResource.data?.next} onClick={() => setScholarPage((page) => page + 1)}>下一页</button>
            </nav>
          <button className="button" type="button" disabled={!selected.length || publishing} onClick={() => void refresh(true)}><Save size={15} />{publishing ? "正在处理…" : "预览选中的推荐"}</button>
          <Notice>{message}</Notice>
        </section>
      </div>
    </Frame>
  );
}

type AboutBlock = { id: string; key: string; block_type: string; title: string; body: string; icon: string; action_label: string; action_href: string; sort_order: number; visible: boolean; configuration: Record<string, unknown> };
export function AboutAdmin() {
  const resource = useResource<Page<AboutBlock>>("/catalog/admin/about-blocks/");
  const [editing, setEditing] = useState<AboutBlock | null>(null);
  const [message, setMessage] = useState("");
  const current = editing ?? resource.data?.results[0] ?? null;
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!current) return;
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      const saved = await apiRequest<AboutBlock>(
        `/catalog/admin/about-blocks/${current.id}/`,
        { method: "PATCH", body: JSON.stringify(current) },
        token,
      );
      setEditing(saved);
      setMessage("关于书库页面已经更新。动态统计值保持由馆藏数据实时计算。");
      resource.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "保存失败");
    }
  }
  return (
    <Frame eyebrow="网站内容" title="关于书库" description="可见文字、图标、步骤、入口和显示顺序均由固定区块控制。统计值、更新时间和版本号由系统实时读取，标签仍可在这里修改。">
      <div className="knowledge-admin-layout">
        <nav className="admin-panel about-block-list">
          {resource.data?.results.map((row) => <button className={current?.id === row.id ? "active" : ""} type="button" onClick={() => setEditing({ ...row })} key={row.id}><strong>{row.title || row.key}</strong><small>{row.block_type} · {row.visible ? "显示" : "隐藏"}</small><Pencil size={14} /></button>)}
        </nav>
        {current ? (
          <form className="admin-panel knowledge-admin-editor" onSubmit={save}>
            <header><h2>{current.title || current.key}</h2></header>
            <label><span>固定区块</span><input value={current.key} disabled /></label>
            <div className="inline-fields">
              <label><span>区块类型</span><select value={current.block_type} onChange={(event) => setEditing({ ...current, block_type: event.target.value })}><option value="intro">简介</option><option value="stat">动态数据</option><option value="feature">功能</option><option value="process">入库步骤</option><option value="principle">开放原则</option><option value="notice">提示</option><option value="action">操作入口</option><option value="footer">辅助文字</option></select></label>
              <label><span>图标</span><select value={current.icon} onChange={(event) => setEditing({ ...current, icon: event.target.value })}><option value="">无图标</option><option value="search">搜索</option><option value="book-open">阅读</option><option value="network">知识关系</option><option value="highlighter">标注</option><option value="refresh">更新</option><option value="users">学者</option></select></label>
            </div>
            <label><span>页面标题或数据标签</span><input value={current.title} onChange={(event) => setEditing({ ...current, title: event.target.value })} /></label>
            <label><span>正文或步骤</span><textarea rows={8} value={current.body} onChange={(event) => setEditing({ ...current, body: event.target.value })} /></label>
            <label><span>补充说明</span><textarea rows={3} value={String(current.configuration.description ?? "")} onChange={(event) => setEditing({ ...current, configuration: { ...current.configuration, description: event.target.value } })} /></label>
            <div className="inline-fields"><label><span>按钮文字</span><input value={current.action_label} onChange={(event) => setEditing({ ...current, action_label: event.target.value })} /></label><label><span>按钮链接</span><input value={current.action_href} onChange={(event) => setEditing({ ...current, action_href: event.target.value })} /></label></div>
            <div className="inline-fields"><label><span>顺序</span><input type="number" value={current.sort_order} onChange={(event) => setEditing({ ...current, sort_order: Number(event.target.value) })} /></label><label className="switch-row"><input type="checkbox" checked={current.visible} onChange={(event) => setEditing({ ...current, visible: event.target.checked })} /><span>公开显示</span></label></div>
            <button className="button" type="submit"><Save size={15} />保存页面内容</button><Notice>{message}</Notice>
          </form>
        ) : null}
      </div>
    </Frame>
  );
}
