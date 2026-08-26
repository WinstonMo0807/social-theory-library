"use client";

import Link from "next/link";
import { RefreshCw, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActionButton, AsyncStatus } from "@/components/action-feedback";
import { DisciplinePublicView } from "@/components/public/discipline-public-view";
import { KnowledgeNodePublicView } from "@/components/public/knowledge-node-public-view";
import { ReadingPathPublicView } from "@/components/public/reading-path-public-view";
import { ScholarPublicView } from "@/components/public/scholar-public-view";
import { SubdisciplinePublicView } from "@/components/public/subdiscipline-public-view";
import { TopicPublicView } from "@/components/public/topic-public-view";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { adaptApiScholarDetail, adaptApiTopic, adaptApiWork } from "@/lib/public-data-adapters";
import type {
  ApiScholar,
  ApiTopic,
  Discipline,
  KnowledgeNodeDetail,
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

function PreviewSurface({ payload }: { payload: KnowledgePreviewPayload }) {
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
      return <ScholarPublicView data={adaptApiScholarDetail(item)} footer={footer} slug={item.slug} theorySchools={[]} />;
    }
    case "topic": {
      const item = adaptApiTopic(data as ApiTopic);
      return <TopicPublicView topic={item} footer={footer} />;
    }
    case "reading_path":
      return <ReadingPathPublicView path={data as NormalizedReadingPath} footer={footer} />;
    case "theory":
    case "concept":
    case "debate":
    case "research_problem": {
      const node = data as KnowledgeNodeDetail;
      return <KnowledgeNodePublicView node={node} timeline={[]} allPaths={[]} slug={node.slug} footer={footer} />;
    }
    default:
      return <p className="admin-list-state is-unavailable">该对象请使用它在 Knowledge Studio 中提供的专用预览。</p>;
  }
}

export function AdminKnowledgePagePreview({ objectType, objectId }: { objectType: string; objectId: string }) {
  const [payload, setPayload] = useState<KnowledgePreviewPayload | null>(null);
  const [message, setMessage] = useState("");
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
        {unsupported.length ? <p className="admin-preview-warning">暂未物化字段：{unsupported.join("、")}。发布前请回到 Knowledge Studio 核对。</p> : null}
      </div>
      <div className="admin-knowledge-page-preview-body" inert>
        <PreviewSurface payload={payload} />
      </div>
      <div className="page-shell"><p className="admin-preview-note">预览复用公开页面组件。为避免误操作，预览内的保存、询问、Reader 和跨页链接均已停用。</p></div>
    </div>
  );
}
