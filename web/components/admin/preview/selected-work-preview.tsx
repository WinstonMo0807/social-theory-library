"use client";

import Link from "next/link";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { CoverImage } from "../workflow/edition-cover-editor";
import { useState } from "react";
import { Monitor, Smartphone, Maximize2 } from "lucide-react";
import { AdminWorkPagePreview } from "./work-page-preview";
import { PreviewViewport } from "../curation/fixed-page-editor";
import { WORKFLOW_GROUPS } from "../workflow/file-presentation";

/** Uses the protected saved-edition preview; selection never saves or publishes. */
export function SelectedWorkPreview({ editionId, title, publicHref = "", editHref = "", currentStep, heading, subtitle }: {
  editionId?: string | null; title?: string; publicHref?: string; editHref?: string; currentStep?: string; heading?: string; subtitle?: string;
}) {
  const [perspective, setPerspective] = useState<"draft" | "published">("draft");
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [location, setLocation] = useState<"details" | "card">("details");
  const stepIndex = WORKFLOW_GROUPS.findIndex(group => group.steps.some(step => step === currentStep));
  const href = perspective === "published" ? publicHref : editionId ? `/admin/preview/works/${encodeURIComponent(editionId)}` : "";
  return <aside className="selected-work-preview" aria-label="已保存内容预览">
    <header className="selected-preview-heading"><div><h2>{heading || (title ? `正在处理：${title}` : "读者会看到什么")}</h2><p>{subtitle || ""}</p></div>{stepIndex >= 0 ? <div className="selected-preview-progress"><strong>当前：第 {stepIndex + 1} / 4 步</strong><ol className="reference-preview-steps" aria-label="当前整理进度">{WORKFLOW_GROUPS.map((group,index)=><li key={group.label} aria-current={index === stepIndex ? "step" : undefined}><b>{index+1}</b><span>{group.label}</span></li>)}</ol></div> : null}</header>
    <section className="selected-preview-paper"><div className="selected-preview-paper-heading"><div><h2>已保存内容预览</h2><p>这里在网站上的实际显示效果。</p></div>
    <div className="selected-preview-tools">
      <div role="group" aria-label="预览内容"><button type="button" aria-pressed={perspective === "draft"} onClick={() => setPerspective("draft")}>修改后</button><button type="button" aria-pressed={perspective === "published"} onClick={() => setPerspective("published")}>当前线上</button></div>
      <div role="group" aria-label="预览尺寸"><button type="button" aria-pressed={device === "desktop"} onClick={() => setDevice("desktop")}><Monitor size={15}/>电脑</button><button type="button" aria-pressed={device === "mobile"} onClick={() => setDevice("mobile")}><Smartphone size={15}/>手机</button></div>
      {href ? <Link href={href} target="_blank"><Maximize2 size={15}/>放大查看</Link> : null}
    </div></div>
    <div className="selected-preview-location"><label>位置：<select aria-label="预览位置" value={location} disabled={perspective === "published"} onChange={event=>setLocation(event.target.value as "details" | "card")}><option value="details">图书详情页</option><option value="card">搜索卡片</option></select></label><p className="selected-preview-caption">{perspective === "draft" ? "已保存内容预览" : publicHref ? "当前公开内容" : "当前没有公开页面"}</p></div>
    <div className={`selected-preview-viewport ${device}`}>
      {perspective === "published" ? publicHref ? <PreviewViewport device={device}><iframe src={publicHref} title="当前公开图书详情" style={{ width: "100%", height: 1000, border: 0 }}/></PreviewViewport> : <p className="empty-state">—</p> : editionId ? <PreviewViewport device={device}><div className="saved-content-preview"><AdminWorkPagePreview embedded embeddedView={location} key={editionId} editionId={editionId} footer={null}/></div></PreviewViewport> : <p className="empty-state">—</p>}
    </div></section>
    {editHref ? <footer><Link className="button" href={editHref}>继续填写这本书</Link></footer> : null}
  </aside>;
}

export function SavedEditionCover({editionId,title}: {editionId?:string|null;title:string}) {
  const token=getServerSessionCredential();
  const resource=useApiResource<{edition_id:string;image_url:string}>(editionId ? `/catalog/admin/editions/${editionId}/cover/` : "",token);
  return <span className="reference-saved-cover">{resource.data && resource.data.edition_id===editionId && resource.data.image_url ? <CoverImage url={resource.data.image_url} token={token} alt={title}/> : resource.error ? <small role="status">封面读取失败</small> : null}</span>;
}
