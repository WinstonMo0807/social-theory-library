"use client";

import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Cloud,
  Database,
  Download,
  HardDrive,
  ImagePlus,
  LoaderCircle,
  LockKeyhole,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  Server,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { defaultSiteConfig, type SiteConfig } from "@/lib/site-config";
import { EntityRelationsAdmin } from "@/components/entity-relations-admin";
import { EntityLifecycleActions } from "@/components/entity-lifecycle-actions";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { FieldEnrichmentControl } from "@/components/field-enrichment-control";
import {
  AuthoritySuggestions,
  StringListEditor,
  StructuredRowsEditor,
  type StructuredRow,
} from "@/components/structured-editors";

type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

function useAdminResource<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (!path) {
      Promise.resolve().then(() => {
        setData(null);
        setError("");
        setLoading(false);
      });
      return;
    }
    const token = getServerSessionCredential();
    let active = true;
    if (!token) {
      Promise.resolve().then(() => {
        if (!active) return;
        setError("请先登录后台。");
        setLoading(false);
      });
      return () => {
        active = false;
      };
    }
    apiRequest<T>(path, {}, token)
      .then((payload) => {
        if (!active) return;
        setData(payload);
        setError("");
      })
      .catch((reason) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "数据加载失败。");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [path, revision]);

  return {
    data,
    error,
    loading,
    refresh: () => setRevision((value) => value + 1),
  };
}

type AdminUploadItem = {
  id: string;
  source_filename: string;
  status: string;
  stage_progress: number;
  error_message: string;
  replacement_of_asset: string | null;
  created_at: string;
  review_data: null | {
    title: string;
    document_type: "book" | "journal_article" | "thesis" | "report";
    publication_year: number | null;
    authors: string[];
    publication_state: string;
    ocr_status: string;
    semantic_index_status: string;
    page_label_status: string;
    public_slug: string | null;
  };
};

const documentLabels = {
  book: "图书",
  journal_article: "期刊论文",
  thesis: "学位论文",
  report: "研究报告",
};

const uploadStatusLabels: Record<string, string> = {
  received: "已接收",
  validating: "校验中",
  deduplicating: "查重中",
  extracting: "提取文本",
  ocr: "OCR 中",
  metadata: "识别元数据",
  linking: "建立关联",
  indexing: "建立索引",
  preparing_public_asset: "准备公开文件",
  syncing_cloud: "同步云端",
  ready: "可发布",
  published: "已发布",
  needs_review: "待复核",
  failed: "失败",
  withdrawn: "已下架",
  deleted: "已删除",
};

export function LibraryAdmin({ initialQuery = "" }: { initialQuery?: string }) {
  const [query, setQuery] = useState(initialQuery);
  const [submittedQuery, setSubmittedQuery] = useState(initialQuery);
  const [message, setMessage] = useState("");
  const [replacing, setReplacing] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<{ item: AdminUploadItem; type: "withdraw" | "delete" } | null>(null);
  const path = `/ingestion/items/?ordering=-created_at${submittedQuery ? `&search=${encodeURIComponent(submittedQuery)}` : ""}`;
  const resource = useAdminResource<Paginated<AdminUploadItem>>(path);

  async function action(item: AdminUploadItem, type: "retry" | "withdraw" | "delete") {
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      await apiRequest(
        `/ingestion/items/${item.id}/${type}/`,
        {
          method: "POST",
          body: type === "withdraw"
            ? JSON.stringify({ reason: "管理员从馆藏后台下架" })
            : type === "delete"
              ? JSON.stringify({ confirmed: true })
              : undefined,
        },
        token,
      );
      setMessage(type === "retry" ? "文件已进入重试队列。" : type === "withdraw" ? "文献已下架。" : "记录已移出馆藏和处理队列，NAS 文件仍保留。");
      setPendingAction(null);
      resource.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "操作失败。");
    }
  }

  async function replacePdf(item: AdminUploadItem, file: File) {
    const token = getServerSessionCredential();
    if (!token) return;
    if (!window.confirm(`确认用“${file.name}”替换“${item.review_data?.title ?? item.source_filename}”的公开 PDF 吗？旧文件会保留，新文件处理完成前不会影响当前阅读。`)) return;
    const body = new FormData();
    body.append("file", file);
    setReplacing(item.id);
    try {
      await apiRequest(
        `/ingestion/items/${item.id}/replace/`,
        { method: "POST", body },
        token,
      );
      setMessage("替换文件已进入处理队列。新文件全部就绪后才会接管在线阅读。");
      resource.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "替换文件提交失败。");
    } finally {
      setReplacing(null);
    }
  }

  return (
    <AdminPageFrame eyebrow="馆藏管理" title="馆藏项目" description="公开统计由已发布记录实时计算。每个 PDF 保留独立状态、错误与重试入口。">
      <Toolbar
        query={query}
        onQueryChange={setQuery}
        onSubmit={() => setSubmittedQuery(query.trim())}
        createHref="/admin/uploads"
        createLabel="批量上传"
      />
      {message ? <p className="form-message" role="status">{message}</p> : null}
      <ResourceState loading={resource.loading} error={resource.error} empty={!resource.data?.results.length} />
      {resource.data?.results.length ? (
        <section className="admin-entity-table admin-panel">
          <header><span>文献</span><span>类型</span><span>作者</span><span>年份</span><span>处理状态</span><span>操作</span></header>
          {resource.data.results.map((item) => {
            const metadata = item.review_data;
            const published = metadata?.publication_state === "published" && metadata.public_slug;
            const withdrawn = metadata?.publication_state === "withdrawn";
            return (
              <article key={item.id}>
                <p><span className="mini-cover line" /><span><strong>{metadata?.title || item.source_filename}</strong><small>{item.source_filename}</small></span></p>
                <span>{metadata ? documentLabels[metadata.document_type] : "待识别"}</span>
                <span>{metadata?.authors.join("、") || "待识别"}</span>
                <span>{metadata?.publication_year || "—"}</span>
                <b className={`status-${item.status}`}><CheckCircle2 size={13} />{uploadStatusLabels[item.status] ?? item.status} {item.stage_progress}%{metadata ? <small>OCR {metadata.ocr_status} · 页码 {metadata.page_label_status} · 语义 {metadata.semantic_index_status}</small> : null}</b>
                <span className="admin-row-actions">
                  {published ? <Link href={`/works/${metadata.public_slug}`}>查看 <ArrowRight size={13} /></Link> : <Link href={`/admin/review/${item.id}`}>复核内容 <ArrowRight size={13} /></Link>}
                  {!published && metadata ? <Link href={`/admin/publication?item=${item.id}`}>{withdrawn ? "重新发布" : "发布确认"} <ArrowRight size={13} /></Link> : null}
                  {published ? <Link href={`/admin/review/${item.id}?mode=edit`}><Pencil size={13} /> 编辑</Link> : null}
                  {published ? (
                    <label className={`admin-inline-file ${replacing === item.id ? "disabled" : ""}`}>
                      {replacing === item.id ? "上传中" : "替换 PDF"}
                      <input
                        className="sr-only"
                        type="file"
                        accept="application/pdf,.pdf"
                        disabled={replacing !== null}
                        onChange={(event) => {
                          const file = event.currentTarget.files?.[0];
                          event.currentTarget.value = "";
                          if (file) void replacePdf(item, file);
                        }}
                      />
                    </label>
                  ) : null}
                  {published ? <button type="button" onClick={() => setPendingAction({ item, type: "withdraw" })}>下架</button> : null}
                  {item.status === "failed" ? <button type="button" onClick={() => void action(item, "retry")}>重试</button> : null}
                  {!published && !withdrawn ? <button className="danger-link" type="button" onClick={() => setPendingAction({ item, type: "delete" })}><Trash2 size={13} />删除记录</button> : null}
                </span>
              </article>
            );
          })}
          <footer>共 {resource.data.count} 个上传项目。列表仅显示当前页。</footer>
        </section>
      ) : null}
      <ConfirmDialog
        open={Boolean(pendingAction)}
        title={pendingAction?.type === "withdraw" ? `下架“${pendingAction.item.review_data?.title ?? pendingAction.item.source_filename}”` : `移除“${pendingAction?.item.review_data?.title ?? pendingAction?.item.source_filename ?? "馆藏记录"}”`}
        description={pendingAction?.type === "withdraw" ? "确认后所有公开列表和检索会停止展示，文件、处理结果与稳定地址继续保留。" : "确认后记录会从馆藏、处理中心和复核队列隐藏，NAS 原始文件与审计记录继续保留。"}
        confirmLabel={pendingAction?.type === "withdraw" ? "确认下架" : "确认移除"}
        tone="danger"
        onCancel={() => setPendingAction(null)}
        onConfirm={() => pendingAction ? void action(pendingAction.item, pendingAction.type) : undefined}
      />
    </AdminPageFrame>
  );
}

type AdminTheory = {
  id: string;
  name: string;
  slug: string;
  description: string;
  symbol: string;
  foreign_name: string;
  entity_level: "tradition" | "school" | "branch";
  formation_period: string;
  core_questions: string[];
  hero_image: string;
  key_themes: string[];
  curation: Record<string, unknown>;
  suggestions: TaxonomySuggestions;
  editorial_status: string;
  work_count: number;
};

type AdminTopic = {
  id: string;
  name: string;
  slug: string;
  description: string;
  problem_statement: string;
  core_questions: string[];
  research_dimensions: string[];
  methods: string[];
  formation_context: string;
  hero_image: string;
  key_concepts: string[];
  timeline: [string, string, string][];
  curation: Record<string, unknown>;
  suggestions: TaxonomySuggestions;
  editorial_status: string;
  work_count: number;
};

type CuratedOption = {
  id: string;
  title?: string;
  name?: string;
  description?: string;
  source?: string;
  source_label?: string;
  reason?: string;
  confidence?: number;
  approved?: boolean;
  page_index?: number;
  printed_label?: string;
  evidence?: Record<string, unknown>;
  document_type?: string;
  slug?: string;
};

type TaxonomySuggestions = {
  works?: CuratedOption[];
  scholars?: CuratedOption[];
  neighbors?: CuratedOption[];
  theories?: CuratedOption[];
  concepts?: CuratedOption[];
  passages?: CuratedOption[];
};

type RelationMetadata = {
  relation: string;
  source: string;
};

type ReadingPathDraft = {
  title: string;
  level: string;
  description: string;
  workIds: string[];
};

type TaxonomyDraft = {
  id: string | null;
  kind: "theory" | "topic";
  name: string;
  slug: string;
  description: string;
  symbol: string;
  foreignName: string;
  entityLevel: "tradition" | "school" | "branch";
  formationPeriod: string;
  coreQuestions: string;
  problemStatement: string;
  researchDimensions: string;
  methods: string;
  formationContext: string;
  terms: string;
  timeline: string;
  heroCaption: string;
  primaryWorkIds: string[];
  secondaryWorkIds: string[];
  scholarIds: string[];
  theoryIds: string[];
  featuredPassageIds: string[];
  conceptLines: string;
  mapLines: string;
  neighborRelations: Record<string, RelationMetadata>;
  readingPaths: ReadingPathDraft[];
  baseCuration: Record<string, unknown>;
  suggestions: TaxonomySuggestions;
  status: string;
};

const emptyTaxonomy: TaxonomyDraft = {
  id: null,
  kind: "theory",
  name: "",
  slug: "",
  description: "",
  symbol: "",
  foreignName: "",
  entityLevel: "tradition",
  formationPeriod: "",
  coreQuestions: "",
  problemStatement: "",
  researchDimensions: "",
  methods: "",
  formationContext: "",
  terms: "",
  timeline: "",
  heroCaption: "",
  primaryWorkIds: [],
  secondaryWorkIds: [],
  scholarIds: [],
  theoryIds: [],
  featuredPassageIds: [],
  conceptLines: "",
  mapLines: "",
  neighborRelations: {},
  readingPaths: [],
  baseCuration: {},
  suggestions: {},
  status: "draft",
};

export function TaxonomyAdmin({
  mode = "combined",
  entityId,
}: {
  mode?: "combined" | "theory" | "topic";
  entityId?: string;
}) {
  const router = useRouter();
  const createName = useSearchParams().get("create")?.trim() ?? "";
  const editorOnly = entityId !== undefined;
  const showTheories = mode !== "topic";
  const showTopics = mode !== "theory";
  const theories = useAdminResource<Paginated<AdminTheory>>(
    !editorOnly && showTheories ? "/catalog/admin/theory-schools/" : null,
  );
  const topics = useAdminResource<Paginated<AdminTopic>>(
    !editorOnly && showTopics ? "/catalog/admin/topics/" : null,
  );
  const detailBase = mode === "topic"
    ? "/catalog/admin/topics"
    : "/catalog/admin/theory-schools";
  const detail = useAdminResource<AdminTheory | AdminTopic>(
    editorOnly && entityId !== "new"
      ? `${detailBase}/${entityId}/`
      : null,
  );
  const [draft, setDraft] = useState<TaxonomyDraft>({
    ...emptyTaxonomy,
    kind: mode === "topic" ? "topic" : "theory",
    name: createName,
  });
  const [message, setMessage] = useState("");
  const [heroFile, setHeroFile] = useState<File | null>(null);

  function editTheory(item: AdminTheory) {
    const curation = item.curation ?? {};
    setDraft({
      id: item.id,
      kind: "theory",
      name: item.name,
      slug: item.slug,
      description: item.description,
      symbol: item.symbol,
      foreignName: item.foreign_name ?? "",
      entityLevel: item.entity_level ?? "tradition",
      formationPeriod: item.formation_period ?? "",
      coreQuestions: (item.core_questions ?? []).join("\n"),
      problemStatement: "",
      researchDimensions: "",
      methods: "",
      formationContext: "",
      terms: item.key_themes.join("\n"),
      timeline: "",
      heroCaption: String(curation.hero_caption ?? ""),
      primaryWorkIds: stringArray(curation.foundational_work_ids),
      secondaryWorkIds: stringArray(curation.curated_reading_work_ids),
      scholarIds: stringArray(curation.key_scholar_ids),
      theoryIds: stringArray(curation.neighbor_school_ids),
      featuredPassageIds: [],
      conceptLines: structuredLines(curation.core_concepts, "name", "description", "source"),
      mapLines: structuredLines(
        curation.conceptual_map,
        "source",
        "target",
        "relation",
        "description",
      ),
      neighborRelations: relationMetadata(curation.neighbor_relations, "school_id"),
      readingPaths: [],
      baseCuration: curation,
      suggestions: item.suggestions ?? {},
      status: item.editorial_status,
    });
  }

  function editTopic(item: AdminTopic) {
    const curation = item.curation ?? {};
    setDraft({
      id: item.id,
      kind: "topic",
      name: item.name,
      slug: item.slug,
      description: item.description,
      symbol: "",
      foreignName: "",
      entityLevel: "tradition",
      formationPeriod: "",
      coreQuestions: (item.core_questions ?? []).join("\n"),
      problemStatement: item.problem_statement ?? "",
      researchDimensions: (item.research_dimensions ?? []).join("\n"),
      methods: (item.methods ?? []).join("\n"),
      formationContext: item.formation_context ?? "",
      terms: item.key_concepts.join("\n"),
      timeline: item.timeline.map((row) => row.join("｜")).join("\n"),
      heroCaption: String(curation.hero_caption ?? ""),
      primaryWorkIds: stringArray(curation.foundational_work_ids),
      secondaryWorkIds: stringArray(curation.recent_work_ids),
      scholarIds: stringArray(curation.related_scholar_ids),
      theoryIds: stringArray(curation.linked_theory_ids),
      featuredPassageIds: curation.featured_passage_id
        ? [String(curation.featured_passage_id)]
        : [],
      conceptLines: "",
      mapLines: "",
      neighborRelations: {},
      readingPaths: Array.isArray(curation.reading_paths)
        ? curation.reading_paths.flatMap((item) => {
            if (!item || typeof item !== "object") return [];
            const path = item as Record<string, unknown>;
            return [{
              title: String(path.title ?? ""),
              level: String(path.level ?? ""),
              description: String(path.description ?? ""),
              workIds: stringArray(path.work_ids),
            }];
          })
        : [],
      baseCuration: curation,
      suggestions: item.suggestions ?? {},
      status: item.editorial_status,
    });
  }

  useEffect(() => {
    if (!editorOnly || entityId === "new" || !detail.data) return;
    let active = true;
    Promise.resolve().then(() => {
      if (!active) return;
      if (mode === "topic") editTopic(detail.data as AdminTopic);
      else editTheory(detail.data as AdminTheory);
    });
    return () => {
      active = false;
    };
  }, [detail.data, editorOnly, entityId, mode]);

  async function save(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return;
    const base = draft.kind === "theory" ? "/catalog/admin/theory-schools" : "/catalog/admin/topics";
    const terms = splitValues(draft.terms);
    const curation = draft.kind === "theory"
      ? {
          ...draft.baseCuration,
          hero_caption: draft.heroCaption.trim(),
          foundational_work_ids: draft.primaryWorkIds,
          curated_reading_work_ids: draft.secondaryWorkIds,
          key_scholar_ids: draft.scholarIds,
          neighbor_school_ids: draft.theoryIds,
          core_concepts: parseStructuredLines(
            draft.conceptLines,
            ["name", "description", "source"],
          ),
          conceptual_map: parseStructuredLines(
            draft.mapLines,
            ["source", "target", "relation", "description"],
          ),
          neighbor_relations: draft.theoryIds.map((schoolId) => ({
            school_id: schoolId,
            relation: draft.neighborRelations[schoolId]?.relation ?? "",
            source: draft.neighborRelations[schoolId]?.source ?? "",
          })),
        }
      : {
          ...draft.baseCuration,
          hero_caption: draft.heroCaption.trim(),
          foundational_work_ids: draft.primaryWorkIds,
          recent_work_ids: draft.secondaryWorkIds,
          related_scholar_ids: draft.scholarIds,
          linked_theory_ids: draft.theoryIds,
          featured_passage_id: draft.featuredPassageIds[0] ?? "",
          featured_passage_reason: (
            draft.suggestions.passages?.find(
              (option) => option.id === draft.featuredPassageIds[0],
            )?.reason ?? ""
          ),
          featured_passage_evidence: (
            draft.suggestions.passages?.find(
              (option) => option.id === draft.featuredPassageIds[0],
            )?.evidence ?? {}
          ),
          reading_paths: draft.readingPaths.map((path) => ({
            title: path.title.trim(),
            level: path.level.trim(),
            description: path.description.trim(),
            work_ids: path.workIds,
          })).filter((path) => path.title),
        };
    const body = draft.kind === "theory"
      ? {
          name: draft.name,
          slug: draft.slug,
          description: draft.description,
          symbol: draft.symbol,
          foreign_name: draft.foreignName,
          entity_level: draft.entityLevel,
          formation_period: draft.formationPeriod,
          core_questions: splitLines(draft.coreQuestions),
          key_themes: terms,
          curation,
          editorial_status: draft.status,
        }
      : {
          name: draft.name,
          slug: draft.slug,
          description: draft.description,
          problem_statement: draft.problemStatement,
          core_questions: splitLines(draft.coreQuestions),
          research_dimensions: splitLines(draft.researchDimensions),
          methods: splitLines(draft.methods),
          formation_context: draft.formationContext,
          key_concepts: terms,
          timeline: parseStructuredLines(draft.timeline, ["0", "1", "2"]).map((row) => [row["0"], row["1"], row["2"]]),
          curation,
          editorial_status: draft.status,
        };
    try {
      const saved = await apiRequest<AdminTheory | AdminTopic>(
        `${base}/${draft.id ? `${draft.id}/` : ""}`,
        { method: draft.id ? "PATCH" : "POST", body: JSON.stringify(body) },
        token,
      );
      if (heroFile) {
        const imageBody = new FormData();
        imageBody.append("hero_image", heroFile);
        await apiRequest(
          `${base}/${saved.id}/`,
          { method: "PATCH", body: imageBody },
          token,
        );
        setHeroFile(null);
      }
      setDraft((current) => ({
        ...current,
        id: saved.id,
        slug: saved.slug,
        baseCuration: saved.curation ?? current.baseCuration,
        suggestions: saved.suggestions ?? current.suggestions,
      }));
      setMessage("知识分类已经保存。公开状态会立即影响前台目录，但不会自动改变文献关系。");
      theories.refresh();
      topics.refresh();
      if (editorOnly && entityId === "new") {
        router.replace(
          draft.kind === "theory"
            ? `/admin/theory-schools/${saved.id}`
            : `/admin/topics/${saved.id}`,
        );
      }
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "保存失败。");
    }
  }

  return (
    <AdminPageFrame
      eyebrow="知识组织"
      title={mode === "theory" ? "理论流派" : mode === "topic" ? "主题" : "理论流派与主题"}
      description={mode === "theory"
        ? "管理理论流派的公开页面、关键主题和馆藏关系。"
        : mode === "topic"
          ? "管理主题的公开页面、关键概念、时间线和馆藏关系。"
          : "自动识别提出候选，人工确认后写入作品关系。流派和主题保持为不同对象。"}
    >
      <div className={`taxonomy-layout ${editorOnly ? "editor-only" : ""}`}>
        {!editorOnly ? <section>
          {showTheories ? (
            <>
              <div className="admin-list-toolbar">
                <h2>理论流派</h2>
                <Link href="/admin/theory-schools/new"><Plus size={15} />新建流派</Link>
              </div>
              <ResourceState loading={theories.loading} error={theories.error} empty={!theories.data?.results.length} />
              <div className="taxonomy-admin-grid">
                {theories.data?.results.map((school) => (
                  <article className={`admin-panel ${draft.id === school.id ? "selected" : ""}`} key={school.id}>
                    <span className="theory-symbol">{school.symbol || school.name.slice(0, 2)}</span>
                    <h2>{school.name}</h2>
                    <p>{school.description || "尚未填写说明。"}</p>
                    <dl><div><dt>关联馆藏</dt><dd>{school.work_count}</dd></div><div><dt>状态</dt><dd>{school.editorial_status === "published" ? "公开" : "草稿"}</dd></div></dl>
                    <Link href={`/admin/theory-schools/${school.id}`}><Pencil size={14} />编辑</Link>
                  </article>
                ))}
              </div>
            </>
          ) : null}
          {showTopics ? (
            <>
              <div className={`admin-list-toolbar ${showTheories ? "taxonomy-topic-heading" : ""}`}>
                <h2>主题</h2>
                <Link href="/admin/topics/new"><Plus size={15} />新建主题</Link>
              </div>
              <ResourceState loading={topics.loading} error={topics.error} empty={!topics.data?.results.length} />
              <div className="taxonomy-admin-grid">
                {topics.data?.results.map((topic) => (
                  <article className={`admin-panel ${draft.id === topic.id ? "selected" : ""}`} key={topic.id}>
                    <span className="theory-symbol">{topic.name.slice(0, 2)}</span>
                    <h2>{topic.name}</h2>
                    <p>{topic.description || "尚未填写说明。"}</p>
                    <dl><div><dt>关联馆藏</dt><dd>{topic.work_count}</dd></div><div><dt>状态</dt><dd>{topic.editorial_status === "published" ? "公开" : "草稿"}</dd></div></dl>
                    <Link href={`/admin/topics/${topic.id}`}><Pencil size={14} />编辑</Link>
                  </article>
                ))}
              </div>
            </>
          ) : null}
        </section> : null}
        {editorOnly ? <><form className="admin-panel admin-side-editor taxonomy-editor-page" onSubmit={save}>
          <header>
            <div>
              <Link href={draft.kind === "theory" ? "/admin/theory-schools" : "/admin/topics"}>返回列表</Link>
              <h2>{draft.id ? "编辑" : "新建"}{draft.kind === "theory" ? "理论流派" : "主题"}</h2>
            </div>
          </header>
          <ResourceState loading={detail.loading} error={detail.error} empty={false} />
          <label><span>名称</span><input autoComplete="off" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} required /></label>
          <AuthoritySuggestions
            entityType={draft.kind === "theory" ? "theory_tradition" : "topic"}
            query={draft.name}
          />
          {draft.kind === "topic" ? <FieldEnrichmentControl
            targetType="topic"
            targetId={draft.id}
            title="主题字段核对"
            fields={[{ name: "discipline", label: "学科分类" }]}
            onAccepted={detail.refresh}
          /> : null}
          <label><span>固定链接</span><input value={draft.slug} onChange={(event) => setDraft({ ...draft, slug: event.target.value })} placeholder="留空自动生成" /></label>
          {draft.kind === "theory" ? <>
            <div className="inline-fields">
              <label><span>外文名称</span><input value={draft.foreignName} onChange={(event) => setDraft({ ...draft, foreignName: event.target.value })} /></label>
              <label><span>实体层级</span><select value={draft.entityLevel} onChange={(event) => setDraft({ ...draft, entityLevel: event.target.value as TaxonomyDraft["entityLevel"] })}><option value="tradition">理论传统</option><option value="school">流派</option><option value="branch">分支</option></select></label>
            </div>
            <div className="inline-fields">
              <label><span>视觉符号或简称</span><input value={draft.symbol} onChange={(event) => setDraft({ ...draft, symbol: event.target.value })} /></label>
              <label><span>形成时期</span><input value={draft.formationPeriod} onChange={(event) => setDraft({ ...draft, formationPeriod: event.target.value })} /></label>
            </div>
          </> : null}
          {draft.kind === "topic" ? <>
            <label><span>问题陈述</span><textarea rows={4} value={draft.problemStatement} onChange={(event) => setDraft({ ...draft, problemStatement: event.target.value })} placeholder="说明读者从什么研究问题进入" /></label>
            <label><span>形成背景</span><textarea rows={3} value={draft.formationContext} onChange={(event) => setDraft({ ...draft, formationContext: event.target.value })} /></label>
          </> : null}
          <StringListEditor label="核心问题" itemLabel="问题" value={editorLines(draft.coreQuestions)} onChange={(value) => setDraft({ ...draft, coreQuestions: value.join("\n") })} addLabel="添加问题" />
          {draft.kind === "topic" ? <div className="structured-editor-pair">
            <StringListEditor label="研究维度" itemLabel="维度" value={editorLines(draft.researchDimensions)} onChange={(value) => setDraft({ ...draft, researchDimensions: value.join("\n") })} addLabel="添加维度" />
            <StringListEditor label="常用方法" itemLabel="方法" value={editorLines(draft.methods)} onChange={(value) => setDraft({ ...draft, methods: value.join("\n") })} addLabel="添加方法" />
          </div> : null}
          <label className="knowledge-image-upload"><ImagePlus size={18} /><span>{heroFile?.name || "上传或替换主视觉图片"}</span><input type="file" accept="image/*" onChange={(event) => setHeroFile(event.target.files?.[0] ?? null)} /></label>
          <label><span>主视觉说明</span><input value={draft.heroCaption} onChange={(event) => setDraft({ ...draft, heroCaption: event.target.value })} placeholder="显示在主视觉图片下方" /></label>
          <StringListEditor label={draft.kind === "theory" ? "关键主题" : "关键概念"} itemLabel={draft.kind === "theory" ? "主题" : "概念"} value={editorLines(draft.terms)} onChange={(value) => setDraft({ ...draft, terms: value.join("\n") })} />
          {draft.kind === "theory" ? (
            <div>
              <StructuredRowsEditor
                label="核心概念"
                rowLabel="概念"
                addLabel="添加概念"
                value={editorStructuredRows(draft.conceptLines, ["name", "description", "source"])}
                createRow={() => ({ name: "", description: "", source: "" })}
                columns={[
                  { key: "name", label: "概念名称" },
                  { key: "source", label: "来源" },
                  { key: "description", label: "说明", multiline: true },
                ]}
                onChange={(value) => setDraft({ ...draft, conceptLines: formatEditorRows(value, ["name", "description", "source"]) })}
              />
              {draft.suggestions.concepts?.length ? (
                <button
                  className="inline-suggestion-button"
                  type="button"
                  onClick={() => setDraft({
                    ...draft,
                    conceptLines: mergeSuggestionLines(
                      draft.conceptLines,
                      draft.suggestions.concepts ?? [],
                    ),
                  })}
                >
                  <Plus size={13} />加入系统识别出的概念候选
                </button>
              ) : null}
            </div>
          ) : null}
          {draft.kind === "topic" ? <StructuredRowsEditor
            label="概念时间线"
            rowLabel="时间节点"
            addLabel="添加时间节点"
            value={editorStructuredRows(draft.timeline, ["year", "node", "description"])}
            createRow={() => ({ year: "", node: "", description: "" })}
            columns={[
              { key: "year", label: "年份或时期" },
              { key: "node", label: "节点" },
              { key: "description", label: "说明", multiline: true },
            ]}
            onChange={(value) => setDraft({ ...draft, timeline: formatEditorRows(value, ["year", "node", "description"]) })}
          /> : null}
          <label><span>说明</span><textarea rows={7} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
          <fieldset className="curation-fieldset">
            <legend>自动建议与人工策展</legend>
            <p>候选来自已确认的 PDF 作者、流派和主题关系。选中后才会进入公开页面。</p>
            <CuratedSelector
              label="奠基文献"
              options={draft.suggestions.works ?? []}
              selected={draft.primaryWorkIds}
              onChange={(primaryWorkIds) => setDraft({ ...draft, primaryWorkIds })}
            />
            <CuratedSelector
              label={draft.kind === "theory" ? "策展阅读书目" : "最近入库"}
              options={draft.suggestions.works ?? []}
              selected={draft.secondaryWorkIds}
              onChange={(secondaryWorkIds) => setDraft({ ...draft, secondaryWorkIds })}
            />
            <CuratedSelector
              label={draft.kind === "theory" ? "代表学者" : "相关学者"}
              options={draft.suggestions.scholars ?? []}
              selected={draft.scholarIds}
              onChange={(scholarIds) => setDraft({ ...draft, scholarIds })}
            />
            <CuratedSelector
              label={draft.kind === "theory" ? "相邻流派" : "关联理论流派"}
              options={draft.kind === "theory" ? draft.suggestions.neighbors ?? [] : draft.suggestions.theories ?? []}
              selected={draft.theoryIds}
              onChange={(theoryIds) => setDraft({ ...draft, theoryIds })}
            />
            {draft.kind === "topic" ? (
              <CuratedSelector
                label="全文摘录聚焦，限选一项"
                options={draft.suggestions.passages ?? []}
                selected={draft.featuredPassageIds}
                single
                onChange={(featuredPassageIds) => setDraft({ ...draft, featuredPassageIds })}
              />
            ) : null}
            {draft.kind === "theory" ? (
              <RelationDetailsEditor
                label="相邻流派的关系与依据"
                options={draft.suggestions.neighbors ?? []}
                selected={draft.theoryIds}
                value={draft.neighborRelations}
                relationPlaceholder="例如：批判继承、概念邻近"
                onChange={(neighborRelations) => setDraft({ ...draft, neighborRelations })}
              />
            ) : null}
          </fieldset>
          {draft.kind === "theory" ? <StructuredRowsEditor
            label="概念关系图"
            rowLabel="关系"
            addLabel="添加关系"
            value={editorStructuredRows(draft.mapLines, ["source", "target", "relation", "description"])}
            createRow={() => ({ source: "", target: "", relation: "", description: "" })}
            columns={[
              { key: "source", label: "起点" },
              { key: "target", label: "终点" },
              { key: "relation", label: "关系" },
              { key: "description", label: "说明", multiline: true },
            ]}
            onChange={(value) => setDraft({ ...draft, mapLines: formatEditorRows(value, ["source", "target", "relation", "description"]) })}
          /> : null}
          {draft.kind === "topic" ? (
            <fieldset className="reading-path-editor">
              <legend>策展阅读路径</legend>
              <p>每条路径独立选择文献，不再自动复用奠基文献。</p>
              {draft.readingPaths.map((path, index) => (
                <div className="reading-path-admin-row" key={`${index}-${path.title}`}>
                  <div className="inline-fields">
                    <label>
                      <span>路径名称</span>
                      <input
                        value={path.title}
                        onChange={(event) => setDraft({
                          ...draft,
                          readingPaths: draft.readingPaths.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, title: event.target.value } : item
                          )),
                        })}
                      />
                    </label>
                    <label>
                      <span>难度</span>
                      <select
                        value={path.level}
                        onChange={(event) => setDraft({
                          ...draft,
                          readingPaths: draft.readingPaths.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, level: event.target.value } : item
                          )),
                        })}
                      >
                        <option value="">未分级</option>
                        <option value="入门">入门</option>
                        <option value="进阶">进阶</option>
                        <option value="研究">研究</option>
                      </select>
                    </label>
                  </div>
                  <label>
                    <span>说明</span>
                    <textarea
                      rows={2}
                      value={path.description}
                      onChange={(event) => setDraft({
                        ...draft,
                        readingPaths: draft.readingPaths.map((item, itemIndex) => (
                          itemIndex === index ? { ...item, description: event.target.value } : item
                        )),
                      })}
                    />
                  </label>
                  <CuratedSelector
                    label="本路径文献"
                    options={draft.suggestions.works ?? []}
                    selected={path.workIds}
                    onChange={(workIds) => setDraft({
                      ...draft,
                      readingPaths: draft.readingPaths.map((item, itemIndex) => (
                        itemIndex === index ? { ...item, workIds } : item
                      )),
                    })}
                  />
                  <button
                    className="button secondary"
                    type="button"
                    onClick={() => setDraft({
                      ...draft,
                      readingPaths: draft.readingPaths.filter((_item, itemIndex) => itemIndex !== index),
                    })}
                  >
                    <X size={14} />删除这条路径
                  </button>
                </div>
              ))}
              <button
                className="button secondary"
                type="button"
                onClick={() => setDraft({
                  ...draft,
                  readingPaths: draft.readingPaths.concat({
                    title: "",
                    level: "",
                    description: "",
                    workIds: [],
                  }),
                })}
              >
                <Plus size={14} />新增阅读路径
              </button>
            </fieldset>
          ) : null}
          <label><span>编辑状态</span><select value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}><option value="draft">草稿</option><option value="published">公开</option><option value="archived">已下线</option></select></label>
          <button className="button" type="submit"><Save size={15} />保存</button>
          {message ? <p className="form-message" role="status">{message}</p> : null}
          {draft.id ? <EntityLifecycleActions
            kind={draft.kind === "topic" ? "topic" : "theory-school"}
            id={draft.id}
            name={draft.name}
            status={draft.status}
            previewHref={draft.kind === "topic" ? `/topics/${draft.slug}` : `/theory-schools/${draft.slug}`}
            onChanged={(snapshot) => setDraft((current) => ({ ...current, status: snapshot.status }))}
            onDeleted={() => router.replace(draft.kind === "topic" ? "/admin/topics" : "/admin/theory-nodes?node_type=theory_tradition")}
          /> : null}
        </form>{draft.id ? <EntityRelationsAdmin
          kind={draft.kind}
          entityId={draft.id}
          previewHref={draft.kind === "topic" ? `/topics/${draft.slug}` : `/theory-schools/${draft.slug}`}
        /> : null}</> : null}
      </div>
    </AdminPageFrame>
  );
}

type AdminScholar = {
  id: string;
  person_id: string;
  slug: string;
  preferred_name: string;
  original_name: string;
  aliases: string[];
  birth_year: number | null;
  death_year: number | null;
  biography: string;
  portrait: string;
  short_description: string;
  affiliations: string[];
  key_concerns: string[];
  timeline: [string, string][];
  featured_quote: string;
  quote_source: string;
  curation: Record<string, unknown>;
  suggestions: {
    works?: CuratedOption[];
    theories?: CuratedOption[];
    topics?: CuratedOption[];
    related_scholars?: CuratedOption[];
    concepts?: CuratedOption[];
  };
  editorial_status: string;
};

type ScholarDraft = {
  id: string | null;
  personId: string | null;
  slug: string;
  name: string;
  originalName: string;
  aliases: string;
  birthYear: string;
  deathYear: string;
  biography: string;
  description: string;
  affiliations: string;
  concerns: string;
  timeline: string;
  keyConcepts: string;
  conceptMap: string;
  essentialWorkIds: string[];
  networkScholarIds: string[];
  networkRelations: Record<string, RelationMetadata>;
  frequentScholarIds: string[];
  relatedTheoryIds: string[];
  baseCuration: Record<string, unknown>;
  suggestions: AdminScholar["suggestions"];
  quote: string;
  quoteSource: string;
  status: string;
};

const emptyScholar: ScholarDraft = {
  id: null,
  personId: null,
  slug: "",
  name: "",
  originalName: "",
  aliases: "",
  birthYear: "",
  deathYear: "",
  biography: "",
  description: "",
  affiliations: "",
  concerns: "",
  timeline: "",
  keyConcepts: "",
  conceptMap: "",
  essentialWorkIds: [],
  networkScholarIds: [],
  networkRelations: {},
  frequentScholarIds: [],
  relatedTheoryIds: [],
  baseCuration: {},
  suggestions: {},
  quote: "",
  quoteSource: "",
  status: "draft",
};

export function ScholarsAdmin({ scholarId }: { scholarId?: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const createName = searchParams.get("create")?.trim() ?? "";
  const requestedQuery = searchParams.get("q")?.trim() ?? "";
  const editorOnly = scholarId !== undefined;
  const [query, setQuery] = useState(requestedQuery);
  const [submittedQuery, setSubmittedQuery] = useState(requestedQuery);
  const resource = useAdminResource<Paginated<AdminScholar>>(
    editorOnly
      ? null
      : `/catalog/admin/scholars/${submittedQuery ? `?search=${encodeURIComponent(submittedQuery)}` : ""}`,
  );
  const detail = useAdminResource<AdminScholar>(
    editorOnly && scholarId !== "new"
      ? `/catalog/admin/scholars/${scholarId}/`
      : null,
  );
  const [draft, setDraft] = useState<ScholarDraft>({ ...emptyScholar, name: createName });
  const [message, setMessage] = useState("");
  const [portraitFile, setPortraitFile] = useState<File | null>(null);
  const visible = resource.data?.results ?? [];

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setQuery(requestedQuery);
      setSubmittedQuery(requestedQuery);
    });
    return () => {
      active = false;
    };
  }, [requestedQuery]);

  function edit(scholar: AdminScholar) {
    const curation = scholar.curation ?? {};
    const network = Array.isArray(curation.network) ? curation.network : [];
    setDraft({
      id: scholar.id,
      personId: scholar.person_id,
      slug: scholar.slug,
      name: scholar.preferred_name,
      originalName: scholar.original_name,
      aliases: scholar.aliases.join("\n"),
      birthYear: scholar.birth_year ? String(scholar.birth_year) : "",
      deathYear: scholar.death_year ? String(scholar.death_year) : "",
      biography: scholar.biography,
      description: scholar.short_description,
      affiliations: scholar.affiliations.join("\n"),
      concerns: scholar.key_concerns.join("\n"),
      timeline: scholar.timeline.map(([year, event]) => {
        const parsed = parseScholarTimelineEvent(event);
        return [year, parsed.type, parsed.event].join("｜");
      }).join("\n"),
      keyConcepts: structuredLines(curation.key_concepts, "name", "description", "source"),
      conceptMap: structuredLines(
        curation.concept_map,
        "source",
        "target",
        "relation",
        "description",
      ),
      essentialWorkIds: stringArray(curation.essential_work_ids),
      networkScholarIds: network.flatMap((item) => (
        item && typeof item === "object" && "scholar_id" in item
          ? [String((item as Record<string, unknown>).scholar_id)]
          : []
      )),
      networkRelations: relationMetadata(curation.network, "scholar_id"),
      frequentScholarIds: stringArray(curation.frequently_read_scholar_ids),
      relatedTheoryIds: stringArray(curation.related_theory_ids),
      baseCuration: curation,
      suggestions: scholar.suggestions ?? {},
      quote: scholar.featured_quote,
      quoteSource: scholar.quote_source,
      status: scholar.editorial_status,
    });
  }

  useEffect(() => {
    if (!editorOnly || scholarId === "new" || !detail.data) return;
    const scholar = detail.data;
    let active = true;
    Promise.resolve().then(() => {
      if (active) edit(scholar);
    });
    return () => {
      active = false;
    };
  }, [detail.data, editorOnly, scholarId]);

  async function save(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return;
    const curation = {
      ...draft.baseCuration,
      essential_work_ids: draft.essentialWorkIds,
      key_concepts: parseStructuredLines(
        draft.keyConcepts,
        ["name", "description", "source"],
      ),
      concept_map: parseStructuredLines(
        draft.conceptMap,
        ["source", "target", "relation", "description"],
      ),
      network: draft.networkScholarIds.map((scholarId) => (
        {
          scholar_id: scholarId,
          relation: draft.networkRelations[scholarId]?.relation ?? "",
          source: draft.networkRelations[scholarId]?.source ?? "",
        }
      )),
      frequently_read_scholar_ids: draft.frequentScholarIds,
      related_theory_ids: draft.relatedTheoryIds,
    };
    try {
      const saved = await apiRequest<AdminScholar>(
        `/catalog/admin/scholars/${draft.id ? `${draft.id}/` : ""}`,
        {
          method: draft.id ? "PATCH" : "POST",
          body: JSON.stringify({
            slug: draft.slug,
            preferred_name: draft.name,
            original_name: draft.originalName,
            aliases: splitValues(draft.aliases),
            birth_year: Number(draft.birthYear) || null,
            death_year: Number(draft.deathYear) || null,
            biography: draft.biography,
            short_description: draft.description,
            affiliations: splitValues(draft.affiliations),
            key_concerns: splitValues(draft.concerns),
            timeline: parseStructuredLines(draft.timeline, ["year", "type", "event"]).map((row) => [
              row.year,
              formatScholarTimelineEvent(row.type, row.event),
            ]),
            curation,
            featured_quote: draft.quote,
            quote_source: draft.quoteSource,
            editorial_status: draft.status,
          }),
        },
        token,
      );
      if (portraitFile) {
        const portraitBody = new FormData();
        portraitBody.append("portrait", portraitFile);
        await apiRequest(
          `/catalog/admin/scholars/${saved.id}/`,
          { method: "PATCH", body: portraitBody },
          token,
        );
        setPortraitFile(null);
      }
      setDraft((current) => ({
        ...current,
        id: saved.id,
        personId: saved.person_id,
        slug: saved.slug,
        baseCuration: saved.curation ?? current.baseCuration,
        suggestions: saved.suggestions ?? current.suggestions,
      }));
      setMessage("学者档案已保存。作品列表仍由作者贡献关系自动汇总。");
      resource.refresh();
      if (editorOnly && scholarId === "new") {
        router.replace(`/admin/scholars/${saved.id}`);
      }
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "保存失败。");
    }
  }

  return (
    <AdminPageFrame eyebrow="人物资料" title="学者" description="中文名、原名、译名和作者身份分别保存。学者馆藏作品从真实作者关系汇总。">
      {!editorOnly ? <Toolbar query={query} onQueryChange={setQuery} onSubmit={() => { const normalized = query.trim(); setSubmittedQuery(normalized); router.replace(normalized ? `/admin/scholars?q=${encodeURIComponent(normalized)}` : "/admin/scholars"); }} onCreate={() => router.push("/admin/scholars/new")} createLabel="新建学者" /> : null}
      <div className={`admin-master-detail ${editorOnly ? "editor-only" : ""}`}>
        {!editorOnly ? <section className="admin-entity-table scholar-admin-table admin-panel">
          <header><span>学者</span><span>原名</span><span>年代</span><span>关注领域</span><span>公开档案</span><span>操作</span></header>
          {visible.map((scholar) => (
            <article className={draft.id === scholar.id ? "selected" : ""} key={scholar.id}>
              <p><span className="tiny-portrait" /><strong>{scholar.preferred_name}</strong></p>
              <span>{scholar.original_name || "—"}</span>
              <span>{scholar.birth_year ? `${scholar.birth_year}—${scholar.death_year ?? ""}` : "—"}</span>
              <span>{scholar.key_concerns.slice(0, 2).join("、") || "待补"}</span>
              <b>{scholar.editorial_status === "published" ? "已公开" : "草稿"}</b>
              <span className="admin-row-actions"><Link href={`/admin/scholars/${scholar.id}`}>编辑</Link>{scholar.editorial_status === "published" ? <Link href={`/scholars/${scholar.slug}`}>查看</Link> : null}</span>
            </article>
          ))}
          {!visible.length ? <p className="empty-state">没有匹配的真实学者档案。</p> : null}
        </section> : null}
        {editorOnly ? <form className="admin-panel admin-side-editor scholar-editor dedicated-editor" onSubmit={save}>
          <header><div><Link href="/admin/scholars">返回列表</Link><h2>{draft.id ? "编辑学者" : "新建学者"}</h2></div></header>
          <ResourceState loading={detail.loading} error={detail.error} empty={false} />
          <label><span>主要显示名</span><input autoComplete="off" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} required /></label>
          <AuthoritySuggestions
            entityType="person"
            query={draft.name}
          />
          <label><span>原名</span><input value={draft.originalName} onChange={(event) => setDraft({ ...draft, originalName: event.target.value })} /></label>
          <StringListEditor label="其他译名或音译" itemLabel="名称" value={editorLines(draft.aliases)} onChange={(value) => setDraft({ ...draft, aliases: value.join("\n") })} addLabel="添加译名或别名" />
          <label className="knowledge-image-upload"><ImagePlus size={18} /><span>{portraitFile?.name || (detail.data?.portrait ? "替换学者肖像" : "上传学者肖像")}</span><input type="file" accept="image/*" onChange={(event) => setPortraitFile(event.target.files?.[0] ?? null)} /></label>
          <div className="inline-fields"><label><span>出生年</span><input type="number" value={draft.birthYear} onChange={(event) => setDraft({ ...draft, birthYear: event.target.value })} /></label><label><span>逝世年</span><input type="number" value={draft.deathYear} onChange={(event) => setDraft({ ...draft, deathYear: event.target.value })} /></label></div>
          <label><span>页面简介</span><textarea rows={3} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /><small>用于学者列表和学者页首屏，建议用一段话概括研究位置。</small></label>
          <label><span>完整传记</span><textarea rows={7} value={draft.biography} onChange={(event) => setDraft({ ...draft, biography: event.target.value })} /><small>用于“完整传记”页面。生平节点和重要发表请在下方逐项维护，避免重复堆在一段文字里。</small></label>
          <StringListEditor label="机构" itemLabel="机构" value={editorLines(draft.affiliations)} onChange={(value) => setDraft({ ...draft, affiliations: value.join("\n") })} addLabel="添加机构" />
          <FieldEnrichmentControl
            targetType="person"
            targetId={draft.personId}
            title="学者字段核对"
            fields={[
              { name: "external_identifier", label: "权威标识符" },
              { name: "affiliation", label: "机构", currentValue: editorLines(draft.affiliations) },
              { name: "name_variant", label: "译名或别名", currentValue: editorLines(draft.aliases) },
            ]}
            formContext={{
              language: "zh",
              known_birth_year: Number(draft.birthYear) || null,
              known_death_year: Number(draft.deathYear) || null,
            }}
            onAccepted={detail.refresh}
          />
          <StringListEditor label="关注领域" itemLabel="领域" value={editorLines(draft.concerns)} onChange={(value) => setDraft({ ...draft, concerns: value.join("\n") })} addLabel="添加领域" />
          <StructuredRowsEditor
            label="生平与重要发表"
            description="年份可填写具体年份或时期。类型用于区分生平、著作、任职和其他事件，并以兼容格式保存到现有时间线字段。"
            rowLabel="事件"
            addLabel="添加事件"
            value={editorStructuredRows(draft.timeline, ["year", "type", "event"])}
            createRow={() => ({ year: "", type: "life", event: "" })}
            columns={[
              { key: "year", label: "年份或时期" },
              { key: "type", label: "类型", options: scholarTimelineTypes },
              { key: "event", label: "事件或发表", multiline: true },
            ]}
            onChange={(value) => setDraft({ ...draft, timeline: formatEditorRows(value, ["year", "type", "event"]) })}
          />
          <div>
            <StructuredRowsEditor
              label="关键概念"
              rowLabel="概念"
              addLabel="添加概念"
              value={editorStructuredRows(draft.keyConcepts, ["name", "description", "source"])}
              createRow={() => ({ name: "", description: "", source: "" })}
              columns={[
                { key: "name", label: "概念名称" },
                { key: "source", label: "来源" },
                { key: "description", label: "说明", multiline: true },
              ]}
              onChange={(value) => setDraft({ ...draft, keyConcepts: formatEditorRows(value, ["name", "description", "source"]) })}
            />
            {draft.suggestions.concepts?.length ? (
              <button
                className="inline-suggestion-button"
                type="button"
                onClick={() => setDraft({
                  ...draft,
                  keyConcepts: mergeSuggestionLines(
                    draft.keyConcepts,
                    draft.suggestions.concepts ?? [],
                  ),
                })}
              >
                <Plus size={13} />加入系统识别出的概念候选
              </button>
            ) : null}
          </div>
          <StructuredRowsEditor
            label="概念地图"
            rowLabel="关系"
            addLabel="添加关系"
            value={editorStructuredRows(draft.conceptMap, ["source", "target", "relation", "description"])}
            createRow={() => ({ source: "", target: "", relation: "", description: "" })}
            columns={[
              { key: "source", label: "起点" },
              { key: "target", label: "终点" },
              { key: "relation", label: "关系" },
              { key: "description", label: "说明", multiline: true },
            ]}
            onChange={(value) => setDraft({ ...draft, conceptMap: formatEditorRows(value, ["source", "target", "relation", "description"]) })}
          />
          <fieldset className="curation-fieldset">
            <legend>自动建议与人工策展</legend>
            <p>系统依据作者贡献和共同流派、主题给出候选，管理员选择后才进入公开学者页。</p>
            <CuratedSelector
              label="重要文献"
              options={draft.suggestions.works ?? []}
              selected={draft.essentialWorkIds}
              onChange={(essentialWorkIds) => setDraft({ ...draft, essentialWorkIds })}
            />
            <CuratedSelector
              label="学术关系"
              options={draft.suggestions.related_scholars ?? []}
              selected={draft.networkScholarIds}
              onChange={(networkScholarIds) => setDraft({ ...draft, networkScholarIds })}
            />
            <RelationDetailsEditor
              label="学术关系类型与依据"
              options={draft.suggestions.related_scholars ?? []}
              selected={draft.networkScholarIds}
              value={draft.networkRelations}
              relationPlaceholder="例如：师承、合作、批评、影响"
              onChange={(networkRelations) => setDraft({ ...draft, networkRelations })}
            />
            <CuratedSelector
              label="经常连着阅读"
              options={draft.suggestions.related_scholars ?? []}
              selected={draft.frequentScholarIds}
              onChange={(frequentScholarIds) => setDraft({ ...draft, frequentScholarIds })}
            />
            <CuratedSelector
              label="相关理论流派"
              options={draft.suggestions.theories ?? []}
              selected={draft.relatedTheoryIds}
              onChange={(relatedTheoryIds) => setDraft({ ...draft, relatedTheoryIds })}
            />
          </fieldset>
          <label><span>代表语录</span><textarea rows={3} value={draft.quote} onChange={(event) => setDraft({ ...draft, quote: event.target.value })} /></label>
          <label><span>语录来源</span><input value={draft.quoteSource} onChange={(event) => setDraft({ ...draft, quoteSource: event.target.value })} /></label>
          <label><span>编辑状态</span><select value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}><option value="draft">草稿</option><option value="published">公开</option><option value="archived">已下线</option></select></label>
          <button className="button" type="submit"><Save size={15} />保存学者</button>
          {message ? <p className="form-message">{message}</p> : null}
          {draft.id ? <EntityLifecycleActions
            kind="scholar"
            id={draft.id}
            name={draft.name}
            status={draft.status}
            previewHref={`/scholars/${draft.slug}`}
            onChanged={(snapshot) => setDraft((current) => ({ ...current, status: snapshot.status }))}
            onDeleted={() => router.replace("/admin/scholars")}
          /> : null}
        </form> : null}
      </div>
    </AdminPageFrame>
  );
}

type AdminUser = {
  id: number;
  email: string;
  display_name: string;
  role: "admin" | "editor" | "reviewer" | "reader";
  is_active: boolean;
  date_joined: string;
  last_login: string | null;
  annotation_count: number;
  bookmark_count: number;
  saved_count: number;
  is_library_owner: boolean;
  can_manage_admin_role: boolean;
};

export function UsersAdmin() {
  const resource = useAdminResource<Paginated<AdminUser>>("/auth/users/");
  const [target, setTarget] = useState<number | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<AdminUser["role"]>("reader");
  const [active, setActive] = useState(true);
  const [newPassword, setNewPassword] = useState("");
  const [message, setMessage] = useState("");
  const selected = resource.data?.results.find((user) => user.id === target);
  const canManageAdminRole = Boolean(resource.data?.results.some((user) => user.can_manage_admin_role));

  function select(user: AdminUser) {
    setTarget(user.id);
    setDisplayName(user.display_name);
    setRole(user.role);
    setActive(user.is_active);
    setMessage("");
  }

  async function saveAccount() {
    const token = getServerSessionCredential();
    if (!token || target === null) return;
    try {
      await apiRequest(
        `/auth/users/${target}/`,
        {
          method: "PATCH",
          body: JSON.stringify({ display_name: displayName, role, is_active: active }),
        },
        token,
      );
      setMessage("账户状态和角色已经更新。");
      resource.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "账户更新失败。");
    }
  }

  async function reset(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token || target === null) {
      setMessage("请先从真实用户列表选择账户。");
      return;
    }
    try {
      await apiRequest(
        `/auth/users/${target}/set-password/`,
        { method: "POST", body: JSON.stringify({ new_password: newPassword }) },
        token,
      );
      setNewPassword("");
      setMessage("新密码已设置。系统没有读取或显示旧密码。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "设置失败。");
    }
  }

  return (
    <AdminPageFrame eyebrow="账户与权限" title="读者用户" description="管理员可以设置新密码、停用账户或调整角色。旧密码始终不可读取。">
      <ResourceState loading={resource.loading} error={resource.error} empty={!resource.data?.results.length} />
      <section className="user-admin-grid">
        <div className="admin-panel">
          <header><h2>用户列表</h2><span>{resource.data?.count ?? 0} 人</span></header>
          {resource.data?.results.map((user, index) => <button className={target === user.id ? "active" : ""} type="button" key={user.id} onClick={() => select(user)}><span>{index + 1}</span><p><strong>{user.display_name}{user.is_library_owner ? " · 最高管理员" : ""}</strong><small>{user.email}</small></p><b>{user.is_active ? user.role : "已停用"}</b></button>)}
        </div>
        <div className="user-admin-actions">
          <section className="admin-panel account-editor">
            <h2>账户状态</h2>
            <p>{selected?.email ?? "从左侧选择用户"}</p>
            <label><span>显示名</span><input value={displayName} onChange={(event) => setDisplayName(event.target.value)} disabled={!selected} /></label>
            <label><span>角色</span><select value={role} onChange={(event) => setRole(event.target.value as AdminUser["role"])} disabled={!selected || selected.is_library_owner || (selected.role === "admin" && !canManageAdminRole)}><option value="reader">读者</option><option value="editor">编辑</option><option value="reviewer">审核者</option>{canManageAdminRole || selected?.role === "admin" ? <option value="admin">管理员</option> : null}</select><small>{canManageAdminRole ? "只有你可以将读者升级为管理员。" : "管理员角色只能由最高管理员授予。"}</small></label>
            <label className="switch-row"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} disabled={!selected || selected.is_library_owner} /><span>账户有效</span></label>
            {selected ? <p className="account-counts">批注 {selected.annotation_count} · 书签 {selected.bookmark_count} · 收藏 {selected.saved_count}</p> : null}
            <button className="button secondary" type="button" onClick={saveAccount} disabled={!selected}>保存账户</button>
          </section>
          <form className="admin-panel direct-reset" onSubmit={reset}>
            <LockKeyhole size={25} />
            <h2>直接设置新密码</h2>
            <p>目标账户：{selected?.email ?? "尚未选择"}</p>
            <label><span>新密码</span><input type="password" minLength={10} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required disabled={!selected} /></label>
            <button className="button" type="submit" disabled={!selected}>设置新密码</button>
          </form>
          {message ? <p className="form-message" role="status">{message}</p> : null}
        </div>
      </section>
    </AdminPageFrame>
  );
}

type CloudProvider = {
  id: string;
  name: string;
  provider_type: string;
  endpoint_url: string;
  bucket: string;
  region: string;
  public_base_url: string;
  credential_reference: string;
  enabled: boolean;
  is_default: boolean;
  budget_policy: null | {
    monthly_budget: string | null;
    warning_ratio: number;
    stop_new_publications_ratio: number;
    pause_new_cdn_on_limit: boolean;
    preserve_existing_reads: boolean;
    notification_emails: string[];
  };
  latest_usage: null | {
    period: string;
    storage_bytes: number;
    egress_bytes: number;
    request_count: number;
    estimated_cost: string;
  };
  object_status_counts: Record<string, number>;
};

type CloudDraft = {
  id: string | null;
  name: string;
  endpoint: string;
  bucket: string;
  region: string;
  publicBaseUrl: string;
  credentialReference: string;
  enabled: boolean;
  isDefault: boolean;
  monthlyBudget: string;
  warningPercent: string;
  stopPercent: string;
  notificationEmails: string;
};

const emptyCloud: CloudDraft = {
  id: null,
  name: "",
  endpoint: "",
  bucket: "",
  region: "",
  publicBaseUrl: "",
  credentialReference: "S3",
  enabled: false,
  isDefault: false,
  monthlyBudget: "",
  warningPercent: "80",
  stopPercent: "100",
  notificationEmails: "",
};

export function DistributionAdmin() {
  const resource = useAdminResource<Paginated<CloudProvider>>("/distribution/providers/");
  const [draft, setDraft] = useState<CloudDraft>(emptyCloud);
  const [message, setMessage] = useState("");
  const [usagePeriod, setUsagePeriod] = useState(new Date().toISOString().slice(0, 7));
  const [usageCost, setUsageCost] = useState("");
  const [usageEgress, setUsageEgress] = useState("");
  const selected = resource.data?.results.find((provider) => provider.id === draft.id);
  const totalReady = resource.data?.results.reduce((sum, provider) => sum + (provider.object_status_counts.ready ?? 0), 0) ?? 0;
  const totalCost = resource.data?.results.reduce((sum, provider) => sum + Number(provider.latest_usage?.estimated_cost ?? 0), 0) ?? 0;

  function edit(provider: CloudProvider) {
    setDraft({
      id: provider.id,
      name: provider.name,
      endpoint: provider.endpoint_url,
      bucket: provider.bucket,
      region: provider.region,
      publicBaseUrl: provider.public_base_url,
      credentialReference: provider.credential_reference || "S3",
      enabled: provider.enabled,
      isDefault: provider.is_default,
      monthlyBudget: provider.budget_policy?.monthly_budget ?? "",
      warningPercent: String(Math.round((provider.budget_policy?.warning_ratio ?? 0.8) * 100)),
      stopPercent: String(Math.round((provider.budget_policy?.stop_new_publications_ratio ?? 1) * 100)),
      notificationEmails: provider.budget_policy?.notification_emails.join("\n") ?? "",
    });
  }

  async function save() {
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      const provider = await apiRequest<CloudProvider>(
        `/distribution/providers/${draft.id ? `${draft.id}/` : ""}`,
        {
          method: draft.id ? "PATCH" : "POST",
          body: JSON.stringify({
            name: draft.name,
            provider_type: "s3",
            endpoint_url: draft.endpoint,
            bucket: draft.bucket,
            region: draft.region,
            public_base_url: draft.publicBaseUrl,
            credential_reference: draft.credentialReference,
            enabled: draft.enabled,
            is_default: draft.isDefault,
            budget: {
              monthly_budget: draft.monthlyBudget || null,
              warning_ratio: Number(draft.warningPercent) / 100,
              stop_new_publications_ratio: Number(draft.stopPercent) / 100,
              pause_new_cdn_on_limit: true,
              preserve_existing_reads: true,
              notification_emails: splitValues(draft.notificationEmails),
            },
          }),
        },
        token,
      );
      edit(provider);
      setMessage("云端配置已保存。密钥只从部署环境读取，没有写入浏览器或数据库。");
      resource.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "配置保存失败。");
    }
  }

  async function addUsage(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token || !draft.id) return;
    try {
      await apiRequest(
        `/distribution/providers/${draft.id}/usage/`,
        {
          method: "POST",
          body: JSON.stringify({
            period: usagePeriod,
            storage_bytes: 0,
            egress_bytes: Math.round((Number(usageEgress) || 0) * 1024 * 1024 * 1024),
            request_count: 0,
            estimated_cost: Number(usageCost) || 0,
            source_payload: { source: "admin_manual_entry" },
          }),
        },
        token,
      );
      setMessage("本月用量快照已记录，并已经检查预算告警阈值。");
      resource.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "用量保存失败。");
    }
  }

  return (
    <AdminPageFrame eyebrow="在线阅读基础设施" title="云端分发" description="NAS 保存主副本。生产环境通过私有对象存储签名地址提供公开阅读副本。">
      <section className="distribution-cards">
        <StatusCard icon={HardDrive} title="NAS 主副本" value="部署目录" description="原始归档和规范副本不从后台删除" />
        <StatusCard icon={Cloud} title="对象存储" value={resource.data?.results.some((item) => item.enabled && item.is_default) ? "已启用" : "未启用"} description={`${resource.data?.count ?? 0} 个服务商配置`} />
        <StatusCard icon={Server} title="云端阅读副本" value={String(totalReady)} description="已完成校验的 PDF 副本" />
        <StatusCard icon={Database} title="最近月份估算" value={`¥ ${totalCost.toFixed(2)}`} description="来自服务商账单或人工用量快照" />
      </section>
      <div className="distribution-layout">
        <section className="admin-panel provider-list">
          <header><h2>服务商</h2><button type="button" onClick={() => setDraft(emptyCloud)}><Plus size={14} />新增</button></header>
          {resource.data?.results.map((provider) => <button className={draft.id === provider.id ? "active" : ""} type="button" key={provider.id} onClick={() => edit(provider)}><Cloud size={17} /><span><strong>{provider.name}</strong><small>{provider.bucket}</small></span><b>{provider.enabled ? provider.is_default ? "默认" : "启用" : "关闭"}</b></button>)}
          {!resource.data?.results.length ? <p className="empty-state">尚未配置对象存储。</p> : null}
        </section>
        <section className="cloud-config admin-panel">
          <header><h2>{draft.id ? "编辑对象存储" : "新增对象存储"}</h2><button type="button" onClick={() => setDraft(emptyCloud)}><RefreshCw size={14} />清空</button></header>
          <div className="form-grid">
            <label><span>服务商名称</span><input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="Cloudflare R2 / 阿里云 OSS / S3" /></label>
            <label><span>S3 Endpoint</span><input value={draft.endpoint} onChange={(event) => setDraft({ ...draft, endpoint: event.target.value })} placeholder="https://…" /></label>
            <label><span>Bucket</span><input value={draft.bucket} onChange={(event) => setDraft({ ...draft, bucket: event.target.value })} /></label>
            <label><span>区域</span><input value={draft.region} onChange={(event) => setDraft({ ...draft, region: event.target.value })} /></label>
            <label><span>凭据环境变量前缀</span><input value={draft.credentialReference} onChange={(event) => setDraft({ ...draft, credentialReference: event.target.value.toUpperCase() })} /><small>例如 S3 对应 S3_ACCESS_KEY_ID 和 S3_SECRET_ACCESS_KEY</small></label>
            <label><span>预留 CDN 域名</span><input value={draft.publicBaseUrl} onChange={(event) => setDraft({ ...draft, publicBaseUrl: event.target.value })} /></label>
            <label><span>月度预算上限</span><input type="number" min="0" step="0.01" value={draft.monthlyBudget} onChange={(event) => setDraft({ ...draft, monthlyBudget: event.target.value })} /></label>
            <label><span>费用告警比例</span><input type="number" min="0" max="100" value={draft.warningPercent} onChange={(event) => setDraft({ ...draft, warningPercent: event.target.value })} /></label>
            <label><span>停止新发布比例</span><input type="number" min="1" value={draft.stopPercent} onChange={(event) => setDraft({ ...draft, stopPercent: event.target.value })} /></label>
            <label className="wide"><span>告警邮箱，每行一个</span><textarea rows={3} value={draft.notificationEmails} onChange={(event) => setDraft({ ...draft, notificationEmails: event.target.value })} /></label>
          </div>
          <label className="switch-row"><input type="checkbox" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} /><span>启用云端公开阅读</span><small>正式发布仍需云端副本完成校验。</small></label>
          <label className="switch-row"><input type="checkbox" checked={draft.isDefault} onChange={(event) => setDraft({ ...draft, isDefault: event.target.checked })} /><span>设为默认服务商</span><small>系统只允许一个默认服务商。</small></label>
          <button className="button" type="button" onClick={save}><Save size={15} />保存配置</button>
        </section>
        <form className="admin-panel usage-editor" onSubmit={addUsage}>
          <header><h2>月度用量快照</h2></header>
          <p>服务商账单适配器尚未接入时，可以记录账单估算值。达到阈值会发送告警并阻止新的公开同步，现有阅读保持可用。</p>
          <label><span>月份</span><input type="month" value={usagePeriod} onChange={(event) => setUsagePeriod(event.target.value)} /></label>
          <label><span>估算费用</span><input type="number" min="0" step="0.01" value={usageCost} onChange={(event) => setUsageCost(event.target.value)} /></label>
          <label><span>下载流量 GB</span><input type="number" min="0" step="0.01" value={usageEgress} onChange={(event) => setUsageEgress(event.target.value)} /></label>
          <button className="button secondary" type="submit" disabled={!draft.id}>记录用量</button>
          {selected?.latest_usage ? <small>最近记录 {selected.latest_usage.period} · ¥ {selected.latest_usage.estimated_cost}</small> : null}
        </form>
      </div>
      {message ? <p className="form-message" role="status">{message}</p> : null}
    </AdminPageFrame>
  );
}

type BackupJob = {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  destination_path: string;
  include_originals: boolean;
  archive_path: string;
  checksum: string;
  error_message: string;
  created_at: string;
};

type OcrRuntime = {
  mode: "nas_preferred" | "nas_only" | "remote_only";
  remote_url: string;
  remote_model: string;
  nas_url: string;
  nas_configured: boolean;
  remote_key_configured: boolean;
  remote_configured: boolean;
  remote_fallback_available: boolean;
  saved_configuration_version: string;
  effective_configuration: {
    mode: string;
    nas_url_configured: boolean;
    remote_fallback_available: boolean;
    loads_settings_per_job: boolean;
  };
  restart_required: boolean;
  last_success_at: string | null;
  last_job: {
    id: string;
    status: string;
    engine: string;
    settings_version: string;
    attempt: number;
    error: string;
    created_at: string;
    finished_at: string | null;
  } | null;
};

const defaultOcrRuntime: OcrRuntime = {
  mode: "nas_preferred",
  remote_url: "",
  remote_model: "",
  nas_url: "",
  nas_configured: false,
  remote_key_configured: false,
  remote_configured: false,
  remote_fallback_available: false,
  saved_configuration_version: "environment-default",
  effective_configuration: { mode: "nas_preferred", nas_url_configured: false, remote_fallback_available: false, loads_settings_per_job: true },
  restart_required: false,
  last_success_at: null,
  last_job: null,
};

type SemanticRuntime = {
  engine: "lightweight" | "meilisearch_hybrid";
  provider: "huggingFace" | "openAi" | "ollama";
  embedder_name: string;
  model: string;
  model_repo_id: string;
  model_local_path: string;
  model_revision: string;
  dimensions: number | null;
  pooling: "useModel" | "forceMean" | "forceCls";
  offline_mode: boolean;
  service_url: string;
  semantic_ratio: number;
  reranker: string;
  query_rewrite_enabled: boolean;
  max_results_per_work: number;
  api_key_configured: boolean;
  model_health?: {
    configured: boolean;
    available: boolean | null;
    reason: string;
    cache_root?: string;
    files?: Record<string, boolean>;
  };
  effective?: boolean;
  apply_error?: string;
  restart_required?: boolean;
  pending_configuration?: Partial<SemanticRuntime> | null;
  pending_model_health?: SemanticRuntime["model_health"] | null;
  task?: { taskUid?: number; status?: string; version_id?: string; index_uid?: string; type?: string } | null;
};

type AIRuntimeCapability = "metadata_extraction" | "library_qa" | "field_enrichment_optional";

type AIRuntimeProfile = {
  key: string;
  capability: AIRuntimeCapability;
  provider: "none" | "ollama" | "vllm" | "openai_compatible";
  model: string;
  enabled: boolean;
  temperature: number;
  max_output_tokens: number;
  timeout_seconds: number;
  max_input_chars: number;
  endpoint_alias: string;
  credential_alias: string;
  retrieval_profile: "stable" | "experimental_v2";
  answer_behavior: string;
  fallback_profile_key?: string;
  reasoning?: Record<string, string | number | boolean | null>;
  environment?: {
    endpoint_configured: boolean;
    credential_configured: boolean;
    restart_may_be_required: boolean;
  };
};

type AIRuntimeDocument = {
  version: string;
  active: Record<AIRuntimeCapability, string>;
  profiles: AIRuntimeProfile[];
  source: string;
  secret_values_exposed: false;
  hot_reload_fields: string[];
  deployment_fields: string[];
};

const aiCapabilityLabels: Record<AIRuntimeCapability, string> = {
  metadata_extraction: "元数据提取",
  library_qa: "Ask Library",
  field_enrichment_optional: "联网补全可选判断",
};

const defaultSemanticRuntime: SemanticRuntime = {
  engine: "lightweight",
  provider: "huggingFace",
  embedder_name: "social-science-library",
  model: "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
  model_repo_id: "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
  model_local_path: "/models",
  model_revision: "main",
  dimensions: null,
  pooling: "useModel",
  offline_mode: true,
  service_url: "",
  semantic_ratio: 0.72,
  reranker: "rules",
  query_rewrite_enabled: false,
  max_results_per_work: 2,
  api_key_configured: false,
};

export function SettingsAdmin() {
  const configResource = useAdminResource<SiteConfig>("/catalog/site-config/");
  const submissionResource = useAdminResource<{ email: string }>("/catalog/admin/reader-submission/");
  const ocrResource = useAdminResource<OcrRuntime>("/catalog/admin/ocr-runtime/");
  const semanticResource = useAdminResource<SemanticRuntime>("/catalog/admin/semantic-runtime/");
  const aiRuntimeResource = useAdminResource<AIRuntimeDocument>("/reading/admin/ai-runtime-profiles/");
  const backups = useAdminResource<Paginated<BackupJob>>("/distribution/backups/");
  const [draft, setDraft] = useState<SiteConfig | null>(null);
  const [ocrDraft, setOcrDraft] = useState<OcrRuntime | null>(null);
  const [semanticDraft, setSemanticDraft] = useState<SemanticRuntime | null>(null);
  const [aiRuntimeDraft, setAiRuntimeDraft] = useState<AIRuntimeDocument | null>(null);
  const [submissionEmailDraft, setSubmissionEmail] = useState<string | null>(null);
  const [backupPath, setBackupPath] = useState("/data/backups");
  const [includeOriginals, setIncludeOriginals] = useState(false);
  const [message, setMessage] = useState("");
  const config = draft ?? configResource.data ?? defaultSiteConfig;
  const submissionEmail = submissionEmailDraft
    ?? submissionResource.data?.email
    ?? "submissions@example.com";
  const ocrRuntime = ocrDraft ?? ocrResource.data ?? defaultOcrRuntime;
  const semanticRuntime = semanticDraft
    ?? semanticResource.data
    ?? defaultSemanticRuntime;
  const semanticRuntimeReady = Boolean(semanticDraft ?? semanticResource.data);
  const aiRuntime = aiRuntimeDraft ?? aiRuntimeResource.data;

  function updateConfig(patch: Partial<SiteConfig>) {
    setDraft({ ...config, ...patch });
  }

  async function saveConfig(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      const saved = await apiRequest<SiteConfig>(
        "/catalog/site-config/",
        { method: "PUT", body: JSON.stringify(config) },
        token,
      );
      setDraft(saved);
      setMessage("网站名称、首页文字、导航和区块标题已经保存并立即生效。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "内容保存失败。");
    }
  }

  async function createBackup() {
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      await apiRequest(
        "/distribution/backups/",
        {
          method: "POST",
          body: JSON.stringify({
            destination_path: backupPath,
            include_originals: includeOriginals,
          }),
        },
        token,
      );
      setMessage("手动备份已经进入任务队列。可以刷新下方记录查看归档路径和校验值。");
      backups.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "备份创建失败。");
    }
  }

  async function saveSubmissionEmail(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      const saved = await apiRequest<{ email: string }>(
        "/catalog/admin/reader-submission/",
        {
          method: "PUT",
          body: JSON.stringify({ email: submissionEmail.trim() }),
        },
        token,
      );
      setSubmissionEmail(saved.email);
      setMessage("读者中心投稿邮箱已经保存。荐书时会打开读者自己的邮件应用。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "投稿邮箱保存失败。");
    }
  }

  async function saveOcrRuntime(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      const saved = await apiRequest<OcrRuntime>(
        "/catalog/admin/ocr-runtime/",
        {
          method: "PUT",
          body: JSON.stringify({
            mode: ocrRuntime.mode,
            remote_url: ocrRuntime.remote_url.trim(),
            remote_model: ocrRuntime.remote_model.trim(),
          }),
        },
        token,
      );
      setOcrDraft(saved);
      setMessage("OCR 运行方式已经保存。新上传的扫描 PDF 将使用该设置。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "OCR 设置保存失败。");
    }
  }

  async function testOcrRuntime(action: "test_nas" | "test_remote") {
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      const result = await apiRequest<{ reachable: boolean; detail: string; target: string }>(
        "/catalog/admin/ocr-runtime/",
        { method: "POST", body: JSON.stringify({ action }) },
        token,
      );
      setMessage(`${result.target === "nas" ? "NAS OCR" : "远程 OCR"} 测试结果：${result.reachable ? "可连接" : "不可用"}。${result.detail || ""}`);
      ocrResource.refresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "OCR 连通性测试失败。");
    }
  }

  async function saveSemanticRuntime(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token || !semanticRuntimeReady) {
      setMessage("尚未读取服务器上的观点检索配置，未执行保存。");
      return;
    }
    try {
      const saved = await apiRequest<SemanticRuntime>(
        "/catalog/admin/semantic-runtime/",
        {
          method: "PUT",
          body: JSON.stringify({
            engine: semanticRuntime.engine,
            provider: semanticRuntime.provider,
            embedder_name: semanticRuntime.embedder_name.trim(),
            model: semanticRuntime.model.trim(),
            model_repo_id: semanticRuntime.model_repo_id.trim(),
            model_local_path: semanticRuntime.model_local_path.trim(),
            model_revision: semanticRuntime.model_revision.trim(),
            dimensions: semanticRuntime.dimensions,
            pooling: semanticRuntime.pooling,
            offline_mode: semanticRuntime.offline_mode,
            service_url: semanticRuntime.service_url.trim(),
            semantic_ratio: semanticRuntime.semantic_ratio,
            reranker: semanticRuntime.reranker,
            query_rewrite_enabled: semanticRuntime.query_rewrite_enabled,
            max_results_per_work: semanticRuntime.max_results_per_work,
          }),
        },
        token,
      );
      setSemanticDraft(saved);
      setMessage(
        saved.task?.version_id
          ? `新索引版本 ${saved.task.index_uid || saved.task.version_id} 正在后台构建；验证和人工切换前，当前生产配置保持不变。`
          : saved.engine === "meilisearch_hybrid"
          ? `向量混合检索设置已提交${saved.task?.taskUid ? `，索引任务 ${saved.task.taskUid} 正在后台运行` : ""}。`
          : "已启用关键词回退检索，不会额外加载嵌入模型。",
      );
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "观点检索设置保存失败。");
    }
  }

  function updateAiProfile(profileKey: string, patch: Partial<AIRuntimeProfile>) {
    if (!aiRuntime) return;
    setAiRuntimeDraft({
      ...aiRuntime,
      profiles: aiRuntime.profiles.map((profile) => (
        profile.key === profileKey ? { ...profile, ...patch } : profile
      )),
    });
  }

  async function saveAiRuntime(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token || !aiRuntime) {
      setMessage("尚未读取服务器上的 AI Runtime 配置，未执行保存。");
      return;
    }
    try {
      const saved = await apiRequest<AIRuntimeDocument>(
        "/reading/admin/ai-runtime-profiles/",
        {
          method: "PUT",
          body: JSON.stringify({
            active: aiRuntime.active,
            profiles: aiRuntime.profiles.map((profile) => {
              const persisted = { ...profile };
              delete persisted.environment;
              return persisted;
            }),
          }),
        },
        token,
      );
      setAiRuntimeDraft(saved);
      setMessage("AI Runtime profiles 已保存。非密钥参数会在下一次任务或问答时读取。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "AI Runtime 设置保存失败。");
    }
  }

  async function testAiRuntime(profileKey: string) {
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      const result = await apiRequest<{
        available: boolean;
        detail: string;
        profile_key: string;
      }>(
        "/reading/admin/ai-runtime-profiles/test/",
        { method: "POST", body: JSON.stringify({ profile_key: profileKey }) },
        token,
      );
      setMessage(`${result.profile_key}：${result.available ? "模型服务可用" : "模型服务不可用"}。${result.detail}`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "AI Runtime 连通性测试失败。");
    }
  }

  return (
    <AdminPageFrame eyebrow="网站内容" title="网站设置" description="名称、首页文字、导航和主要区块标题都可编辑。未启用自动每日备份。">
      <section className="settings-grid">
        <form className="admin-panel settings-content-form" onSubmit={saveConfig}>
          <header><h2>品牌与首页</h2></header>
          <label><span>网站名称</span><input value={config.site_name} onChange={(event) => updateConfig({ site_name: event.target.value })} /></label>
          <label><span>英文标识，每行一段</span><textarea rows={3} value={config.wordmark_lines.join("\n")} onChange={(event) => updateConfig({ wordmark_lines: splitLines(event.target.value) })} /></label>
          <label><span>首页左侧主标题，每行一段</span><textarea rows={3} value={config.home_title_left_lines.join("\n")} onChange={(event) => updateConfig({ home_title_left_lines: splitLines(event.target.value) })} /></label>
          <label><span>首页右侧主标题，每行一段</span><textarea rows={3} value={config.home_title_right_lines.join("\n")} onChange={(event) => updateConfig({ home_title_right_lines: splitLines(event.target.value) })} /></label>
          <label><span>首页简介，每行一段</span><textarea rows={4} value={config.intro_lines.join("\n")} onChange={(event) => updateConfig({ intro_lines: splitLines(event.target.value) })} /></label>
          <label><span>关于页标题</span><input value={config.about_title} onChange={(event) => updateConfig({ about_title: event.target.value })} /></label>
          <label><span>关于页说明</span><textarea rows={5} value={config.about_body} onChange={(event) => updateConfig({ about_body: event.target.value })} /></label>
          <details className="about-settings-fields" open>
            <summary>关于书库页面内容</summary>
            <label><span>建设缘起标题</span><input value={config.about_why_title} onChange={(event) => updateConfig({ about_why_title: event.target.value })} /></label>
            <label><span>建设缘起正文</span><textarea rows={6} value={config.about_why_body} onChange={(event) => updateConfig({ about_why_body: event.target.value })} /></label>
            <label><span>寻找出处标题</span><input value={config.about_feature_search_title} onChange={(event) => updateConfig({ about_feature_search_title: event.target.value })} /></label>
            <label><span>寻找出处说明</span><textarea rows={3} value={config.about_feature_search_body} onChange={(event) => updateConfig({ about_feature_search_body: event.target.value })} /></label>
            <label><span>阅读整理标题</span><input value={config.about_feature_read_title} onChange={(event) => updateConfig({ about_feature_read_title: event.target.value })} /></label>
            <label><span>阅读整理说明</span><textarea rows={3} value={config.about_feature_read_body} onChange={(event) => updateConfig({ about_feature_read_body: event.target.value })} /></label>
            <label><span>知识关系标题</span><input value={config.about_feature_knowledge_title} onChange={(event) => updateConfig({ about_feature_knowledge_title: event.target.value })} /></label>
            <label><span>知识关系说明</span><textarea rows={3} value={config.about_feature_knowledge_body} onChange={(event) => updateConfig({ about_feature_knowledge_body: event.target.value })} /></label>
            <label><span>入库流程标题</span><input value={config.about_ingestion_title} onChange={(event) => updateConfig({ about_ingestion_title: event.target.value })} /></label>
            <label><span>入库流程说明</span><textarea rows={4} value={config.about_ingestion_body} onChange={(event) => updateConfig({ about_ingestion_body: event.target.value })} /></label>
            <label><span>开放原则标题</span><input value={config.about_access_title} onChange={(event) => updateConfig({ about_access_title: event.target.value })} /></label>
            <label><span>开放原则说明</span><textarea rows={3} value={config.about_access_body} onChange={(event) => updateConfig({ about_access_body: event.target.value })} /></label>
            <label><span>版权说明标题</span><input value={config.about_rights_title} onChange={(event) => updateConfig({ about_rights_title: event.target.value })} /></label>
            <label><span>版权说明正文</span><textarea rows={3} value={config.about_rights_body} onChange={(event) => updateConfig({ about_rights_body: event.target.value })} /></label>
            <label><span>隐私标题</span><input value={config.about_privacy_title} onChange={(event) => updateConfig({ about_privacy_title: event.target.value })} /></label>
            <label><span>隐私说明</span><textarea rows={3} value={config.about_privacy_body} onChange={(event) => updateConfig({ about_privacy_body: event.target.value })} /></label>
            <label><span>结果提醒标题</span><input value={config.about_warning_title} onChange={(event) => updateConfig({ about_warning_title: event.target.value })} /></label>
            <label><span>结果提醒正文</span><textarea rows={3} value={config.about_warning_body} onChange={(event) => updateConfig({ about_warning_body: event.target.value })} /></label>
          </details>
          <label><span>版权文字</span><input value={config.copyright_text} onChange={(event) => updateConfig({ copyright_text: event.target.value })} /></label>
          <div className="settings-label-grid">
            {Object.entries(config.navigation).map(([key, value]) => <label key={key}><span>导航 {key}</span><input value={value} onChange={(event) => updateConfig({ navigation: { ...config.navigation, [key]: event.target.value } })} /></label>)}
            {Object.entries(config.sections).map(([key, value]) => <label key={key}><span>首页区块 {key}</span><input value={value} onChange={(event) => updateConfig({ sections: { ...config.sections, [key]: event.target.value } })} /></label>)}
          </div>
          <button className="button" type="submit"><Save size={15} />保存内容</button>
        </form>
        <form className="admin-panel submission-email-settings" onSubmit={saveSubmissionEmail}>
          <header><h2>读者荐书投稿</h2></header>
          <p>网站不直接接收 PDF，也不依赖 SMTP。读者填写荐书信息后会打开自己的邮件应用。</p>
          <label><span>投稿邮箱</span><input type="email" value={submissionEmail} onChange={(event) => setSubmissionEmail(event.target.value)} required /></label>
          <button className="button secondary" type="submit"><Save size={15} />保存投稿邮箱</button>
        </form>
        <form className="admin-panel ocr-runtime-settings" onSubmit={saveOcrRuntime}>
          <header><h2>OCR 资源</h2></header>
          <p>配置与运行状态分开显示。远程 URL、模型和 API Key 必须同时齐全，远程回退才会参与任务。</p>
          <label>
            <span>运行方式</span>
            <select
              value={ocrRuntime.mode}
              onChange={(event) => setOcrDraft({
                ...ocrRuntime,
                mode: event.target.value as OcrRuntime["mode"],
              })}
            >
              <option value="nas_preferred">NAS 优先，失败后使用远程</option>
              <option value="nas_only">只使用 NAS PaddleOCR</option>
              <option value="remote_only">只使用远程解析网关</option>
            </select>
          </label>
          <label><span>远程网关地址</span><input type="url" value={ocrRuntime.remote_url} onChange={(event) => setOcrDraft({ ...ocrRuntime, remote_url: event.target.value })} placeholder="https://example.com/v1/parse-pdf" /></label>
          <label><span>远程模型标识</span><input value={ocrRuntime.remote_model} onChange={(event) => setOcrDraft({ ...ocrRuntime, remote_model: event.target.value })} placeholder="远程回退必填" /></label>
          <dl className="ocr-runtime-status">
            <div><dt>NAS PaddleOCR</dt><dd>{ocrRuntime.nas_configured ? "已配置" : "未配置"}</dd></div>
            <div><dt>远程 API 密钥</dt><dd>{ocrRuntime.remote_key_configured ? "已通过环境变量配置" : "未配置"}</dd></div>
            <div><dt>远程回退</dt><dd>{ocrRuntime.remote_fallback_available ? "配置完整" : "不可用"}</dd></div>
            <div><dt>实际加载方式</dt><dd>{ocrRuntime.effective_configuration.loads_settings_per_job ? "每个任务读取最新设置" : "需重启 worker"}</dd></div>
            <div><dt>最近成功</dt><dd>{ocrRuntime.last_success_at ? new Date(ocrRuntime.last_success_at).toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong" }) : "尚无记录"}</dd></div>
            <div><dt>最近任务引擎</dt><dd>{ocrRuntime.last_job?.engine || "尚无任务"}</dd></div>
          </dl>
          {ocrRuntime.last_job?.error ? <p className="attempt-error">最近错误：{ocrRuntime.last_job.error}</p> : null}
          <small>远程密钥只写入服务器的 <code>OCR_REMOTE_API_KEY</code> 环境变量，后台页面不会读取或显示密钥原文。</small>
          <div className="admin-action-row"><button className="button secondary" type="button" onClick={() => void testOcrRuntime("test_nas")}>测试 NAS OCR</button><button className="button secondary" type="button" onClick={() => void testOcrRuntime("test_remote")} disabled={!ocrRuntime.remote_fallback_available}>测试远程 OCR</button><button className="button" type="submit"><Save size={15} />保存 OCR 设置</button></div>
        </form>
        <form className="admin-panel ai-runtime-settings" onSubmit={saveAiRuntime}>
          <header><h2>AI Runtime</h2></header>
          <p>各项能力可以使用不同的 provider 与模型。密钥和实际 endpoint 只由服务器环境提供，页面不会读取或保存其原文。</p>
          {aiRuntime ? <>
            {aiRuntime.profiles.map((profile) => (
              <fieldset key={profile.key}>
                <legend>{aiCapabilityLabels[profile.capability]} · {profile.key}</legend>
                <label className="switch-row">
                  <input type="checkbox" checked={profile.enabled} onChange={(event) => updateAiProfile(profile.key, { enabled: event.target.checked })} />
                  <span>启用该 profile</span>
                </label>
                <label><span>Provider</span><select value={profile.provider} onChange={(event) => updateAiProfile(profile.key, { provider: event.target.value as AIRuntimeProfile["provider"] })}><option value="none">未配置</option><option value="ollama">Ollama</option><option value="vllm">vLLM</option><option value="openai_compatible">OpenAI-compatible</option></select></label>
                <label><span>模型标识</span><input value={profile.model} onChange={(event) => updateAiProfile(profile.key, { model: event.target.value })} /></label>
                <label><span>Temperature</span><input type="number" min="0" max="2" step="0.05" value={profile.temperature} onChange={(event) => updateAiProfile(profile.key, { temperature: Number(event.target.value) })} /></label>
                <label><span>最大输出 tokens</span><input type="number" min="128" max="8192" value={profile.max_output_tokens} onChange={(event) => updateAiProfile(profile.key, { max_output_tokens: Number(event.target.value) })} /></label>
                <label><span>超时，秒</span><input type="number" min="3" max="600" value={profile.timeout_seconds} onChange={(event) => updateAiProfile(profile.key, { timeout_seconds: Number(event.target.value) })} /></label>
                {profile.capability === "library_qa" ? <label><span>馆藏检索配置</span><select value={profile.retrieval_profile} onChange={(event) => updateAiProfile(profile.key, { retrieval_profile: event.target.value as AIRuntimeProfile["retrieval_profile"] })}><option value="stable">Stable，公开认可路径</option><option value="experimental_v2">Experimental V2，仅管理员显式使用</option></select></label> : null}
                <dl className="ocr-runtime-status">
                  <div><dt>Endpoint</dt><dd>{profile.environment?.endpoint_configured ? "服务器已配置" : "服务器未配置"}</dd></div>
                  <div><dt>Credential</dt><dd>{profile.environment?.credential_configured ? "服务器已配置或不需要" : "服务器未配置"}</dd></div>
                  <div><dt>生效方式</dt><dd>模型参数热读取；密钥和 endpoint 需部署环境变更</dd></div>
                </dl>
                <button className="button secondary" type="button" onClick={() => void testAiRuntime(profile.key)}>测试配置</button>
              </fieldset>
            ))}
            <small>当前配置来源：{aiRuntime.source}。健康检查失败不会自动停用 profile。</small>
            <button className="button" type="submit"><Save size={15} />保存 AI Runtime</button>
          </> : <p className={aiRuntimeResource.error ? "attempt-error" : "admin-help"}>{aiRuntimeResource.error || "正在读取 AI Runtime 配置。"}</p>}
        </form>
        <form className="admin-panel semantic-runtime-settings" onSubmit={saveSemanticRuntime}>
          <header><h2>观点检索资源</h2><Link href="/admin/semantic-index">打开索引管理</Link></header>
          <p>原文检索不受这里影响。向量模式会为公开全文段落生成嵌入；发生故障时，是否完成关键词降级要以测试查询返回的运行结果为准。</p>
          {semanticRuntimeReady ? <>
          <label>
            <span>检索方式</span>
            <select
              value={semanticRuntime.engine}
              onChange={(event) => setSemanticDraft({
                ...semanticRuntime,
                engine: event.target.value as SemanticRuntime["engine"],
              })}
            >
              <option value="lightweight">轻量模式，NAS 资源占用较低</option>
              <option value="meilisearch_hybrid">Meilisearch 向量混合检索</option>
            </select>
          </label>
          <label>
            <span>嵌入模型来源</span>
            <select
              value={semanticRuntime.provider}
              onChange={(event) => setSemanticDraft({
                ...semanticRuntime,
                provider: event.target.value as SemanticRuntime["provider"],
              })}
              disabled={semanticRuntime.engine !== "meilisearch_hybrid"}
            >
              <option value="huggingFace">NAS 本地 Hugging Face 模型</option>
              <option value="openAi">OpenAI 兼容嵌入接口</option>
              <option value="ollama">Ollama 服务</option>
            </select>
          </label>
          <label><span>嵌入器名称</span><input value={semanticRuntime.embedder_name} onChange={(event) => setSemanticDraft({ ...semanticRuntime, embedder_name: event.target.value })} disabled={semanticRuntime.engine !== "meilisearch_hybrid"} /></label>
          <label><span>模型标识</span><input value={semanticRuntime.model_repo_id} onChange={(event) => setSemanticDraft({ ...semanticRuntime, model: event.target.value, model_repo_id: event.target.value })} disabled={semanticRuntime.engine !== "meilisearch_hybrid"} /></label>
          <label><span>NAS 模型缓存目录</span><input value={semanticRuntime.model_local_path} onChange={(event) => setSemanticDraft({ ...semanticRuntime, model_local_path: event.target.value })} disabled={semanticRuntime.engine !== "meilisearch_hybrid" || semanticRuntime.provider !== "huggingFace"} /></label>
          <label><span>模型 revision</span><input value={semanticRuntime.model_revision} onChange={(event) => setSemanticDraft({ ...semanticRuntime, model_revision: event.target.value })} disabled={semanticRuntime.engine !== "meilisearch_hybrid" || semanticRuntime.provider !== "huggingFace"} /></label>
          <label><span>向量维度</span><input type="number" min="1" value={semanticRuntime.dimensions ?? ""} onChange={(event) => setSemanticDraft({ ...semanticRuntime, dimensions: event.target.value ? Number(event.target.value) : null })} placeholder="由模型决定" disabled={semanticRuntime.engine !== "meilisearch_hybrid"} /></label>
          <label><span>池化方式</span><select value={semanticRuntime.pooling} onChange={(event) => setSemanticDraft({ ...semanticRuntime, pooling: event.target.value as SemanticRuntime["pooling"] })} disabled={semanticRuntime.engine !== "meilisearch_hybrid" || semanticRuntime.provider !== "huggingFace"}><option value="useModel">使用模型默认</option><option value="forceMean">平均池化</option><option value="forceCls">CLS 池化</option></select></label>
          <label className="switch-row"><input type="checkbox" checked={semanticRuntime.offline_mode} onChange={(event) => setSemanticDraft({ ...semanticRuntime, offline_mode: event.target.checked })} disabled={semanticRuntime.provider !== "huggingFace"} /><span>本地模型严格离线运行</span><small>启用后缺少模型文件会直接降级关键词检索，不尝试访问 Hugging Face 公网。</small></label>
          <label><span>Ollama 服务地址</span><input type="url" value={semanticRuntime.service_url} onChange={(event) => setSemanticDraft({ ...semanticRuntime, service_url: event.target.value })} placeholder="http://ollama:11434" disabled={semanticRuntime.engine !== "meilisearch_hybrid" || semanticRuntime.provider !== "ollama"} /></label>
          <label>
            <span>混合检索权重 {Math.round(semanticRuntime.semantic_ratio * 100)}%</span>
            <input type="range" min="0" max="1" step="0.01" value={semanticRuntime.semantic_ratio} onChange={(event) => setSemanticDraft({ ...semanticRuntime, semantic_ratio: Number(event.target.value) })} disabled={semanticRuntime.engine !== "meilisearch_hybrid"} />
            <small>只用于融合关键词结果与语义结果，不是检索质量分数。测试查询会显示服务端实际采用的数值。</small>
          </label>
          <label>
            <span>重排方式</span>
            <select value={semanticRuntime.reranker} onChange={(event) => setSemanticDraft({ ...semanticRuntime, reranker: event.target.value })}>
              <option value="rules">内置规则重排</option>
            </select>
            <small>当前运行代码只接入这一方式。外部模型重排需要先定义和验证服务协议，不能只保存一个模型名称。</small>
          </label>
          <label><span>每本文献默认上限</span><input type="number" min="0" max="20" value={semanticRuntime.max_results_per_work} onChange={(event) => setSemanticDraft({ ...semanticRuntime, max_results_per_work: Number(event.target.value) })} /></label>
          <label className="switch-row"><input type="checkbox" checked={semanticRuntime.query_rewrite_enabled} onChange={(event) => setSemanticDraft({ ...semanticRuntime, query_rewrite_enabled: event.target.checked })} /><span>展示并使用查询改写候选</span></label>
          <dl className="ocr-runtime-status">
            <div><dt>远程嵌入密钥</dt><dd>{semanticRuntime.api_key_configured ? "已通过环境变量配置" : "未配置"}</dd></div>
            <div><dt>当前资源策略</dt><dd>{semanticRuntime.engine === "lightweight" ? "低占用" : "生成向量索引"}</dd></div>
            <div><dt>模型文件检查</dt><dd>{semanticRuntime.model_health?.available === true ? "本地缓存完整" : semanticRuntime.model_health?.available === false ? "语义模型不可用" : "需要测试查询"}</dd></div>
            <div><dt>保存后生效</dt><dd>{semanticRuntime.restart_required ? "需要重启" : "无需重启"}</dd></div>
          </dl>
          {semanticRuntime.model_health?.reason ? <p className={semanticRuntime.model_health.available ? "admin-help" : "attempt-error"}>{semanticRuntime.model_health.reason}</p> : null}
          {semanticRuntime.engine === "meilisearch_hybrid" && semanticRuntime.model_health?.available === false ? <small className="attempt-error">混合检索权重当前不会生效。安装完整本地模型后，请运行测试查询验证关键词回退与混合检索，再建立新版本索引。</small> : null}
          {semanticRuntime.apply_error ? <p className="attempt-error">设置已保存，但运行配置应用失败：{semanticRuntime.apply_error}</p> : null}
          <small>本地多语种模型会占用 NAS 的 CPU、内存和索引空间。建议先用轻量模式试运行。远程密钥只写入 <code>SEMANTIC_EMBEDDING_API_KEY</code>，后台不会显示原文。</small>
          <button className="button secondary" type="submit"><Save size={15} />保存观点检索设置</button>
          </> : (
            <p className={semanticResource.error ? "attempt-error" : "admin-help"} role={semanticResource.error ? "alert" : "status"}>
              {semanticResource.error || "正在读取服务器上的有效配置。载入完成前不会显示或保存默认值。"}
            </p>
          )}
        </form>
        <section className="admin-panel backup-settings">
          <header><h2>手动备份</h2><button type="button" onClick={backups.refresh}><RefreshCw size={14} />刷新</button></header>
          <Download size={28} />
          <p>备份写入指定 NAS 目录，并生成数据库、文件清单和 SHA-256 校验值。不会自动安排每日任务。</p>
          <label><span>容器内备份目录</span><input value={backupPath} onChange={(event) => setBackupPath(event.target.value)} /></label>
          <label className="switch-row"><input type="checkbox" checked={includeOriginals} onChange={(event) => setIncludeOriginals(event.target.checked)} /><span>归档内再包含原始 PDF</span></label>
          <button className="button secondary" type="button" onClick={createBackup}>立即创建备份</button>
          <small>同一台 NAS 上的备份可恢复误操作，但不能替代异地灾难备份。</small>
          <div className="backup-history">
            {backups.data?.results.slice(0, 6).map((job) => <article key={job.id}><header><strong>{job.status}</strong><time>{new Date(job.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong" })}</time></header><p>{job.archive_path || job.destination_path}</p>{job.checksum ? <small>SHA-256 {job.checksum}</small> : null}{job.error_message ? <small className="attempt-error">{job.error_message}</small> : null}</article>)}
            {!backups.data?.results.length ? <p className="empty-state">尚无手动备份记录。</p> : null}
          </div>
        </section>
      </section>
      {message ? <p className="form-message" role="status">{message}</p> : null}
    </AdminPageFrame>
  );
}

function AdminPageFrame({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children: React.ReactNode }) {
  return <div className="admin-page"><header className="admin-page-title"><div><p>{eyebrow}</p><h1>{title}</h1><span>{description}</span></div></header>{children}</div>;
}

function Toolbar({
  query,
  onQueryChange,
  onSubmit,
  onCreate,
  createHref,
  createLabel,
}: {
  query: string;
  onQueryChange: (value: string) => void;
  onSubmit: () => void;
  onCreate?: () => void;
  createHref?: string;
  createLabel: string;
}) {
  return (
    <form className="admin-list-toolbar" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
      <label><Search size={15} /><input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="搜索……" /></label>
      {createHref ? <Link href={createHref}><Plus size={15} />{createLabel}</Link> : <button type="button" onClick={onCreate}><Plus size={15} />{createLabel}</button>}
    </form>
  );
}

function StatusCard({ icon: Icon, title, value, description }: { icon: typeof Cloud; title: string; value: string; description: string }) {
  return <article className="admin-panel"><Icon size={23} /><p><strong>{title}</strong><span>{description}</span></p><b>{value}</b></article>;
}

function ResourceState({ loading, error, empty }: { loading: boolean; error: string; empty: boolean }) {
  if (loading) return <p className="admin-resource-state"><LoaderCircle className="spin" size={17} />正在读取真实数据……</p>;
  if (error) return <p className="admin-resource-state error"><AlertCircle size={17} />{error}</p>;
  if (empty) return <p className="admin-resource-state">当前没有记录。</p>;
  return null;
}

function splitLines(value: string) {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

function editorLines(value: string) {
  return value === "" ? [] : value.split(/\r?\n/);
}

function editorStructuredRows(value: string, fields: string[]): StructuredRow[] {
  if (value === "") return [];
  return value.split(/\r?\n/).map((line) => {
    const parts = line.split(/[|｜]/);
    return Object.fromEntries(fields.map((field, index) => [field, parts[index] ?? ""]));
  });
}

function formatEditorRows(rows: StructuredRow[], fields: string[]) {
  return rows.map((row) => fields.map((field) => row[field] ?? "").join("｜")).join("\n");
}

const scholarTimelineTypes = [
  { value: "life", label: "生平" },
  { value: "publication", label: "著作或发表" },
  { value: "appointment", label: "任职" },
  { value: "award", label: "荣誉" },
  { value: "reception", label: "译介或传播" },
  { value: "other", label: "其他" },
];

function parseScholarTimelineEvent(value: string) {
  const matched = value.match(/^【([^】]+)】\s*([\s\S]*)$/);
  if (!matched) return { type: "life", event: value };
  const byValue = scholarTimelineTypes.find((item) => item.value === matched[1]);
  const byLabel = scholarTimelineTypes.find((item) => item.label === matched[1]);
  return { type: byValue?.value || byLabel?.value || "other", event: matched[2] };
}

function formatScholarTimelineEvent(type: string, event: string) {
  const normalizedEvent = event.trim();
  if (!normalizedEvent) return "";
  const label = scholarTimelineTypes.find((item) => item.value === type)?.label;
  return label ? `【${label}】${normalizedEvent}` : normalizedEvent;
}

function splitValues(value: string) {
  return value.split(/[\r\n,，;；]+/).map((item) => item.trim()).filter(Boolean);
}

function stringArray(value: unknown) {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function structuredLines(value: unknown, ...fields: string[]) {
  if (!Array.isArray(value)) return "";
  return value.map((item) => {
    if (typeof item === "string") return item;
    if (!item || typeof item !== "object") return "";
    const record = item as Record<string, unknown>;
    return fields.map((field) => String(
      record[field] ?? (field === "source" ? record.label ?? "" : ""),
    )).join("｜");
  }).filter(Boolean).join("\n");
}

function parseStructuredLines(value: string, fields: string[]) {
  return splitLines(value).map((line) => {
    const parts = line.split(/[|｜]/).map((part) => part.trim());
    return Object.fromEntries(fields.map((field, index) => [field, parts[index] ?? ""]));
  });
}

function relationMetadata(value: unknown, idField: string) {
  if (!Array.isArray(value)) return {};
  return Object.fromEntries(
    value.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const record = item as Record<string, unknown>;
      const id = String(record[idField] ?? "");
      if (!id) return [];
      return [[id, {
        relation: String(record.relation ?? ""),
        source: String(record.source ?? ""),
      }]];
    }),
  ) as Record<string, RelationMetadata>;
}

function mergeSuggestionLines(value: string, options: CuratedOption[]) {
  const current = splitLines(value);
  const known = new Set(
    current.map((line) => line.split(/[|｜]/)[0].trim().toLocaleLowerCase()),
  );
  const additions = options.flatMap((option) => {
    const name = (option.name || option.title || "").trim();
    if (!name || known.has(name.toLocaleLowerCase())) return [];
    known.add(name.toLocaleLowerCase());
    return [`${name}｜${option.description ?? ""}｜${option.source ?? "系统识别候选"}`];
  });
  return current.concat(additions).join("\n");
}

function CuratedSelector({
  label,
  options,
  selected,
  single = false,
  onChange,
}: {
  label: string;
  options: CuratedOption[];
  selected: string[];
  single?: boolean;
  onChange: (value: string[]) => void;
}) {
  return (
    <div className="curated-selector">
      <strong>{label}</strong>
      <div>
        {options.map((option) => {
          const active = selected.includes(option.id);
          const text = option.title || option.name || "未命名条目";
          return (
            <button
              className={active ? "active" : ""}
              type="button"
              key={option.id}
              onClick={() => onChange(
                active
                  ? selected.filter((id) => id !== option.id)
                  : single ? [option.id] : selected.concat(option.id),
              )}
            >
              {active ? <CheckCircle2 size={13} /> : <Plus size={13} />}
              <span>
                <b>{text}</b>
                {option.page_index ? (
                  <small>
                    PDF 第 {option.page_index} 页
                    {option.printed_label && option.printed_label !== String(option.page_index)
                      ? ` · 书页 ${option.printed_label}`
                      : ""}
                  </small>
                ) : null}
                {option.reason ? <small>{option.reason}</small> : null}
                {option.description ? (
                  <small className="curated-option-excerpt">
                    <span>原文内容</span>
                    {option.description}
                  </small>
                ) : null}
                <small>
                  {option.source_label || option.source || "馆藏数据"}
                  {typeof option.confidence === "number"
                    ? ` · 可信度 ${Math.round(option.confidence * 100)}%`
                    : ""}
                  {option.approved === false ? " · 待人工确认" : ""}
                </small>
              </span>
            </button>
          );
        })}
        {!options.length ? <small>保存基础资料并建立 PDF 关联后，系统会在这里给出候选。</small> : null}
      </div>
    </div>
  );
}

function RelationDetailsEditor({
  label,
  options,
  selected,
  value,
  relationPlaceholder,
  onChange,
}: {
  label: string;
  options: CuratedOption[];
  selected: string[];
  value: Record<string, RelationMetadata>;
  relationPlaceholder: string;
  onChange: (value: Record<string, RelationMetadata>) => void;
}) {
  const selectedOptions = selected.map((id) => (
    options.find((option) => option.id === id) ?? { id, name: "已保存的关联对象" }
  ));
  if (!selectedOptions.length) return null;

  return (
    <div className="relation-details-editor">
      <strong>{label}</strong>
      {selectedOptions.map((option) => {
        const metadata = value[option.id] ?? { relation: "", source: "" };
        const name = option.name || option.title || "未命名对象";
        const update = (field: keyof RelationMetadata, fieldValue: string) => onChange({
          ...value,
          [option.id]: { ...metadata, [field]: fieldValue },
        });
        return (
          <div key={option.id}>
            <span>{name}</span>
            <input
              aria-label={`${name}的关系类型`}
              value={metadata.relation}
              placeholder={relationPlaceholder}
              onChange={(event) => update("relation", event.target.value)}
            />
            <input
              aria-label={`${name}的关系依据`}
              value={metadata.source}
              placeholder="来源或管理员核对说明"
              onChange={(event) => update("source", event.target.value)}
            />
          </div>
        );
      })}
    </div>
  );
}
