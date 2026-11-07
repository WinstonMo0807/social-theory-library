"use client";

import { LoadingState } from "@/components/ui/loading-state";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { getServerSessionCredential } from "@/lib/api";
import type { CatalogingSession } from "@/lib/api/cataloging";
import { useApiResource } from "@/lib/api/use-api-resource";
import { WorkflowEditor } from "./workflow-editor";
import { safeAdminHref, withAdminReturn } from "@/lib/admin-route-context";
export { ManualCatalogForm } from "./manual-catalog";

export function CatalogingWorkbench({ sessionId, initialAssistant=false }: { sessionId: string; initialAssistant?:boolean }) {
  const params = useSearchParams();
  const returnHref = safeAdminHref(params.get("return_to"));
  const { data, error, loading, retry } = useApiResource<{ session: CatalogingSession }>(
    `/catalog/admin/cataloging-sessions/${encodeURIComponent(sessionId)}/?workspace=0`, getServerSessionCredential(),
  );
  if (error) return <section className="admin-panel" role="alert"><p>{error}</p><button type="button" onClick={retry}>重新读取</button><Link href={returnHref}>返回原页面</Link></section>;
  if (loading || !data) return <LoadingState className="admin-list-state" role="status">正在读取编目会话…</LoadingState>;
  const session = data.session;
  if (["published", "abandoned"].includes(session.status)) return <section className="admin-panel"><p>本次编目已结束，草稿、馆藏和原始文件均保留。</p>{session.work_id && session.edition_id ? <Link href={withAdminReturn(`/admin/library/works/${session.work_id}?edition=${session.edition_id}`, returnHref, "publication")}>核对当前出版版本及公开结果</Link> : null}<Link href={returnHref}>返回原页面</Link></section>;
  if (!session.work_id || !session.edition_id) return <section className="admin-panel"><p role="status">上传尚未建立作品版本，文件处理完成后可继续编目。</p><button type="button" onClick={retry}>刷新处理结果</button><Link href={withAdminReturn(session.upload_item_id ? `/admin/uploads?item=${encodeURIComponent(session.upload_item_id)}` : "/admin/uploads", returnHref)}>查看原上传来源</Link></section>;
  return <WorkflowEditor key={session.id} mode="maintenance" workId={session.work_id} editionId={session.edition_id} initialAssistant={initialAssistant}/>;
}
