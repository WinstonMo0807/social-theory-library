"use client";

import { LoadingState } from "@/components/ui/loading-state";

import Link from "next/link";
import { useCallback, useRef } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import type { PlacementPage, PlacementState } from "@/lib/api/curation-workspace.client";
import type { SiteConfig } from "@/lib/site-config";
import type { TimelineEventDetail } from "@/lib/api/timeline.types";
import type { Subdiscipline, SubdisciplineSource } from "@/lib/api/taxonomy.types";
import { PreviewSurface, type KnowledgePreviewPayload } from "../preview/knowledge-page-preview";
import { RecommendationIssueView } from "@/components/public/recommendation-issue-view";
import type { IssuePublicationReviewData } from "./issue-publication-review";
import { TimelineEventDetails } from "@/components/public/timeline-event-details";
import { PlacementList } from "@/components/public/placement-list";
import { SiteHeader } from "@/components/site-header";
import { SiteFooterView } from "@/components/public/site-footer-view";
import timelineStyles from "@/components/public/theory-timeline.module.css";

type PagePreview = {owner_id:string;page_id:string;page_type:PlacementPage;expected_revision:string;parent_version:string;checked_at:string;config:SiteConfig} & (
  {kind:"knowledge";page:KnowledgePreviewPayload} | {kind:"issue";page:IssuePublicationReviewData["reader_preview"]} | {kind:"timeline_event";page:TimelineEventDetail}
);

export function PlacementPagePreview({owner,pageType,pageId,version,items,groups,selected,onSelect}:{
  owner:string;pageType:PlacementPage;pageId:string;version:string;items:PlacementState["items"];groups:PlacementState["groups"];selected:string;onSelect:(id:string)=>void;
}) {
  const placementRegion=useRef<HTMLDivElement|null>(null);
  const load=useCallback(async (path:string,signal:AbortSignal)=>{
    const value=await apiRequest<PagePreview>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false);
    if(value.owner_id!==owner||value.page_id!==pageId||value.page_type!==pageType||value.expected_revision!==version)throw new Error("预览不属于当前账户或页面，请重新读取。");
    return value;
  },[owner,pageId,pageType,version]);
  const resource=usePersistentWorkspace<PagePreview>(`/catalog/admin/content-placements/${pageType}/${pageId}/parent-preview/?${new URLSearchParams({expected_revision:version})}`,owner,undefined,load);
  if(resource.error)return <section role="alert"><p>{resource.error}</p><p>编排输入仍保留，完整页面读取成功后才能核对其位置。</p><button type="button" onClick={resource.reload}>重新读取页面</button></section>;
  const data=resource.data;
  if(!data)return <LoadingState role="status">正在读取完整页面的已保存资料…</LoadingState>;
  const visibleItems=pageType==="subdiscipline"?items.filter(row=>row.target.type!=="span"):items;
  const placements=<div ref={placementRegion} data-placement-selection="true"><PlacementList items={visibleItems} groups={groups} selected={selected} onSelect={onSelect}/></div>;
  const footer=<>{placements}<SiteFooterView config={data.config} preview/></>;
  let knowledge=data.kind==="knowledge"?data.page:null;
  if(knowledge&&pageType==="subdiscipline"){
    const original=knowledge.perspective.data as Subdiscipline;
    const sources:SubdisciplineSource[]=items.flatMap(row=>{
      const source=row.source;
      if(row.target.type!=="span"||!source?.public_eligible||!source.text||!source.asset_id||!source.document_revision_id||!source.work_id||!source.edition_id||!source.reader_url||typeof source.page_start!=="number")return [];
      return [{id:row.id,source_kind:"placement_span",work_id:source.work_id,edition_id:source.edition_id,asset_id:source.asset_id,document_revision_id:source.document_revision_id,title:String(source.work_title||source.title),edition_label:String(source.edition_label||""),quote:source.text,pdf_page:source.page_start,printed_page_label:String(source.printed_label||""),reader_href:source.reader_url}];
    });
    knowledge={...knowledge,perspective:{...knowledge.perspective,data:{...original,sources:[...(original.sources||[]).filter(row=>row.source_kind!=="placement_span"),...sources]}}};
  }
  return <>
    <p role="status">父页面已保存资料 · 编排区使用当前输入。点击编排条目可返回编辑，其他控件仅展示。<button type="button" onClick={resource.reload}>更新父页面资料</button><button type="button" disabled={!visibleItems.some(row=>row.id===selected&&row.source?.public_eligible&&!row.concept_usage)} onClick={()=>placementRegion.current?.querySelector("[data-selected=true]")?.scrollIntoView({block:"center",behavior:"auto"})}>定位当前条目</button></p>
    <div onClickCapture={event=>{
      const target=event.target as HTMLElement;
      if(target.closest("[data-placement-selection]"))return;
      if(target.closest("a,button,input,select,textarea,form")){event.preventDefault();event.stopPropagation();}
    }} onSubmitCapture={event=>{event.preventDefault();event.stopPropagation();}}>
      <SiteHeader config={data.config} preview/>
      {knowledge?<PreviewSurface payload={knowledge} pageId="overview" footer={footer} subdisciplineDraftFields={false}/>:data.kind==="issue"?<><RecommendationIssueView issue={data.page} preview/>{footer}</>:data.kind==="timeline_event"?<>
        <div className={timelineStyles.page}><nav className={`${timelineStyles.breadcrumb} ${timelineStyles.standaloneBreadcrumb}`} aria-label="面包屑"><Link href="/theories/timeline">学科与概念时间线</Link><span>/</span><span>{data.page.title}</span></nav><TimelineEventDetails event={data.page} standalone/></div>{footer}
      </>:null}
    </div>
  </>;
}
