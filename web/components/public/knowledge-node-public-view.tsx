import { Bookmark, Quote, Share2 } from "lucide-react";
import type { ReactNode } from "react";
import type { KnowledgeNodeDetail, NormalizedReadingPath, NormalizedTimelineEvent } from "@/lib/api/knowledge.types";
import { TheoryDetailPublicView } from "./theory-detail-public-view";
import { KnowledgeNodeActions } from "./knowledge-node-actions";
import actionStyles from "./knowledge-node-actions.module.css";

// Public routes and protected previews share one presentation. Preview actions
// are static: mounting live account controls would still read private state.
export function KnowledgeNodePublicView({
  node, timeline, allPaths, footer, section = "overview", pagination,
  initialCompare = "", preview = false,
}: {
  node: KnowledgeNodeDetail;
  timeline: NormalizedTimelineEvent[];
  allPaths: NormalizedReadingPath[];
  footer: ReactNode;
  section?: string;
  pagination?: ReactNode;
  initialCompare?: string;
  preview?: boolean;
}) {
  return <><TheoryDetailPublicView node={node} timeline={timeline} paths={allPaths}
    preview={preview} section={section} initialCompare={initialCompare} pagination={pagination}
    actions={preview ? <div className={actionStyles.actions} aria-label="预览中的读者操作">
      <button type="button" disabled><Bookmark size={15} />收藏</button>
      <button type="button" disabled><Quote size={15} />引用</button>
      <button type="button" disabled><Share2 size={15} />分享</button>
    </div> : <KnowledgeNodeActions node={node} />} />{footer}</>;
}
