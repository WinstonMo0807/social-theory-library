"use client";

import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import type { RecyclePreview } from "@/lib/api/recycle.types";
import { SiteHeader } from "@/components/site-header";
import { WorkDetailView } from "@/components/work-detail-view";
import { RecommendationIssueView } from "@/components/public/recommendation-issue-view";
import { PreviewSurface } from "./knowledge-page-preview";
import { adaptPreviewWork } from "./work-page-preview";

export function RecyclePagePreview({ entryId }: { entryId: string }) {
  const resource = useApiResource<RecyclePreview>(`/catalog/admin/recycle/${entryId}/preview/`, getServerSessionCredential());
  if (resource.error) return <main className="page-shell"><p role="alert">{resource.error}</p><button type="button" onClick={resource.retry}>重试预览</button></main>;
  if (!resource.data || resource.loading) return <main className="page-shell"><p role="status">正在读取保留的内容…</p></main>;
  const data = resource.data;
  return <div className="recycle-page-preview">
    <p className="admin-page-preview-banner" role="status">恢复效果预览 · 尚未公开。恢复后请回到编辑区检查并发布。</p>
    {data.blocked_reason ? <p className="page-shell" role="alert">{data.blocked_reason}</p> : null}
    {data.preview_kind === "work" ? <><SiteHeader preview previewPath="/"/><WorkDetailView work={adaptPreviewWork(data.preview.work)} footer={null} presentation="publication" preview={{ publicationState: "unpublished", pdfPreviewUrl: "", returnHref: "/admin/recycle" }}/></>
      : data.preview_kind === "knowledge" ? <div inert><PreviewSurface payload={data.preview} pageId="overview"/></div>
      : data.preview_kind === "issue" ? <div inert><SiteHeader preview previewPath="/recommendations"/><RecommendationIssueView issue={data.preview} preview/></div>
      : <main className="page-shell"><h1>{data.entry.name}</h1><p>{data.preview.message}</p><dl><dt>删除时间</dt><dd>{new Date(data.entry.deleted_at).toLocaleString("zh-CN")}</dd><dt>删除原因</dt><dd>{data.entry.reason || "未记录"}</dd></dl></main>}
  </div>;
}
