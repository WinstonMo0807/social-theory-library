"use client";
import { useEffect, useRef, useState } from "react";
import { Maximize2, Monitor, Smartphone } from "lucide-react";
import { apiBlob, apiRequest } from "@/lib/api";
import { WorkDetailView } from "@/components/work-detail-view";
import type { WorkDetailPresentation } from "@/components/work-detail-tabs";
import type { Work } from "@/lib/data";
import type { WorkflowStepKey } from "./workflow-state";
import { asArray, asRecord, asString, type WorkflowDrafts, type WorkflowContext } from "./workflow-types";
import { WorkflowInspector } from "@/components/admin/inspector/workflow-inspector";
import { PreviewViewport } from "@/components/admin/curation/fixed-page-editor";
import { SiteHeader } from "@/components/site-header";

export function WorkflowLivePreview({ drafts, context, token, savedAt, dirty, returnHref, onLocate, reader = false, coverOverride = null, presentation = "bibliography" }: {
  drafts: WorkflowDrafts; context: WorkflowContext; token: string | null; savedAt: string; dirty: boolean;
  returnHref: string; onLocate: (step: WorkflowStepKey) => void; reader?: boolean; coverOverride?: string | null;
  presentation?: WorkDetailPresentation;
}) {
  const [cover, setCover] = useState("");
  const [coverError, setCoverError] = useState("");
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [expanded, setExpanded] = useState(false);
  const fullPreview = useRef<HTMLDialogElement>(null);
  const editionId = asString(context.edition_id);
  useEffect(() => {
    if (!editionId) return;
    let active = true, objectUrl = "";
    const controller = new AbortController();
    const reset = window.setTimeout(() => { setCover(""); setCoverError(""); }, 0);
    void apiRequest<{ image_url: string }>(`/catalog/admin/editions/${editionId}/cover/`, { signal: controller.signal }, token)
      .then(async result => { if (!result.image_url) return; const blob = await apiBlob(result.image_url, token); objectUrl = URL.createObjectURL(blob); if (active) setCover(objectUrl); else URL.revokeObjectURL(objectUrl); })
      .catch(() => { if (active) setCoverError("封面暂时无法读取，请刷新重试。"); });
    return () => { active = false; window.clearTimeout(reset); controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [editionId, token, savedAt]);
  const authorRows = asArray(drafts.contributors.items).map(asRecord).filter(row => row.role === "author");
  const title = asString(drafts.work.title, "未填写题名");
  const assets = asArray(drafts.file.assets).map(asRecord);
  const currentAsset = assets.find(asset => asset.is_current && asset.kind === "normalized") ?? assets.find(asset => asset.is_current);
  const documentType = asString(drafts.work.document_type, "book");
  const pdfUrl = asString(context.pdf_preview_url) || asString(context.preview_url) || asString(drafts.file.preview_url) || asString(currentAsset?.preview_url);
  const work: Work = {
    id: asString(currentAsset?.id), workId: asString(context.work_id), editionId, slug: asString(context.work_id), title,
    originalTitle: asString(drafts.work.original_title), author: authorRows.map(row => asString(row.display_name || row.name)).filter(Boolean).join("、") || "作者待确认",
    subtitle: asString(drafts.work.subtitle), publisher: asString(drafts.bibliography.publisher), versionLabel: asString(drafts.bibliography.version_label),
    isbn: asString(drafts.bibliography.isbn13 || drafts.bibliography.isbn10 || drafts.bibliography.isbn), originalLanguage: asString(drafts.work.original_language),
    translators: asArray(drafts.contributors.items).map(asRecord).filter(row=>row.role==="translator").map(row=>({name:asString(row.display_name || row.name)})),
    year: asString(drafts.bibliography.publication_year) || String(drafts.bibliography.publication_year || "年份待补"),
    kind: ({ book:"图书", journal_article:"期刊论文", journal_issue:"整期期刊", thesis:"学位论文", report:"研究报告" } as Record<string, Work["kind"]>)[documentType] || "图书",
    school: asArray(drafts.classification.primary_disciplines).map(asRecord).map(row => asString(row.name)).join("、"),
    categories: asArray(drafts.classification.primary_disciplines).map(asRecord).map(row => asString(row.name)).filter(Boolean),
    summary: asString(drafts.work.abstract), cover:"paper", coverImage:(coverOverride ?? cover) || undefined, coverAlt:title,
    pages: Number(currentAsset?.page_count || drafts.reader.page_count || 0), language:asString(drafts.work.language),
    authors:authorRows.map(row => ({name:asString(row.display_name || row.name)})),
    theories:asArray(drafts.knowledge.nodes).map(asRecord).map(row => ({name:asString(row.name),slug:asString(row.id)})),
    topics:asArray(drafts.knowledge.topics).map(asRecord).map(row => ({name:asString(row.name),slug:asString(row.id)})),
    journalContents:asArray(drafts.bibliography.journal_contents).map(asRecord).map(row=>({id:asString(row.id) || null,title:asString(row.title),author_display:asString(row.author_display),page_range:asString(row.page_range)})),
  };
  if (reader) return <div className="workflow-v307-live-preview"><header><h2>读者会看到什么</h2><span>文件内容预览</span></header>{pdfUrl ? <WorkflowInspector key={pdfUrl} selection={{kind:"pdf",title,pdfUrl}} token={token} onClose={()=>onLocate("work")}/> : <p className="empty-state">当前文件暂无可用预览。请先核对文件是否上传并验证完成。</p>}</div>;
  return <div className="workflow-v307-live-preview">
    <header><h2>读者会看到什么</h2></header>
    <div className="selected-preview-tools"><div role="group" aria-label="预览尺寸"><button type="button" aria-pressed={device==="desktop"} onClick={()=>setDevice("desktop")}><Monitor size={15}/>电脑</button><button type="button" aria-pressed={device==="mobile"} onClick={()=>setDevice("mobile")}><Smartphone size={15}/>手机</button></div><button type="button" onClick={()=>{setExpanded(true);fullPreview.current?.showModal();}}><Maximize2 size={15}/>放大查看</button></div>
    <p className="workflow-v307-preview-state" role="status">{dirty ? "有未保存修改 · 当前输入实时预览" : "当前已保存草稿 · 尚需明确发布"}</p>
    {coverError ? <p role="status">{coverError}</p> : null}
    <div className="workflow-v307-preview-locate"><button type="button" onClick={() => onLocate("work")}>编辑书目与封面</button><button type="button" onClick={() => onLocate("contributors")}>编辑作者与分类</button></div>
    <div onClickCapture={event => { const target = event.target as HTMLElement; if (target.closest("a,button")) return; if (target.closest(".book-cover")) onLocate("work"); else if (target.closest(".work-author-link")) onLocate("contributors"); else if (target.closest(".work-hero h1,.work-summary,.work-body")) onLocate("work"); else if (target.closest("dl")) onLocate("bibliography"); }}>
      <PreviewViewport device={device}><SiteHeader preview previewPath={`/works/${work.slug}`}/><WorkDetailView work={work} presentation={presentation} preview={{publicationState:"draft",pdfPreviewUrl:"",returnHref}} footer={null} /></PreviewViewport>
    </div>
    <dialog ref={fullPreview} className="fixed-preview-dialog" onClose={()=>setExpanded(false)}><header><strong>{dirty ? "当前输入 · 尚未保存" : "已保存内容"}</strong><button type="button" onClick={()=>fullPreview.current?.close()}>关闭预览</button></header>{expanded ? <PreviewViewport device={device}><SiteHeader preview previewPath={`/works/${work.slug}`}/><WorkDetailView work={work} presentation={presentation} preview={{publicationState:"draft",pdfPreviewUrl:"",returnHref}} footer={null}/></PreviewViewport> : null}</dialog>
  </div>;
}
