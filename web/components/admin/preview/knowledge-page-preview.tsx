"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { RefreshCw, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ActionButton, AsyncStatus } from "@/components/action-feedback";
import { DisciplinePublicView } from "@/components/public/discipline-public-view";
import { KnowledgeNodePublicView } from "@/components/public/knowledge-node-public-view";
import { ReadingPathPublicView } from "@/components/public/reading-path-public-view";
import { ScholarPublicView } from "@/components/public/scholar-public-view";
import { ScholarSectionPublicView } from "@/components/public/scholar-section-public-view";
import { SubdisciplinePublicView } from "@/components/public/subdiscipline-public-view";
import { TopicPublicView } from "@/components/public/topic-public-view";
import { TopicSectionPublicView } from "@/components/public/topic-section-public-view";
import { TheoryTimelinePublicList } from "@/components/public/theory-timeline-public-view";
import { KnowledgeMapHero } from "@/components/public/knowledge-map-hero";
import { TimelineHero } from "@/components/public/theory-timeline-workspace";
import surfaceStyles from "@/components/public/secondary-public-view.module.css";
import { TheoryGraphExplorer } from "@/components/theory-graph-explorer";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useAdminSession } from "@/lib/admin-session";
import type { TheorySchool } from "@/lib/data";
import { adaptApiWork } from "@/lib/public-data-adapters";
import type { PublicScholarDetail } from "@/lib/api/scholars.types";
import type { PublicTopicDetail } from "@/lib/api/topics.types";
import { adminListHref, safeAdminHref } from "@/lib/admin-route-context";
import type { Discipline, Subdiscipline } from "@/lib/api/taxonomy.types";
import type { KnowledgeNodeDetail, LocalTheoryGraph, NormalizedTimelineEvent, NormalizedReadingPath, TheoryDisciplinePage } from "@/lib/api/knowledge.types";

type PreviewPerspective = {
  source: string;
  available: boolean;
  complete?: boolean;
  serializer: string;
  revision_id?: string | null;
  data: unknown;
  unsupported_preview_fields?: string[];
  reason?: string;
};

export type KnowledgePreviewPayload = {
  publication_review?: {
    checked_at:string;saved_at:string;current_revision:number;draft_revision_id:string|null;
    has_draft:boolean;withdrawing:boolean;actor_label:string;blocking_count:number;warning_count:number;can_publish:boolean;
    checks:Array<{code:string;severity:"blocking"|"warning"|"notice";title:string;detail:string;section:string}>;
    changes:Array<{key:string;label:string;before:Record<string,unknown>;after:Record<string,unknown>;changed:boolean}>;
  };
  edit_version?: string;
  preview_mode: true;
  protected: true;
  object_type: string;
  object_id: string;
  label: string;
  status: string;
  active_perspective: "draft" | "published";
  source: string;
  perspective: PreviewPerspective;
  perspectives: Record<"draft" | "published", PreviewPerspective>;
  preview_routes: { draft?: string; published?: string };
  content_completeness?: {
    perspective_source?: string;
    unsupported_preview_fields?: string[];
  };
  public_control?: {
    page_tree?: Array<{
      page_id: string;
      display_name: string;
      modules: Array<{ module_id: string; display_name: string }>;
      preview?: { supported?: boolean };
    }>;
  };
  secondary_preview?: {
    graph?: LocalTheoryGraph;
    timeline?: NormalizedTimelineEvent[];
    reading_paths?: NormalizedReadingPath[];
    legacy_theory_schools?: TheorySchool[];
  };
};

function disciplinePage(data: Discipline): TheoryDisciplinePage {
  return {
    discipline: {
      id: data.id,
      code: data.code,
      name: data.name,
      foreign_name: data.foreign_name,
      slug: data.slug,
      description: data.description || data.introduction,
      hero_image: data.hero_image,
    },
    counts: {
      theory_traditions: data.theory_count,
      subdisciplines: data.subdiscipline_count,
      scholars: data.scholar_count,
      works: data.work_count,
    },
    active_type: "theory_tradition",
    nodes: [],
    lineage: [],
    reading_paths: [],
  };
}

function previewProblem(payload:KnowledgePreviewPayload):string {
  const data=payload.perspective.data as Record<string,unknown>|null;
  if(!data||typeof data!=="object"||Array.isArray(data))return "当前对象没有可渲染的草稿或公开内容。";
  if(payload.object_type==="scholar"&&(!data.person||typeof data.person!=="object"))return "未取得学者记录，草稿已保留。";
  if(payload.object_type==="topic"&&(!data.id||!data.slug||!data.name))return "缺少主题编号，无法预览。草稿已保留。";
  if(["theory","concept","debate","research_problem"].includes(payload.object_type)&&(!data.id||!data.slug||!data.canonical_name_zh))return "缺少理论编号，无法预览。草稿已保留。";
  if(!["discipline","subdiscipline","scholar","topic","reading_path","theory","concept","debate","research_problem"].includes(payload.object_type))return "该对象请使用专用预览。";
  return "";
}

export function PreviewSurface({ payload, pageId, moduleId = "", previewStageId = "", footer = null, subdisciplineDraftFields = true }: { payload: KnowledgePreviewPayload; pageId: string; moduleId?: string; previewStageId?: string; footer?:ReactNode; subdisciplineDraftFields?:boolean }) {
  const data = payload.perspective.data,problem=previewProblem(payload);
  if(problem)return <p className="admin-list-state is-unavailable">{problem}</p>;

  switch (payload.object_type) {
    case "discipline": {
      const item = data as Discipline & {page_projection?:TheoryDisciplinePage};
      return <DisciplinePublicView payload={item.page_projection || disciplinePage(item)} activeType="theory_tradition" slug={item.slug} footer={footer} />;
    }
    case "subdiscipline": {
      const item = data as Subdiscipline;
      return <SubdisciplinePublicView preview={subdisciplineDraftFields} item={{ ...item, works: (item.works ?? []).map(adaptApiWork) }} footer={footer} />;
    }
    case "scholar": {
      const item = data as PublicScholarDetail;
      return pageId && pageId !== "overview"
        ? <ScholarSectionPublicView preview data={item} section={pageId} footer={footer} />
        : <ScholarPublicView preview data={item} footer={footer} />;
    }
    case "topic": {
      const item = data as PublicTopicDetail;
      return pageId && pageId !== "overview"
        ? <TopicSectionPublicView preview topic={item} section={pageId} />
        : <TopicPublicView preview topic={item} footer={footer} />;
    }
    case "reading_path":
      return <ReadingPathPublicView preview initialTab={moduleId.replace(/^reading-path-/, "") || pageId} previewStageId={previewStageId} path={data as NormalizedReadingPath} footer={footer} />;
    case "theory":
    case "concept":
    case "debate":
    case "research_problem": {
      const raw = data as KnowledgeNodeDetail;
      const node = {
        ...raw,
        aliases: raw.aliases ?? [],
        core_questions: raw.core_questions ?? [],
        basic_propositions: raw.basic_propositions ?? [],
        representative_scholars: raw.representative_scholars ?? [],
        related_disciplines: raw.related_disciplines ?? [],
        subdiscipline_links: raw.subdiscipline_links ?? [],
        topic_links: raw.topic_links ?? [],
        direct_relations: raw.direct_relations ?? [],
        work_groups: raw.work_groups ?? {},
        evidence: raw.evidence ?? [],
        curated_claims: raw.curated_claims ?? {
          core_viewpoint: [],
          major_criticism: [],
          major_response: [],
          debate_position: [],
        },
      } as KnowledgeNodeDetail;
      if (payload.object_type === "theory" && pageId === "graph") {
        return <main className={surfaceStyles.page}><KnowledgeMapHero title={`${node.canonical_name_zh}的理论图谱`} description="预览使用当前草稿和已发布的关系。" /><div className={surfaceStyles.content}>{payload.secondary_preview?.graph?.nodes.length ? <TheoryGraphExplorer graph={payload.secondary_preview.graph} /> : <p className="empty-state">当前没有可预览的理论关系。</p>}</div></main>;
      }
      if (payload.object_type === "theory" && pageId === "timeline") {
        return <main className={surfaceStyles.page}><TimelineHero scope={{ name: node.canonical_name_zh, href: `/theories/nodes/${node.slug}` }} /><div className={surfaceStyles.content}><TheoryTimelinePublicList events={payload.secondary_preview?.timeline ?? []} /></div></main>;
      }
      if (payload.object_type === "theory" && pageId === "reading-path") {
        const path = payload.secondary_preview?.reading_paths?.[0];
        return path
          ? <ReadingPathPublicView preview path={path} footer={footer} />
          : <main className={`${surfaceStyles.page} ${surfaceStyles.content}`}><header><h1>{node.canonical_name_zh}的阅读路径</h1></header><p className="empty-state" data-module-id="theory-reading-paths">当前没有包含该理论的已发布阅读路径。</p></main>;
      }
      if (payload.object_type === "theory" && pageId !== "overview" && !["concepts", "works", "evidence", "relations", "propositions", "scholars", "paths", "usages", "debates", "contexts", "research"].includes(pageId)) {
        return <main className={`${surfaceStyles.page} ${surfaceStyles.content}`}><header><h1>{node.canonical_name_zh}</h1></header><p className="empty-state">该位置由学科、学者或主题页面消费。请从对应对象的受保护预览核对具体页面。</p></main>;
      }
      return <KnowledgeNodePublicView
        node={node}
        timeline={payload.secondary_preview?.timeline ?? []}
        allPaths={payload.secondary_preview?.reading_paths ?? []}
        footer={footer}
        preview
        section={pageId}
      />;
    }
    default:
      return <p className="admin-list-state is-unavailable">该对象请使用它在 Knowledge Studio 中提供的专用预览。</p>;
  }
}

export function AdminKnowledgePagePreview(props: { objectType: string; objectId: string }) {
  const owner=useAdminSession()?.id,params=useSearchParams();
  return <KnowledgePagePreview key={`${owner}:${props.objectType}:${props.objectId}:${params.get("edit_version")||""}`} {...props}/>;
}

function KnowledgePagePreview({ objectType, objectId }: { objectType: string; objectId: string }) {
  const searchParams = useSearchParams();
  const user=useAdminSession(),owner=user?String(user.id):"",expectedVersion=searchParams.get("edit_version")||"";
  const pageId = searchParams.get("page") || "overview";
  const frame = searchParams.get("frame") === "1";
  const moduleId = searchParams.get("module") || "";
  const returnHref = safeAdminHref(searchParams.get("return_to"), `/admin/knowledge?selected_type=${encodeURIComponent(objectType)}&selected_id=${encodeURIComponent(objectId)}`);
  const [payload, setPayload] = useState<KnowledgePreviewPayload | null>(null);
  const [message, setMessage] = useState("");
  const [anchorMessage, setAnchorMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const requestRevision = useRef(0);
  const lifetime=useRef<AbortController|null>(null);

  const load = useCallback(async () => {
    const revision = ++requestRevision.current;
    setLoading(true);
    setPayload(null);
    setMessage("");
    try {
      const signal=AbortSignal.any([lifetime.current!.signal,AbortSignal.timeout(30000)]);
      const query=expectedVersion?`?${new URLSearchParams({edit_version:expectedVersion})}`:"";
      const result = await withPrivateOwner(owner,()=>apiRequest<KnowledgePreviewPayload>(
        `/catalog/admin/knowledge-preview/${encodeURIComponent(objectType)}/${encodeURIComponent(objectId)}/${query}`,
        {signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},
        getServerSessionCredential(),
      ),signal);
      if(result.object_id!==objectId||result.object_type!==objectType||!result.edit_version||!/^[a-f0-9]{64}$/.test(result.edit_version)||expectedVersion&&result.edit_version!==expectedVersion)throw Error("预览与当前对象或保存版本不一致，请返回编辑页重新检查。");
      const problem=previewProblem(result);
      if(!result.perspective.available || problem)throw Error(problem||"已保存内容尚不能生成有效预览。");
      if (requestRevision.current === revision) setPayload(result);
    } catch (reason) {
      if (requestRevision.current === revision) {
        setMessage(reason instanceof Error ? reason.message : "知识对象预览加载失败。");
      }
    } finally {
      if (requestRevision.current === revision) setLoading(false);
    }
  }, [objectId, objectType,owner,expectedVersion]);

  useEffect(() => {
    if(!owner)return;
    const controller=new AbortController();lifetime.current=controller;
    const unsubscribe=subscribeToSessionChanges(()=>{controller.abort();requestRevision.current+=1;setPayload(null);setMessage("账户已变化，请重新打开当前对象的预览。");setLoading(false);});
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => {
      controller.abort();unsubscribe();
      window.clearTimeout(timer);
      requestRevision.current += 1;
    };
  }, [load,owner]);

  useEffect(() => {
    if (!payload) return;
    const timer = window.setTimeout(() => {
      setAnchorMessage("");
      if (!moduleId) return;
      const target = document.querySelector<HTMLElement>(
        `[data-module-id="${CSS.escape(moduleId)}"]`,
      );
      if (target) {
        target.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "center" });
        target.setAttribute("data-preview-target", "true");
      } else {
        setAnchorMessage("此栏目尚无内容。请返回编辑页补充。");
      }
    }, 80);
    return () => window.clearTimeout(timer);
  }, [moduleId, pageId, payload]);

  const unsupported = useMemo(
    () => payload?.perspective.unsupported_preview_fields
      ?? payload?.content_completeness?.unsupported_preview_fields
      ?? [],
    [payload],
  );

  useEffect(()=>{
    if(!frame || window.parent===window || !expectedVersion)return;
    // A committed render is required; an API response alone is not readiness.
    const timer=window.requestAnimationFrame(()=>window.parent.postMessage({type:"stl:knowledge-publication-preview",objectType,objectId,version:expectedVersion,owner,pageId,ok:Boolean(payload&&!loading&&!message),state:loading?"loading":payload&&!message?"ready":"error"},window.location.origin));
    return()=>window.cancelAnimationFrame(timer);
  },[frame,expectedVersion,objectType,objectId,owner,pageId,payload,loading,message]);

  if (!payload) {
    return (
      <div className="admin-page admin-page-preview-state">
        <AsyncStatus
          state={loading ? "pending" : "error"}
          message={loading ? "正在生成知识对象草稿预览……" : message || "预览不可用。"}
          assertive={!loading}
        />
        {!loading ? <ActionButton className="button secondary" onClick={() => void load()}><RefreshCw size={15} />重试</ActionButton> : null}
        {!loading ? <Link className="button secondary" href={returnHref}>返回当前对象编辑</Link> : null}
      </div>
    );
  }

  if(frame)return <div className="admin-knowledge-page-preview-body" data-ui-scope="stl4" data-type-mode="expressive" inert><PreviewSurface payload={payload} pageId={pageId} moduleId={moduleId}/></div>;

  return (
    <div className="admin-knowledge-page-preview">
      <div className="page-shell">
        <div className="admin-page-preview-banner" role="status">
          <ShieldCheck size={16} />
          <strong>页面预览 · 仅管理员可见</strong>
          <span>
            {payload.active_perspective === "draft"
              ? `正在预览“${payload.label}”已保存但尚未发布的修改。读者仍看到原内容。`
              : `当前没有待发布草稿，正在显示“${payload.label}”的公开版本。`}
            {unsupported.length ? ` ${unsupported.length} 项内容暂不能完整预览，请查看下方说明。` : ""}
          </span>
        </div>
        <nav className="admin-preview-actions" aria-label="预览操作">
          <Link className="button secondary" href={returnHref}>返回当前对象编辑</Link>
          <ActionButton className="button secondary" onClick={()=>void load()}><RefreshCw size={15}/>重新读取保存版本</ActionButton>
          {payload.preview_routes.published ? <Link className="button secondary" href={payload.preview_routes.published} target="_blank">查看当前公开版</Link> : null}
        </nav>
        {payload.public_control?.page_tree?.length ? <nav className="admin-preview-page-switcher" aria-label="公开页面预览">
          {payload.public_control.page_tree.filter((page) => page.preview?.supported !== false).map((page) => <Link
            className={page.page_id === pageId ? "is-active" : ""}
            href={adminListHref(`/admin/preview/knowledge/${encodeURIComponent(objectType)}/${encodeURIComponent(objectId)}`, searchParams.toString(), { page: page.page_id, module: null })}
            key={page.page_id}
          >{page.display_name}</Link>)}
        </nav> : null}
        {unsupported.length ? <details data-disclosure="collection" className="admin-preview-warning"><summary>有内容暂不能完整预览</summary><p>{unsupported.join("、")}。请返回编辑页核对这些内容后再发布。</p></details> : null}
        {anchorMessage ? <p className="admin-preview-warning">{anchorMessage}</p> : null}
      </div>
      <div className="admin-knowledge-page-preview-body" data-ui-scope="stl4" data-type-mode="expressive" inert>
        <PreviewSurface payload={payload} pageId={pageId} moduleId={moduleId} />
      </div>
      <div className="page-shell"><p className="admin-preview-note">预览复用公开页面组件。为避免误操作，预览内的保存、询问、Reader 和跨页链接均已停用。</p></div>
    </div>
  );
}
