"use client";
import { useEffect, useState } from "react";
import { apiBlob, apiRequest } from "@/lib/api";
import { WorkDetailView } from "@/components/work-detail-view";
import type { Work } from "@/lib/data";
import type { WorkflowStepKey } from "./workflow-state";
import { asArray, asRecord, asString, type WorkflowDrafts, type WorkflowContext } from "./workflow-types";

export function WorkflowLivePreview({ drafts, context, token, savedAt, dirty, returnHref, onLocate }: {
  drafts: WorkflowDrafts; context: WorkflowContext; token: string | null; savedAt: string; dirty: boolean;
  returnHref: string; onLocate: (step: WorkflowStepKey) => void;
}) {
  const [cover, setCover] = useState("");
  const [coverError, setCoverError] = useState("");
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
  const authorRows = asArray(drafts.contributors.items).map(asRecord).filter(row => row.role === "author" && asRecord(row.scope).kind !== "chapter");
  const title = asString(drafts.work.title, "未填写题名");
  const assets = asArray(drafts.file.assets).map(asRecord);
  const currentAsset = assets.find(asset => asset.is_current && asset.kind === "normalized") ?? assets.find(asset => asset.is_current);
  const documentType = asString(drafts.work.document_type, "book");
  const work: Work = {
    id: asString(currentAsset?.id), workId: asString(context.work_id), editionId, slug: asString(context.work_id), title,
    subtitle: asString(drafts.work.subtitle), originalTitle: asString(drafts.work.original_title),
    originalLanguage: asString(drafts.work.original_language), firstPublicationDate: asString(drafts.work.first_publication_date),
    author: authorRows.map(row => asString(row.display_name || row.name)).filter(Boolean).join("、") || "作者待确认",
    year: asString(drafts.bibliography.publication_year) || String(drafts.bibliography.publication_year || "年份待补"),
    kind: ({ book:"图书", journal_article:"期刊论文", journal_issue:"整期期刊", thesis:"学位论文", report:"研究报告" } as Record<string, Work["kind"]>)[documentType] || "图书",
    school: asArray(drafts.classification.primary_disciplines).map(asRecord).map(row => asString(row.name)).join("、"),
    summary: asString(drafts.work.abstract), cover:"paper", coverImage:cover || undefined, coverAlt:title,
    pages: Number(currentAsset?.page_count || drafts.reader.page_count || 0), language:asString(drafts.work.language),
    authors:authorRows.map(row => ({name:asString(row.display_name || row.name)})),
    theories:asArray(drafts.knowledge.nodes).map(asRecord).map(row => ({name:asString(row.name),slug:asString(row.id)})),
    topics:asArray(drafts.knowledge.topics).map(asRecord).map(row => ({name:asString(row.name),slug:asString(row.id)})),
    version: {
      id: editionId, public_slug: asString(drafts.bibliography.public_slug),
      version_label: asString(drafts.bibliography.version_label), edition_statement: asString(drafts.bibliography.version_label),
      publication_year: Number(drafts.bibliography.publication_year) || null,
      publication_date: asString(drafts.bibliography.publication_date) || null,
      publisher: asString(drafts.bibliography.publisher), publisher_verbatim: asString(drafts.bibliography.publisher),
      publication_place_verbatim: asString(drafts.bibliography.publication_place),
      journal_title: asString(drafts.bibliography.journal_title), volume: asString(drafts.bibliography.volume), issue: asString(drafts.bibliography.issue),
      page_range: asString(drafts.bibliography.page_range), isbn: asString(drafts.bibliography.isbn), isbn10: asString(drafts.bibliography.isbn10),
      isbn13: asString(drafts.bibliography.isbn13), doi: asString(drafts.bibliography.doi), extent: asString(drafts.bibliography.extent),
      language: asString(drafts.work.language), availability: "metadata", readable_asset: null, journal_contents: [],
      contributors: asArray(drafts.contributors.items).map(asRecord).map((row, order) => ({
        role: asString(row.role), order, person: { id: null, preferred_name: asString(row.display_name || row.name) },
        scope: asRecord(row.scope).kind === "chapter"
          ? { kind: "chapter", status: "unavailable", chapters: [], notice: "章节责任已指定；原文入口将在保存、校验并正式发布后提供。" }
          : { kind: "edition", status: "available", chapters: [], notice: "" },
      })),
    },
  };
  return <div className="workflow-v307-live-preview">
    <p className="workflow-v307-preview-state" role="status">{dirty ? "有未保存修改 · 当前输入实时预览" : "当前已保存草稿 · 尚需明确发布"}</p>
    {coverError ? <p role="status">{coverError}</p> : null}
    <div className="workflow-v307-preview-locate"><button type="button" onClick={() => onLocate("work")}>编辑书目与封面</button><button type="button" onClick={() => onLocate("contributors")}>编辑作者与分类</button></div>
    <div onClickCapture={event => { const target = event.target as HTMLElement; if (target.closest("a,button")) return; if (target.closest(".book-cover")) onLocate("work"); else if (target.closest(".work-author-link")) onLocate("contributors"); else if (target.closest(".work-hero h1,.work-summary,.work-body")) onLocate("work"); else if (target.closest("dl")) onLocate("bibliography"); }}>
      <WorkDetailView work={work} preview={{publicationState:"draft",pdfPreviewUrl:"",returnHref}} footer={null} />
    </div>
  </div>;
}
