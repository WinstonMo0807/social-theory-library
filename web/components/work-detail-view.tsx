import Link from "next/link";
import { ArrowRight, Eye, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { AssetDownloadButton } from "@/components/asset-download-button";
import { SaveWorkButton } from "@/components/save-work-button";
import { WorkCitationPanel } from "@/components/work-citation-panel";
import { BookCard, BookCover, SectionHeading, TagList } from "@/components/ui";
import type { Work } from "@/lib/data";

type WorkDetailViewProps = {
  work: Work;
  relatedWorks?: Work[];
  preview?: {
    publicationState: string;
    pdfPreviewUrl: string;
    draftRevision?: {
      revision: number;
      changedFields: string[];
      hasConflict: boolean;
    } | null;
  };
  footer: ReactNode;
};

export function WorkDetailView({ work, relatedWorks = [], preview, footer }: WorkDetailViewProps) {
  const primaryAuthor = work.authors?.find((author) => author.slug);
  const tags = [
    ...(work.theories ?? []).map((item) => item.name),
    ...(work.topics ?? []).map((item) => item.name),
  ];
  const languageLabel = ({
    "zh-CN": "简体中文",
    "zh-TW": "繁体中文",
    en: "英文",
  } as Record<string, string>)[work.language ?? "zh-CN"] ?? work.language;
  const previewPdf = preview?.pdfPreviewUrl || "";
  const curatedGroups = [
    { key: "core_viewpoint", title: "核心观点", claims: work.curatedClaims?.core_viewpoint ?? [] },
    { key: "major_criticism", title: "主要批评", claims: work.curatedClaims?.major_criticism ?? [] },
    { key: "major_response", title: "主要回应", claims: work.curatedClaims?.major_response ?? [] },
  ] as const;

  return (
    <>
      <div className="page-shell work-detail">
        {preview ? (
          <div className="admin-page-preview-banner" role="status">
            <ShieldCheck size={16} />
            <strong>管理员页面预览</strong>
            <span>
              {preview.draftRevision
                ? `正在预览已保存的第 ${preview.draftRevision.revision} 版草稿，包含 ${preview.draftRevision.changedFields.length} 项待发布变更。${preview.draftRevision.hasConflict ? "正式内容已变化，请返回工作台处理冲突。" : "普通访客仍看到正式版本。"}`
                : `当前版本状态为 ${preview.publicationState}。此页面需要后台权限，普通访客仍无法访问。`}
            </span>
          </div>
        ) : null}
        <p className="breadcrumbs">
          {preview ? <><Link href="/admin/library">馆藏管理</Link> / 页面预览 / {work.title}</> : <><Link href="/">首页</Link> / <Link href="/explore">馆藏</Link> / {work.title}</>}
        </p>
        <section className="work-hero">
          <BookCover work={work} size="large" />
          <div>
            <p className="eyebrow">{work.kind} · {work.school}</p>
            <h1>{work.title}</h1>
            {work.originalTitle ? <p className="original-title">{work.originalTitle}</p> : null}
            {primaryAuthor && !preview ? (
              <Link className="work-author-link" href={`/scholars/${primaryAuthor.slug}`}>
                {work.author} <ArrowRight size={15} />
              </Link>
            ) : <p className="work-author-link">{work.author}</p>}
            <p className="work-summary">{work.summary}</p>
            <TagList items={tags} />
          </div>
          <aside>
            <dl>
              <div><dt>出版年份</dt><dd>{work.year}</dd></div>
              <div><dt>文献类型</dt><dd>{work.kind}</dd></div>
              <div><dt>页数</dt><dd>{work.pages}</dd></div>
              <div><dt>文本状态</dt><dd>{work.pages ? "全文可检索" : "待处理"}</dd></div>
              <div><dt>语言</dt><dd>{languageLabel}</dd></div>
            </dl>
            {preview ? (
              previewPdf
                ? <a className="button" href={previewPdf} target="_blank" rel="noreferrer"><Eye size={16} /> 后台 PDF</a>
                : <span className="button disabled" aria-disabled="true"><Eye size={16} /> PDF 尚未就绪</span>
            ) : (
              work.pages ? <>
                <Link className="button" href={`/reader/${work.id}`}><Eye size={16} /> 在线阅读</Link>
                <AssetDownloadButton assetId={work.id} />
                <div className="button secondary work-save-control"><SaveWorkButton workId={work.workId} /></div>
              </> : <>
                <span className="button disabled" aria-disabled="true"><Eye size={16} /> 当前版本不可在线阅读</span>
                <div className="button secondary work-save-control"><SaveWorkButton workId={work.workId} /></div>
              </>
            )}
          </aside>
        </section>

        <div className="work-body">
          <section className="panel">
            <SectionHeading title="内容简介" />
            <p>{work.summary} 馆藏版本已经建立逐页规范文本。全文搜索结果、文档内搜索、干净复制和页码引用均使用同一份页级记录。</p>
            <h2>目录</h2>
            {(work.outline ?? []).map((item, index) => (
              preview ? (
                <div className="toc-row" key={`${item.index}-${item.chapter_title}`}>
                  <span>{String(index + 1).padStart(2, "0")}</span><strong>{item.chapter_title}</strong><small>{item.printed_label || item.index}</small>
                </div>
              ) : (
                <Link className="toc-row" href={`/reader/${work.id}?page=${item.index}`} key={`${item.index}-${item.chapter_title}`}>
                  <span>{String(index + 1).padStart(2, "0")}</span><strong>{item.chapter_title}</strong><small>{item.printed_label || item.index}</small>
                </Link>
              )
            ))}
            {!work.outline?.length ? <p className="empty-state">该 PDF 没有可识别的目录书签。</p> : null}
          </section>
          {preview ? (
            <section className="panel admin-preview-note">
              <SectionHeading title="预览边界" />
              <p>引用、保存、下载和公共 Reader 动作在管理员页面预览中不执行。发布后，公开页面会使用相同的内容组件并恢复这些动作。</p>
            </section>
          ) : work.editionId ? <WorkCitationPanel editionId={work.editionId} /> : null}
        </div>
        {curatedGroups.map((group) => group.claims.length ? (
          <section className={`detail-section work-curated-claims work-curated-${group.key}`} key={group.key}>
            <SectionHeading title={group.title} />
            <div className="work-curated-claim-list">
              {group.claims.map((claim) => (
                <article key={claim.id}>
                  {claim.title ? <h3>{claim.title}</h3> : null}
                  <p className="work-curated-proposition">{claim.proposition}</p>
                  {claim.editorial_note ? <p className="work-curated-note">{claim.editorial_note}</p> : null}
                  <details className="work-curated-evidence">
                    <summary>查看依据 <span>{claim.evidence.length} 条馆藏原文</span></summary>
                    <div>
                      {claim.evidence.map((evidence) => {
                        const author = evidence.source.authors?.join("、");
                        const pageLabel = evidence.locator.printed_page_label
                          ? `印刷页 ${evidence.locator.printed_page_label} · PDF 第 ${evidence.locator.page} 页`
                          : `PDF 第 ${evidence.locator.page} 页`;
                        return (
                          <blockquote key={evidence.id}>
                            <p>{evidence.text}</p>
                            <footer>
                              <span>{author ? `${author} · ` : ""}《{evidence.source.work_title}》 · {pageLabel}</span>
                              {preview ? <span>预览中不打开公开 Reader</span> : (
                                <Link href={evidence.reader_url}>
                                  查看原文 <ArrowRight size={14} />
                                </Link>
                              )}
                            </footer>
                          </blockquote>
                        );
                      })}
                    </div>
                  </details>
                </article>
              ))}
            </div>
          </section>
        ) : null)}
        {work.theoryAssociations?.length ? (
          <section className="detail-section work-theory-associations">
            <SectionHeading title="理论关联" />
            <div className="work-theory-association-list">
              {work.theoryAssociations.map((association) => (
                <article key={association.id}>
                  <header>
                    <div>
                      <span>{association.role_label}</span>
                      <h2>{preview ? association.node.name : <Link href={`/theories/nodes/${association.node.slug}`}>{association.node.name}</Link>}</h2>
                      {association.node.foreign_name ? <p>{association.node.foreign_name}</p> : null}
                    </div>
                    <small>人工审核通过</small>
                  </header>
                  {association.evidence.length ? (
                    <div className="work-theory-evidence-list">
                      {association.evidence.slice(0, 3).map((evidence) => (
                        <div key={evidence.id}>
                          <p>{evidence.quote}</p>
                          {preview ? <span>PDF 第 {evidence.page_number} 页</span> : (
                            <Link href={evidence.reader_href}>
                              PDF 第 {evidence.page_number}{evidence.page_end && evidence.page_end !== evidence.page_number ? `–${evidence.page_end}` : ""} 页
                              <ArrowRight size={14} />
                            </Link>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : <p className="empty-state">该关系已确认，页码证据仍待补充。</p>}
                </article>
              ))}
            </div>
          </section>
        ) : null}
        {!preview ? (
          <section className="detail-section">
            <SectionHeading title="相关馆藏" href={`/explore?q=${work.school}`} />
            <div className="four-book-grid">
              {relatedWorks.slice(0, 4).map((item) => <BookCard work={item} key={item.id} />)}
              {!relatedWorks.length ? <p className="empty-state">尚无依据已确认流派或主题关联的其他公开馆藏。</p> : null}
            </div>
          </section>
        ) : null}
      </div>
      {footer}
    </>
  );
}
