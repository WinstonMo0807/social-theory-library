"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { PageHeader } from "@/components/admin-ui";
import { getServerSessionCredential } from "@/lib/api";
import { createRequestKey } from "@/lib/request-key";
import { createManualCatalog, type CatalogingSession, type ManualCatalogInput } from "@/lib/api/cataloging";
import { useApiResource } from "@/lib/api/use-api-resource";
import { WorkflowEditor } from "./workflow-editor";
import { safeAdminHref, withAdminReturn } from "@/lib/admin-route-context";

export function ManualCatalogForm() {
  const router = useRouter();
  const params = useSearchParams();
  const returnHref = safeAdminHref(params.get("return_to"));
  const requestKey = useRef("");
  const submitting = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    const form = new FormData(event.currentTarget);
    submitting.current = true;
    requestKey.current ||= createRequestKey();
    setBusy(true);
    setError("");
    try {
      const session = await createManualCatalog({
        title: String(form.get("title") ?? ""),
        document_type: String(form.get("document_type") ?? "book") as ManualCatalogInput["document_type"],
        language: String(form.get("language") ?? "zh-CN"), request_key: requestKey.current,
      });
      const destination = `/admin/cataloging/${encodeURIComponent(session.id)}`;
      router.push(params.has("return_to") ? withAdminReturn(destination, returnHref, "work") : `${destination}#work`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "未能创建书目，已填写内容仍保留。");
      submitting.current = false;
      setBusy(false);
    }
  }
  return <div className="admin-page">
    <PageHeader title="新建书目" description="可以先整理作品和出版信息，稍后再添加文件。" actions={<Link href={returnHref}>返回原页面</Link>} />
    <form className="admin-panel workflow-field-grid" onSubmit={submit} aria-busy={busy}>
      <label>作品题名<input name="title" maxLength={600} autoComplete="off" placeholder="可稍后补充" disabled={busy} /></label>
      <label>文献类型<select name="document_type" defaultValue="book" disabled={busy}><option value="book">图书</option><option value="journal_article">期刊论文</option><option value="journal_issue">整期期刊</option><option value="thesis">学位论文</option><option value="report">研究报告</option></select></label>
      <label>正文语言<select name="language" defaultValue="zh-CN" disabled={busy}><option value="zh-CN">简体中文</option><option value="zh-TW">繁体中文</option><option value="en">英文</option><option value="mixed">多语种</option></select></label>
      {error ? <p role="alert">{error}</p> : null}
      <div><button type="submit" className="button" disabled={busy}>{busy ? "正在创建…" : "创建草稿并开始编目"}</button></div>
    </form>
  </div>;
}

export function CatalogingWorkbench({ sessionId }: { sessionId: string }) {
  const params = useSearchParams();
  const returnHref = safeAdminHref(params.get("return_to"));
  const { data, error, loading, retry } = useApiResource<{ session: CatalogingSession }>(
    `/catalog/admin/cataloging-sessions/${encodeURIComponent(sessionId)}/?workspace=0`, getServerSessionCredential(),
  );
  if (error) return <section className="admin-panel" role="alert"><p>{error}</p><button type="button" onClick={retry}>重新读取</button><Link href={returnHref}>返回原页面</Link></section>;
  if (loading || !data) return <p className="admin-list-state" role="status">正在读取编目会话…</p>;
  const session = data.session;
  if (["published", "abandoned"].includes(session.status)) return <section className="admin-panel"><p>本次编目已结束，草稿、馆藏和原始文件均保留。</p>{session.work_id && session.edition_id ? <Link href={withAdminReturn(`/admin/library/works/${session.work_id}?edition=${session.edition_id}`, returnHref, "publication")}>核对当前出版版本及公开结果</Link> : null}<Link href={returnHref}>返回原页面</Link></section>;
  if (!session.work_id || !session.edition_id) return <section className="admin-panel"><p role="status">上传尚未建立作品版本，文件处理完成后可继续编目。</p><button type="button" onClick={retry}>刷新处理结果</button><Link href={withAdminReturn(session.upload_item_id ? `/admin/uploads?item=${encodeURIComponent(session.upload_item_id)}` : "/admin/uploads", returnHref)}>查看原上传来源</Link></section>;
  return <WorkflowEditor key={session.id} mode="maintenance" workId={session.work_id} editionId={session.edition_id} />;
}
