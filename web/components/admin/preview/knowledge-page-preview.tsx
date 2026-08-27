"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { RefreshCw, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { TheoryGraphExplorer } from "@/components/theory-graph-explorer";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import type { TheorySchool } from "@/lib/data";
import { adaptApiScholarDetail, adaptApiTopic, adaptApiWork } from "@/lib/public-data-adapters";
import type {
  ApiScholar,
  ApiTopic,
  Discipline,
  KnowledgeNodeDetail,
  LocalTheoryGraph,
  NormalizedTimelineEvent,
  NormalizedReadingPath,
  Subdiscipline,
  TheoryDisciplinePage,
} from "@/lib/server-api";

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

type KnowledgePreviewPayload = {
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

function PreviewSurface({ payload, pageId }: { payload: KnowledgePreviewPayload; pageId: string }) {
  const data = payload.perspective.data;
  if (!data || typeof data !== "object") {
    return <p className="admin-list-state is-unavailable">当前对象没有可渲染的草稿或公开内容。</p>;
  }

  const footer = null;
  switch (payload.object_type) {
    case "discipline": {
      const item = data as Discipline;
      return <DisciplinePublicView payload={disciplinePage(item)} activeType="theory_tradition" slug={item.slug} footer={footer} />;
    }
    case "subdiscipline": {
      const item = data as Subdiscipline;
      return <SubdisciplinePublicView item={{ ...item, works: (item.works ?? []).map(adaptApiWork) }} footer={footer} />;
    }
    case "scholar": {
      const item = data as ApiScholar;
      if (!item.person || typeof item.person !== "object" || !item.slug) {
        return <p className="admin-list-state is-unavailable">学者预览缺少身份或公开路径，已停止渲染并保留草稿。</p>;
      }
      const adapted = adaptApiScholarDetail(item);
      const theorySchools = payload.secondary_preview?.legacy_theory_schools ?? [];
      return pageId && pageId !== "overview"
        ? <ScholarSectionPublicView data={adapted} schools={theorySchools} section={pageId} slug={item.slug} />
        : <ScholarPublicView data={adapted} footer={footer} slug={item.slug} theorySchools={theorySchools} />;
    }
    case "topic": {
      const raw = data as ApiTopic;
      if (!raw.id || !raw.slug || !raw.name) {
        return <p className="admin-list-state is-unavailable">主题预览缺少规范身份，已停止渲染并保留草稿。</p>;
      }
      const item = adaptApiTopic(raw);
      return pageId && pageId !== "overview"
        ? <TopicSectionPublicView topic={item} section={pageId} />
        : <TopicPublicView topic={item} footer={footer} />;
    }
    case "reading_path":
      return <ReadingPathPublicView path={data as NormalizedReadingPath} footer={footer} />;
    case "theory":
    case "concept":
    case "debate":
    case "research_problem": {
      const raw = data as KnowledgeNodeDetail;
      if (!raw.id || !raw.slug || !raw.canonical_name_zh) {
        return <p className="admin-list-state is-unavailable">理论预览缺少规范身份，已停止渲染并保留草稿。</p>;
      }
      const node = {
        ...raw,
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
        return <main className="page-shell theory-system-page theory-graph-page"><section className="theory-graph-heading"><div><p className="eyebrow">局部关系浏览</p><h1>{node.canonical_name_zh}的理论图谱</h1><p>使用当前草稿身份和已经发布的规范关系生成。</p></div></section><TheoryGraphExplorer graph={payload.secondary_preview?.graph ?? { center: null, nodes: [], edges: [], depth: 1, limit: 20, truncated: false }} /></main>;
      }
      if (payload.object_type === "theory" && pageId === "timeline") {
        return <main className="page-shell theory-system-page theory-timeline-page"><section className="theory-timeline-hero"><div><p className="eyebrow">历史时间轴</p><h1>{node.canonical_name_zh}的发展脉络</h1><p>这里只显示已经审核并关联到该理论的真实时间轴事件。</p></div></section><div className="theory-timeline-layout"><TheoryTimelinePublicList events={payload.secondary_preview?.timeline ?? []} /></div></main>;
      }
      if (payload.object_type === "theory" && pageId === "reading-path") {
        const path = payload.secondary_preview?.reading_paths?.[0];
        return path
          ? <ReadingPathPublicView path={path} footer={footer} />
          : <main className="page-shell secondary-detail-page"><header><p className="eyebrow">Reading Path</p><h1>{node.canonical_name_zh}的阅读路径</h1></header><p className="empty-state" data-module-id="theory-reading-paths">当前没有包含该理论的已发布阅读路径。</p></main>;
      }
      if (payload.object_type === "theory" && pageId !== "overview") {
        return <main className="page-shell secondary-detail-page"><header><p className="eyebrow">公开关系入口</p><h1>{node.canonical_name_zh}</h1></header><p className="empty-state">该位置由学科、学者或主题页面消费。请从对应对象的受保护预览核对具体页面。</p></main>;
      }
      return <KnowledgeNodePublicView
        node={node}
        timeline={payload.secondary_preview?.timeline ?? []}
        allPaths={payload.secondary_preview?.reading_paths ?? []}
        slug={node.slug}
        footer={footer}
        publicationStatusLabel={payload.active_perspective === "draft" ? "草稿预览" : "已审核并公开"}
      />;
    }
    default:
      return <p className="admin-list-state is-unavailable">该对象请使用它在 Knowledge Studio 中提供的专用预览。</p>;
  }
}

export function AdminKnowledgePagePreview({ objectType, objectId }: { objectType: string; objectId: string }) {
  const searchParams = useSearchParams();
  const pageId = searchParams.get("page") || "overview";
  const moduleId = searchParams.get("module") || "";
  const [payload, setPayload] = useState<KnowledgePreviewPayload | null>(null);
  const [message, setMessage] = useState("");
  const [anchorMessage, setAnchorMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const requestRevision = useRef(0);

  const load = useCallback(async () => {
    const revision = ++requestRevision.current;
    setLoading(true);
    setMessage("");
    try {
      const result = await apiRequest<KnowledgePreviewPayload>(
        `/catalog/admin/knowledge-preview/${encodeURIComponent(objectType)}/${encodeURIComponent(objectId)}/`,
        {},
        getServerSessionCredential(),
      );
      if (requestRevision.current === revision) setPayload(result);
    } catch (reason) {
      if (requestRevision.current === revision) {
        setMessage(reason instanceof Error ? reason.message : "知识对象预览加载失败。");
      }
    } finally {
      if (requestRevision.current === revision) setLoading(false);
    }
  }, [objectId, objectType]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => {
      window.clearTimeout(timer);
      requestRevision.current += 1;
    };
  }, [load]);

  useEffect(() => {
    if (!payload) return;
    const timer = window.setTimeout(() => {
      setAnchorMessage("");
      if (!moduleId) return;
      const target = document.querySelector<HTMLElement>(
        `[data-module-id="${CSS.escape(moduleId)}"]`,
      );
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        target.setAttribute("data-preview-target", "true");
      } else {
        setAnchorMessage("该模块在当前草稿中没有可渲染内容。页面契约仍保留编辑入口，发布前不会伪造占位数据。");
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

  if (!payload) {
    return (
      <div className="admin-page admin-page-preview-state">
        <AsyncStatus
          state={loading ? "pending" : "error"}
          message={loading ? "正在生成知识对象草稿预览……" : message || "预览不可用。"}
          assertive={!loading}
        />
        {!loading ? <ActionButton className="button secondary" onClick={() => void load()}><RefreshCw size={15} />重试</ActionButton> : null}
      </div>
    );
  }

  return (
    <div className="admin-knowledge-page-preview">
      <div className="page-shell">
        <div className="admin-page-preview-banner" role="status">
          <ShieldCheck size={16} />
          <strong>受保护的知识页面预览</strong>
          <span>
            {payload.active_perspective === "draft"
              ? `正在使用${payload.source === "canonical_draft" ? "未发布正式草稿" : "已保存 EditorialRevision"}渲染“${payload.label}”。普通访客仍看到已发布内容。`
              : `当前没有待发布草稿，正在显示“${payload.label}”的公开版本。`}
            {unsupported.length ? ` ${unsupported.length} 个字段暂不能完整物化，已在下方标明预览边界。` : ""}
          </span>
        </div>
        <nav className="admin-preview-actions" aria-label="预览操作">
          <Link className="button secondary" href="/admin/knowledge">返回 Knowledge Studio</Link>
          {payload.preview_routes.published ? <Link className="button secondary" href={payload.preview_routes.published} target="_blank">查看当前公开版</Link> : null}
        </nav>
        {payload.public_control?.page_tree?.length ? <nav className="admin-preview-page-switcher" aria-label="公开页面预览">
          {payload.public_control.page_tree.filter((page) => page.preview?.supported !== false).map((page) => <Link
            className={page.page_id === pageId ? "is-active" : ""}
            href={`?page=${encodeURIComponent(page.page_id)}`}
            key={page.page_id}
          >{page.display_name}</Link>)}
        </nav> : null}
        {unsupported.length ? <p className="admin-preview-warning">暂未物化字段：{unsupported.join("、")}。发布前请回到 Knowledge Studio 核对。</p> : null}
        {anchorMessage ? <p className="admin-preview-warning">{anchorMessage}</p> : null}
      </div>
      <div className="admin-knowledge-page-preview-body" inert>
        <PreviewSurface payload={payload} pageId={pageId} />
      </div>
      <div className="page-shell"><p className="admin-preview-note">预览复用公开页面组件。为避免误操作，预览内的保存、询问、Reader 和跨页链接均已停用。</p></div>
    </div>
  );
}
