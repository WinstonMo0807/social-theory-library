"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Monitor, Smartphone, RefreshCw } from "lucide-react";
import Link from "next/link";
import { SiteHeader } from "@/components/site-header";
import { BookCard, TagList } from "@/components/ui";
import { PreviewViewport } from "../curation/fixed-page-editor";
import styles from "./work-preview.module.css";
import { ActionButton, AsyncStatus } from "@/components/action-feedback";
import { WorkDetailView } from "@/components/work-detail-view";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import type { Work } from "@/lib/data";
import type { ApiWork } from "@/lib/api/public-catalog";
import { useSearchParams } from "next/navigation";
import { safeAdminHref } from "@/lib/admin-route-context";

type PreviewPayload = {
  preview_mode: true;
  publication_state: string;
  editorial_revision: {
    id: string;
    revision: number;
    changed_fields: string[];
    has_conflict: boolean;
  } | null;
  public_url: string;
  pdf_preview_url: string;
  return_url: string;
  work: ApiWork;
};

const coverStyles: Work["cover"][] = ["dark", "paper", "cream", "line"];

function adaptPreviewWork(value: ApiWork): Work {
  const authors = value.edition?.contributors.filter((row) => row.role === "author") ?? [];
  return {
    id: value.edition?.readable_asset?.id ?? value.id,
    workId: value.id,
    editionId: value.edition?.id,
    slug: value.edition?.public_slug || value.id,
    title: value.title,
    originalTitle: value.original_title || undefined,
    subtitle: value.subtitle || undefined,
    publisher: value.edition?.publisher || undefined,
    isbn: value.edition?.isbn13 || value.edition?.isbn10 || value.edition?.isbn || undefined,
    originalLanguage: value.original_language || undefined,
    versionLabel: value.edition?.version_label || undefined,
    translators: value.edition?.contributors.filter(row=>row.role==="translator").map(row=>({name:row.person.preferred_name,slug:row.person.scholar_slug})),
    author: authors.map((row) => row.person.preferred_name).join("、") || "作者待确认",
    year: String(value.edition?.publication_year ?? "出版年不详"),
    kind: ({ book: "图书", journal_article: "期刊论文", journal_issue: "整期期刊", thesis: "学位论文", report: "研究报告" } satisfies Record<ApiWork["document_type"], Work["kind"]>)[value.document_type],
    school: value.theories[0]?.name ?? value.topics[0]?.name ?? "社会理论",
    summary: value.abstract || "简介待编辑。",
    cover: coverStyles[0],
    coverImage: normalizePublicResourceUrl(value.cover || value.recommendation_image || "") || undefined,
    coverSources: (value.cover ? value.cover_media : value.recommendation_media)?.renditions.map((row) => ({ ...row, url: normalizePublicResourceUrl(row.url) })),
    coverAlt: (value.cover ? value.cover_media : value.recommendation_media)?.alt_text || undefined,
    pages: value.edition?.readable_asset?.page_count ?? 0,
    language: value.language,
    authors: authors.map((row) => ({ name: row.person.preferred_name, slug: row.person.scholar_slug })),
    theories: value.theories,
    topics: value.topics,
    theoryAssociations: value.theory_associations ?? [],
    curatedClaims: value.curated_claims,
    outline: value.outline ?? [],
    journalContents: value.edition?.journal_contents ?? [],
  };
}

export function AdminWorkPagePreview({
  editionId,
  footer,
  embedded = false,
  embeddedView = "details",
}: {
  editionId: string;
  footer: ReactNode;
  embedded?: boolean;
  embeddedView?: "details" | "card";
}) {
  const routeParams = useSearchParams();
  const [payload, setPayload] = useState<PreviewPayload | null>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("details");
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const requestRevision = useRef(0);

  const load = useCallback(async () => {
    const revision = ++requestRevision.current;
    setLoading(true);
    setMessage("");
    try {
      const result = await apiRequest<PreviewPayload>(
        `/catalog/admin/page-preview/editions/${editionId}/`,
        {},
        getServerSessionCredential(),
      );
      if (requestRevision.current === revision) setPayload(result);
    } catch (reason) {
      if (requestRevision.current === revision) {
        setMessage(reason instanceof Error ? reason.message : "管理员页面预览加载失败。");
      }
    } finally {
      if (requestRevision.current === revision) setLoading(false);
    }
  }, [editionId]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => {
      window.clearTimeout(timer);
      requestRevision.current += 1;
    };
  }, [load]);

  const work = useMemo(() => payload?.work.edition?.id === editionId ? adaptPreviewWork(payload.work) : null, [payload, editionId]);
  if (!work || !payload) {
    return (
      <div className="admin-page admin-page-preview-state">
        <AsyncStatus
          state={loading ? "pending" : "error"}
          message={loading ? "正在生成管理员页面预览……" : message || "预览不可用。"}
          assertive={!loading}
        />
        {!loading ? (
          <ActionButton className="button secondary" onClick={() => void load()}>
            <RefreshCw size={15} />重试
          </ActionButton>
        ) : null}
      </div>
    );
  }
  const returnHref = safeAdminHref(routeParams.get("return_to"), payload.return_url);
  const page = <><SiteHeader preview previewPath="/explore"/>
    <WorkDetailView
      work={work}
      footer={footer}
      preview={{
        publicationState: payload.publication_state,
        pdfPreviewUrl: normalizePublicResourceUrl(payload.pdf_preview_url),
        returnHref: safeAdminHref(routeParams.get("return_to"), payload.return_url),
        draftRevision: payload.editorial_revision
          ? {
              revision: payload.editorial_revision.revision,
              changedFields: payload.editorial_revision.changed_fields,
              hasConflict: payload.editorial_revision.has_conflict,
            }
          : null,
      }}
    /></>;
  if (embedded || routeParams.get("embed") === "1") return embeddedView === "card" ? <div className={styles.cardPreview} inert><BookCard work={work} exploreActions/></div> : page;
  const fields = payload.editorial_revision?.changed_fields ?? [];
  const changes = [
    { title: "基本信息", step: "bibliography", fields: fields.filter(field => !/cover|abstract/.test(field)) },
    { title: "图书封面", step: "work", fields: fields.filter(field => /cover/.test(field)) },
    { title: "内容简介", step: "work", fields: fields.filter(field => /abstract/.test(field)) },
  ];
  return <div className={styles.page}><header><h1>查看发布后的样子 <small>仅管理员可见</small></h1><strong>已保存的内容 · 发布前预览</strong><p>确认页面效果后，可进入发布检查。</p></header>
    <div className={styles.layout}><section className={styles.canvas} aria-label="已保存内容预览"><nav className={styles.tools} aria-label="预览内容">
      <div>{[{id:"details",label:"图书详情"},{id:"card",label:"搜索卡片"},{id:"topics",label:"相关主题"}].map(item=><button type="button" key={item.id} aria-pressed={tab===item.id} onClick={()=>setTab(item.id)}>{item.label}</button>)}</div>
      <div>{(["desktop","mobile"] as const).map(item=><button type="button" key={item} aria-pressed={device===item} onClick={()=>setDevice(item)}>{item==="desktop" ? <Monitor size={16}/> : <Smartphone size={16}/>} {item==="desktop" ? "电脑" : "手机"}</button>)}</div>
    </nav><PreviewViewport device={device}>{tab==="details" ? page : <div className={styles.cardPreview} inert>{tab==="card" ? <BookCard work={work} exploreActions/> : <><h2>相关主题</h2><TagList items={(work.topics??[]).map(row=>row.name)}/></>}</div>}</PreviewViewport></section>
    <aside className={styles.checks}><h2>本次改动与检查</h2>{changes.map((change,index)=><section key={change.title}><h3><span>{index+1}</span>{change.title}<small>{change.fields.length ? "已修改" : "—"}</small></h3>{change.fields.length ? <p>{change.fields.length} 项已保存改动</p> : null}<Link href={`${returnHref.split("#")[0]}#${change.step}`}>查看详情 ›</Link></section>)}
      <section><h3>检查结果</h3><ul><li>页面数据 {message ? "读取失败" : "已读取"}</li><li>图片加载 待核实</li><li>链接跳转 待核实</li><li>保存冲突 {payload.editorial_revision?.has_conflict ? "需处理" : "未发现"}</li></ul>{message ? <p role="alert">{message}</p> : null}</section>
      <p className={styles.note}>这是已保存内容的预览。引用、保存、下载和公共 Reader 动作在管理员页面预览中不执行。</p>
      <footer><Link className="button secondary" href={returnHref}>返回编辑</Link><Link className="button" href={`${returnHref.split("#")[0]}#publication`}>进入发布检查</Link><ActionButton className="button secondary" disabled={loading} onClick={()=>void load()}>刷新已保存内容</ActionButton></footer>
    </aside></div></div>;
}
