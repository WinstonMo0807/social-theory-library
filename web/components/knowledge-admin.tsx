"use client";

import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  CalendarDays,
  Check,
  ImagePlus,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { EntityLifecycleActions } from "@/components/entity-lifecycle-actions";
import { AuthoritySuggestions, StringListEditor } from "@/components/structured-editors";
import { FieldEnrichmentControl } from "@/components/field-enrichment-control";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

type Page<T> = { count: number; results: T[]; next?: string | null; previous?: string | null };

function useResource<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => {
    setLoading(true);
    setRevision((value) => value + 1);
  }, []);
  useEffect(() => {
    let active = true;
    const token = getServerSessionCredential();
    if (!token) return;
    apiRequest<T>(path, {}, token)
      .then((payload) => { if (active) { setData(payload); setError(""); } })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "读取失败"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [path, revision]);
  return { data, error, loading, refresh };
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
  const resource = useResource<Page<DisciplineRow>>("/catalog/admin/disciplines/");
  const [editing, setEditing] = useState<DisciplineRow | null>(null);
  const [draft, setDraft] = useState(emptyDiscipline);
  const [image, setImage] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const editorRef = useRef<HTMLFormElement | null>(null);

  function start(row?: DisciplineRow) {
    setEditing(row ?? null);
    setDraft(row ? disciplineToDraft(row) : { ...emptyDiscipline });
    setImage(null);
    setMessage("");
    window.requestAnimationFrame(() => editorRef.current?.scrollIntoView({ behavior: motionAwareScrollBehavior(), block: "start" }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      let saved = await apiRequest<DisciplineRow>(
        `/catalog/admin/disciplines/${editing ? `${editing.id}/` : ""}`,
        {
          method: editing ? "PATCH" : "POST",
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
            editorial_status: draft.editorial_status,
          }),
        },
        token,
      );
      if (image) {
        const imageBody = new FormData();
        imageBody.append("hero_image", image);
        saved = await apiRequest<DisciplineRow>(`/catalog/admin/disciplines/${saved.id}/`, { method: "PATCH", body: imageBody }, token);
      }
      setEditing(saved);
      setDraft(disciplineToDraft(saved));
      setImage(null);
      setMessage("学科已经保存。理论传统、子学科、主题和统计会按关系自动生成。");
      resource.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "保存失败");
    }
  }

  return (
    <Frame eyebrow="知识矩阵" title="学科" description="社会学、人类学和民族学是初始数据。新增学科后，同一套理论、子学科、主题和馆藏关系会自动形成新的学科入口。">
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
        </section>
        <form ref={editorRef} className="admin-panel knowledge-admin-editor knowledge-wide-editor" onSubmit={save}>
          <header><div><h2>{editing ? `编辑 ${editing.name}` : "新增学科"}</h2><p>前台学科入口、统计和关联内容由这里的规范实体自动生成。</p></div></header>
          <fieldset>
            <legend>基本信息</legend>
            <div className="knowledge-form-grid three">
              <label><span>标准中文名</span><input autoComplete="off" required value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
              <label><span>外文名称</span><input value={draft.foreign_name} onChange={(event) => setDraft({ ...draft, foreign_name: event.target.value })} /></label>
              <label><span>学科代码</span><input value={draft.code} onChange={(event) => setDraft({ ...draft, code: event.target.value })} placeholder="留空自动生成" /></label>
              <label><span>固定链接</span><input value={draft.slug} onChange={(event) => setDraft({ ...draft, slug: event.target.value })} placeholder="留空自动生成" /></label>
            </div>
            <AuthoritySuggestions
              entityType="discipline"
              query={draft.foreign_name.trim() || draft.name}
            />
            <FieldEnrichmentControl
              targetType="discipline"
              targetId={editing?.id}
              title="学科字段核对"
              fields={[{ name: "foreign_name", label: "外文名称", currentValue: draft.foreign_name }]}
              onAccepted={resource.refresh}
            />
            <StringListEditor label="检索别名" itemLabel="别名" value={editorLineValues(draft.search_aliases)} onChange={(value) => setDraft({ ...draft, search_aliases: value.join("\n") })} addLabel="添加别名" />
          </fieldset>
          <fieldset><legend>前台内容</legend><div className="knowledge-form-grid two"><label><span>卡片说明</span><textarea rows={5} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label><label><span>学科介绍</span><textarea rows={5} value={draft.introduction} onChange={(event) => setDraft({ ...draft, introduction: event.target.value })} /></label></div></fieldset>
          <fieldset><legend>展示与发布</legend><div className="knowledge-form-grid three"><label className="knowledge-image-upload"><ImagePlus size={19} /><span>{image?.name || (editing?.hero_image ? "替换现有主视觉" : "上传学科主视觉")}</span><input type="file" accept="image/*" onChange={(event) => setImage(event.target.files?.[0] ?? null)} /></label><label><span>排序</span><input type="number" value={draft.sort_order} onChange={(event) => setDraft({ ...draft, sort_order: Number(event.target.value) })} /></label><label><span>状态</span><select value={draft.editorial_status} onChange={(event) => setDraft({ ...draft, editorial_status: event.target.value })}><option value="draft">草稿</option><option value="published">公开</option><option value="archived">下线</option></select></label></div></fieldset>
          {editing ? <EntityLifecycleActions kind="discipline" id={editing.id} name={editing.name} status={draft.editorial_status} previewHref={`/theories/disciplines/${editing.slug}`} onChanged={(snapshot) => { setDraft((current) => ({ ...current, editorial_status: snapshot.status })); setEditing((current) => current ? { ...current, editorial_status: snapshot.status } : current); resource.refresh(); }} onDeleted={() => { setEditing(null); setDraft({ ...emptyDiscipline }); resource.refresh(); }} /> : null}
          <footer className="knowledge-editor-actions"><button className="button" type="submit"><Save size={15} />保存学科</button><Notice>{message}</Notice></footer>
        </form>
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
  const rows = useResource<Page<SubdisciplineRow>>("/catalog/admin/subdisciplines/");
  const disciplines = useResource<Page<DisciplineRow>>("/catalog/admin/disciplines/");
  const [editing, setEditing] = useState<SubdisciplineRow | null>(null);
  const [draft, setDraft] = useState<SubdisciplineDraft>(emptySubdiscipline());
  const [image, setImage] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const editorRef = useRef<HTMLFormElement | null>(null);

  function start(row?: SubdisciplineRow) {
    setEditing(row ?? null);
    setDraft(row ? subdisciplineToDraft(row) : emptySubdiscipline(disciplines.data?.results[0]?.id ?? ""));
    setImage(null);
    setMessage("");
    window.requestAnimationFrame(() => editorRef.current?.scrollIntoView({ behavior: motionAwareScrollBehavior(), block: "start" }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      let saved = await apiRequest<SubdisciplineRow>(
        `/catalog/admin/subdisciplines/${editing ? `${editing.id}/` : ""}`,
        {
          method: editing ? "PATCH" : "POST",
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
            editorial_status: draft.editorial_status,
          }),
        },
        token,
      );
      if (image) {
        const imageBody = new FormData();
        imageBody.append("hero_image", image);
        saved = await apiRequest<SubdisciplineRow>(`/catalog/admin/subdisciplines/${saved.id}/`, { method: "PATCH", body: imageBody }, token);
      }
      setEditing(saved);
      setDraft(subdisciplineToDraft(saved));
      setImage(null);
      setMessage("子学科已经保存。与理论和主题的关系仍需在关系审核区确认。");
      rows.refresh();
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "保存失败"); }
  }

  const disciplineName = (id: string) => disciplines.data?.results.find((item) => item.id === id)?.name || "未归类";
  return (
    <Frame eyebrow="知识矩阵" title="子学科" description="子学科属于学科，但不作为理论传统的上下级。理论与子学科通过经过审核的关系表连接。">
      <div className="knowledge-admin-layout knowledge-admin-workspace">
        <section className="admin-panel knowledge-admin-list"><header><h2>子学科列表</h2><button type="button" onClick={() => start()}><Plus size={15} />新增子学科</button></header><Notice>{rows.error}</Notice>{rows.data?.results.map((row) => <article key={row.id}><div className="knowledge-admin-thumb">{row.name.slice(0, 2)}</div><div><strong>{row.name}</strong><small>{disciplineName(row.discipline)}</small><p>{row.research_object || row.description || "研究对象待编辑"}</p></div><button type="button" onClick={() => start(row)}><Pencil size={14} />编辑</button></article>)}</section>
        <form ref={editorRef} className="admin-panel knowledge-admin-editor knowledge-wide-editor" onSubmit={save}>
          <header><div><h2>{editing ? `编辑 ${editing.name}` : "新增子学科"}</h2><p>子学科与理论传统分别维护。两者的关联由关系审核区管理。</p></div></header>
          <fieldset>
            <legend>规范信息</legend>
            <div className="knowledge-form-grid three">
              <label><span>标准名称</span><input autoComplete="off" required value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
              <label><span>外文名称</span><input value={draft.foreign_name} onChange={(event) => setDraft({ ...draft, foreign_name: event.target.value })} /></label>
              <label><span>固定链接</span><input value={draft.slug} onChange={(event) => setDraft({ ...draft, slug: event.target.value })} placeholder="留空自动生成" /></label>
              <label><span>所属学科</span><select required value={draft.discipline} onChange={(event) => setDraft({ ...draft, discipline: event.target.value, parent: "" })}><option value="">请选择</option>{disciplines.data?.results.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
              <label><span>上级子学科</span><select value={draft.parent} onChange={(event) => setDraft({ ...draft, parent: event.target.value })}><option value="">无</option>{rows.data?.results.filter((item) => item.id !== editing?.id && item.discipline === draft.discipline).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
              <label><span>形成时期</span><input value={draft.formation_period} onChange={(event) => setDraft({ ...draft, formation_period: event.target.value })} /></label>
            </div>
            <AuthoritySuggestions
              entityType="subdiscipline"
              query={draft.foreign_name.trim() || draft.name}
            />
            <FieldEnrichmentControl
              targetType="subdiscipline"
              targetId={editing?.id}
              title="子学科字段核对"
              fields={[{ name: "foreign_name", label: "外文名称", currentValue: draft.foreign_name }]}
              onAccepted={() => { rows.refresh(); disciplines.refresh(); }}
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
          <fieldset><legend>展示与发布</legend><div className="knowledge-form-grid three"><label className="knowledge-image-upload"><ImagePlus size={19} /><span>{image?.name || (editing?.hero_image ? "替换现有主视觉" : "上传子学科主视觉")}</span><input type="file" accept="image/*" onChange={(event) => setImage(event.target.files?.[0] ?? null)} /></label><label><span>策展等级</span><input type="number" min={0} value={draft.curation_level} onChange={(event) => setDraft({ ...draft, curation_level: Number(event.target.value) })} /></label><label><span>状态</span><select value={draft.editorial_status} onChange={(event) => setDraft({ ...draft, editorial_status: event.target.value })}><option value="draft">草稿</option><option value="published">公开</option><option value="archived">下线</option></select></label></div></fieldset>
          {editing ? <EntityLifecycleActions kind="subdiscipline" id={editing.id} name={editing.name} status={draft.editorial_status} previewHref={`/subdisciplines/${editing.slug}`} onChanged={(snapshot) => { setDraft((current) => ({ ...current, editorial_status: snapshot.status })); setEditing((current) => current ? { ...current, editorial_status: snapshot.status } : current); rows.refresh(); }} onDeleted={() => { setEditing(null); setDraft(emptySubdiscipline(disciplines.data?.results[0]?.id ?? "")); rows.refresh(); }} /> : null}
          <footer className="knowledge-editor-actions"><button className="button" type="submit"><Save size={15} />保存子学科</button><Notice>{message}</Notice></footer>
        </form>
      </div>
    </Frame>
  );
}

type Candidate = { id: string; title?: string; name?: string; preferred_name?: string; slug?: string; document_type?: string; editorial_status?: string };
type RecommendationPolicy = { id: string; placement: string; title: string; item_count: number; rotation_days: number; enabled: boolean; last_generated_at: string | null; next_refresh_at: string | null; current: null | { id: string; source: string; starts_at: string; expires_at: string; items: { id: string; reason: string; target: { id: string; title?: string; name?: string }; target_type: string }[] } };
const targetByPlacement: Record<string, "work" | "theory_school" | "topic" | "scholar"> = { home_featured: "work", home_random: "work", theory_weekly: "work", home_theories: "theory_school", home_topics: "topic", home_scholars: "scholar" };

export function RecommendationsAdmin() {
  const policies = useResource<RecommendationPolicy[]>("/catalog/admin/recommendations/");
  const works = useResource<Page<Candidate>>("/catalog/works/?ordering=-created_at&page_size=100");
  const theories = useResource<Page<Candidate>>("/catalog/admin/theory-schools/?page_size=100");
  const topics = useResource<Page<Candidate>>("/catalog/admin/topics/?page_size=100");
  const [scholarSearchDraft, setScholarSearchDraft] = useState("");
  const [scholarSearch, setScholarSearch] = useState("");
  const [scholarPage, setScholarPage] = useState(1);
  const scholarQuery = new URLSearchParams({
    editorial_status: "published",
    page: String(scholarPage),
  });
  if (scholarSearch) scholarQuery.set("search", scholarSearch);
  const scholars = useResource<Page<Candidate>>(`/catalog/admin/scholars/?${scholarQuery.toString()}`);
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
  const candidates = targetType === "work" ? works.data?.results : targetType === "theory_school" ? theories.data?.results : targetType === "topic" ? topics.data?.results : scholars.data?.results;
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

  async function refresh(manual: boolean) {
    if (!policy) return;
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      await apiRequest(`/catalog/admin/recommendations/${policy.placement}/refresh/`, { method: "POST", body: JSON.stringify(manual ? { items: selected.map((id) => ({ target_type: targetType, id })) } : {}) }, token);
      setMessage(manual ? "人工策展已发布，并从现在起重新计算三天周期。" : "系统已随机生成新一组推荐，并从现在起重新计算三天周期。");
      policies.refresh();
      setManualSelections((current) => {
        const next = { ...current };
        delete next[selectionKey];
        return next;
      });
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "更新失败"); }
  }

  return (
    <Frame eyebrow="全站策展" title="推荐管理" description="所有读者看到同一组推荐。系统每三天自动换组，管理员可以随时刷新或指定项目，人工选择优先。">
      <div className="recommendation-admin-layout">
        <nav className="admin-panel recommendation-policy-list">{policies.data?.map((item) => {
          const hasAutomaticFill = item.current?.items.some((entry) => entry.reason === "三天自动补足");
          const sourceLabel = item.current?.source === "manual"
            ? hasAutomaticFill ? "人工优先" : "人工策展"
            : "自动推荐";
          return <button className={item.placement === policy?.placement ? "active" : ""} type="button" onClick={() => setSelectedPolicy(item.placement)} key={item.id}><strong>{item.title}</strong><small>{sourceLabel} · {item.item_count} 项</small><ArrowRight size={15} /></button>;
        })}</nav>
        <section className="admin-panel recommendation-editor">
          <header><div><h2>{policy?.title || "推荐位置"}</h2><p>下一次自动更新 {policy?.next_refresh_at ? new Date(policy.next_refresh_at).toLocaleString("zh-CN") : "待生成"}</p></div><button type="button" onClick={() => void refresh(false)}><RefreshCw size={15} />立即随机换组</button></header>
          <div className="recommendation-current"><h3>当前公开组</h3>{policy?.current?.items.map((item, index) => <div key={item.id}><span>{String(index + 1).padStart(2, "0")}</span><strong>{item.target.title || item.target.name}</strong><small>{item.reason === "管理员策展" ? "人工指定" : item.reason === "三天自动补足" ? "自动补位" : "自动轮换"}</small></div>)}{!policy?.current?.items.length ? <p>尚未生成。</p> : null}</div>
          <h3>人工选择与排序</h3>
          <p className="admin-help">选择最多 {policy?.item_count || 4} 项。此处顺序就是公开展示顺序。{policy?.placement === "home_scholars" ? "不足数量由系统从公开学者中自动补足。" : ""}</p>
          <div className="recommendation-selected-order">
            {selected.map((id, index) => (
              <div key={id}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{selectionNameById.get(id) || id}</strong>
                <div>
                  <button type="button" aria-label={`上移${selectionNameById.get(id) || "推荐项"}`} disabled={index === 0} onClick={() => moveSelected(index, -1)}><ArrowUp size={14} /></button>
                  <button type="button" aria-label={`下移${selectionNameById.get(id) || "推荐项"}`} disabled={index === selected.length - 1} onClick={() => moveSelected(index, 1)}><ArrowDown size={14} /></button>
                  <button type="button" aria-label={`移除${selectionNameById.get(id) || "推荐项"}`} onClick={() => updateSelected((current) => current.filter((itemId) => itemId !== id))}><Trash2 size={14} /></button>
                </div>
              </div>
            ))}
            {!selected.length ? <p>尚未选择推荐项。</p> : null}
          </div>
          {targetType === "scholar" ? (
            <form className="recommendation-candidate-search" onSubmit={submitScholarSearch}>
              <label><span>搜索公开学者</span><input type="search" value={scholarSearchDraft} onChange={(event) => setScholarSearchDraft(event.target.value)} placeholder="中文名、外文名或译名" /></label>
              <button type="submit">搜索</button>
            </form>
          ) : null}
          <div className="recommendation-candidates">{visibleCandidates?.map((item) => {
            const checked = selectedSet.has(item.id);
            const label = item.title || item.name || item.preferred_name || item.id;
            return <label className={checked ? "selected" : ""} key={item.id}><input type="checkbox" checked={checked} onChange={() => {
              setSelectionLabels((current) => ({ ...current, [item.id]: label }));
              updateSelected((current) => checked ? current.filter((id) => id !== item.id) : current.length < (policy?.item_count || 4) ? current.concat(item.id) : current);
            }} /><span>{label}</span>{checked ? <Check size={15} /> : null}</label>;
          })}</div>
          {targetType === "scholar" ? (
            <nav className="recommendation-candidate-pagination" aria-label="学者候选分页">
              <button type="button" disabled={!scholars.data?.previous || scholarPage <= 1} onClick={() => setScholarPage((page) => Math.max(1, page - 1))}>上一页</button>
              <span>第 {scholarPage} 页，共 {scholars.data?.count ?? 0} 位</span>
              <button type="button" disabled={!scholars.data?.next} onClick={() => setScholarPage((page) => page + 1)}>下一页</button>
            </nav>
          ) : null}
          <button className="button" type="button" disabled={!selected.length} onClick={() => void refresh(true)}><Save size={15} />发布人工推荐</button>
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

type TimelineRow = { id: string; title: string; description: string; event_type: string; start_year: number | null; end_year: number | null; date_label: string; orientation: string; theory_school: string | null; discipline: string | null; evidence_page: number | null; evidence_text: string; review_status: string };
export function TimelineAdmin() {
  const events = useResource<Page<TimelineRow>>("/catalog/admin/theory-timeline/");
  const theories = useResource<Page<Candidate>>("/catalog/admin/theory-schools/?page_size=100");
  const disciplines = useResource<Page<DisciplineRow>>("/catalog/admin/disciplines/");
  const [draft, setDraft] = useState({ title: "", description: "", event_type: "development", start_year: "", end_year: "", date_label: "", orientation: "", theory_school: "", discipline: "", evidence_page: "", evidence_text: "", review_status: "suggested" });
  const [message, setMessage] = useState("");
  async function save(event: FormEvent) { event.preventDefault(); const token = getServerSessionCredential(); if (!token) return; const payload = { ...draft, start_year: draft.start_year ? Number(draft.start_year) : null, end_year: draft.end_year ? Number(draft.end_year) : null, evidence_page: draft.evidence_page ? Number(draft.evidence_page) : null, theory_school: draft.theory_school || null, discipline: draft.discipline || null }; try { await apiRequest("/catalog/admin/theory-timeline/", { method: "POST", body: JSON.stringify(payload) }, token); setMessage("时间轴事件已经保存。只有审核通过的事件会出现在前台。"); events.refresh(); } catch (reason) { setMessage(reason instanceof Error ? reason.message : "保存失败"); } }
  async function remove(id: string) { const token = getServerSessionCredential(); if (!token || !window.confirm("删除这条时间轴事件吗？")) return; await apiRequest(`/catalog/admin/theory-timeline/${id}/`, { method: "DELETE" }, token); events.refresh(); }
  return <Frame eyebrow="理论历史" title="时间轴事件" description="时间轴事件独立管理。出版年份、关键词共现和系统建议都不能直接公开，必须保留依据并由管理员确认。"><div className="knowledge-admin-layout"><section className="admin-panel timeline-admin-list"><header><h2>事件记录</h2><Link href="/theory-schools/timeline">查看前台 <ArrowRight size={14} /></Link></header>{events.data?.results.map((row) => <article key={row.id}><CalendarDays size={20} /><div><strong>{row.date_label || row.start_year || "时期待定"} · {row.title}</strong><p>{row.description}</p><small>{row.review_status === "approved" ? "已公开" : "待确认"}{row.evidence_page ? ` · 证据页 ${row.evidence_page}` : ""}</small></div><button type="button" aria-label={`删除时间轴事件：${row.title}`} onClick={() => void remove(row.id)}><Trash2 size={14} /></button></article>)}</section><form className="admin-panel knowledge-admin-editor" onSubmit={save}><header><h2>新增时间轴事件</h2></header><label><span>事件标题</span><input required value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label><span>说明</span><textarea rows={4} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label><div className="inline-fields"><label><span>开始年</span><input type="number" value={draft.start_year} onChange={(event) => setDraft({ ...draft, start_year: event.target.value })} /></label><label><span>结束年</span><input type="number" value={draft.end_year} onChange={(event) => setDraft({ ...draft, end_year: event.target.value })} /></label></div><label><span>显示时期</span><input value={draft.date_label} onChange={(event) => setDraft({ ...draft, date_label: event.target.value })} placeholder="例如 20世纪初至中期" /></label><div className="inline-fields"><label><span>理论传统</span><select value={draft.theory_school} onChange={(event) => setDraft({ ...draft, theory_school: event.target.value })}><option value="">无</option>{theories.data?.results.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label><span>学科</span><select value={draft.discipline} onChange={(event) => setDraft({ ...draft, discipline: event.target.value })}><option value="">无</option>{disciplines.data?.results.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label></div><label><span>证据页码</span><input type="number" value={draft.evidence_page} onChange={(event) => setDraft({ ...draft, evidence_page: event.target.value })} /></label><label><span>证据原文或来源说明</span><textarea rows={4} value={draft.evidence_text} onChange={(event) => setDraft({ ...draft, evidence_text: event.target.value })} /></label><label><span>审核状态</span><select value={draft.review_status} onChange={(event) => setDraft({ ...draft, review_status: event.target.value })}><option value="suggested">候选</option><option value="approved">确认并公开</option><option value="rejected">拒绝</option></select></label><button className="button" type="submit"><Save size={15} />保存事件</button><Notice>{message}</Notice></form></div></Frame>;
}
