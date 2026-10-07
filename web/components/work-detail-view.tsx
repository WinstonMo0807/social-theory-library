import Link from "next/link";
import { ArrowRight, BookOpen, Download, Bookmark } from "lucide-react";
import type { ReactNode } from "react";
import { AssetDownloadButton } from "@/components/asset-download-button";
import { SaveWorkButton } from "@/components/save-work-button";
import { WorkCitationPanel } from "@/components/work-citation-panel";
import { BookCard, BookCover, SectionHeading, TagList } from "@/components/ui";
import type { Work } from "@/lib/data";
import { WorkDetailSummary, WorkDetailTabs, type WorkDetailPresentation } from "./work-detail-tabs";
import styles from "./work-detail.module.css";

type WorkDetailViewProps = {
  work: Work;
  relatedWorks?: Work[];
  presentation?: WorkDetailPresentation;
  preview?: {
    publicationState: string;
    pdfPreviewUrl: string;
    returnHref: string;
    draftRevision?: {
      revision: number;
      changedFields: string[];
      hasConflict: boolean;
    } | null;
  };
  footer: ReactNode;
};

const languages: Record<string, string> = {
  "zh-CN": "简体中文", "zh-TW": "繁体中文", en: "英语", fr: "法语", de: "德语", ja: "日语", ru: "俄语",
};

export function WorkDetailView({ work, relatedWorks = [], preview, footer, presentation = "publication" }: WorkDetailViewProps) {
  const primaryAuthor = work.authors?.find(author => author.slug);
  const tags = [...(work.theories ?? []).map(item => item.name), ...(work.topics ?? []).map(item => item.name)];
  const languageLabel = languages[work.language || ""] || work.language || "—";
  const publication = [work.publisher, work.year, work.versionLabel].filter(Boolean).join(" · ");
  const readerHref = work.readerHref || `/reader/${work.id}`;
  const renderTags = (items: string[]) => preview ? <div inert><TagList items={items}/></div> : <TagList items={items}/>;
  const actions = <div className={styles.actions}>{preview ? <>
    <span className="button disabled" aria-disabled="true" title="预览中不执行公开阅读操作"><BookOpen size={17}/>在线阅读</span>
    <span className="button secondary disabled" aria-disabled="true"><Download size={17}/>下载 PDF</span>
    {presentation === "publication" ? <span className="button secondary disabled" aria-disabled="true"><Bookmark size={17}/>加入书架</span> : null}
  </> : <>
    {work.pages ? <Link className="button" href={readerHref}><BookOpen size={17}/>在线阅读</Link> : <span className="button disabled" aria-disabled="true"><BookOpen size={17}/>当前版本不可在线阅读</span>}
    {work.downloadAssetId || work.pages ? <AssetDownloadButton assetId={work.downloadAssetId || work.id}/> : null}
    <div className="button secondary work-save-control"><SaveWorkButton workId={work.workId}/></div>
  </>}</div>;
  const metadata = presentation === "contents" ? [
    ["主题", (work.topics ?? []).map(item => item.name).join(" · ")],
    ["ISBN", work.isbn], ["分类", work.categories?.join(" · ")], ["出版时间", work.year], ["页数", work.pages || ""],
  ] : presentation === "reading" ? [
    ["作者", work.author], ["译者", work.translators?.map(item => item.name).join("、")],
    ["出版社", work.publisher], ["出版年", work.year], ["页数", work.pages || ""], ["分类", work.categories?.join(" · ")],
  ] : [
    ["出版信息", publication], ["原作语言", languages[work.originalLanguage || ""] || work.originalLanguage],
    ["主题", (work.topics ?? []).map(item => item.name).join(" · ")],
    ["所属流派", (work.theories ?? []).map(item => item.name).join(" · ")], ["ISBN", work.isbn],
  ];
  const authorIntroduction = <><h2>作者介绍</h2>{work.authors?.filter(author => author.biography?.trim()).map((author, index) => <article key={`${author.name}-${index}`}><h3>{author.name}</h3><p>{author.biography}</p></article>)}</>;
  const outline = <><h2>{work.kind === "整期期刊" ? "本期目录与论文" : "目录"}</h2>
    {(work.kind === "整期期刊" ? work.journalContents ?? [] : []).map((item, index) => <div className="toc-row" key={item.id || `issue-${index}`}>
      <span>{String(index + 1).padStart(2, "0")}</span><div>{item.article_href && !preview ? <Link href={item.article_href}><strong>{item.title}</strong></Link> : <strong>{item.title}</strong>}{item.author_display ? <p>{item.author_display}</p> : null}</div><small>{item.page_range}</small>
    </div>)}
    {(work.outline ?? []).map((item, index) => preview ? <div className="toc-row" key={`${item.index}-${item.chapter_title}`}><span>{String(index + 1).padStart(2, "0")}</span><strong>{item.chapter_title}</strong><small>{item.printed_label || item.index}</small></div> : <Link className="toc-row" href={`${readerHref}?page=${item.index}`} key={`${item.index}-${item.chapter_title}`}><span>{String(index + 1).padStart(2, "0")}</span><strong>{item.chapter_title}</strong><small>{item.printed_label || item.index}</small></Link>)}
    {!work.outline?.length && !work.journalContents?.length ? <p className="empty-state">{work.kind === "整期期刊" ? "本期目录尚待补充。" : "该 PDF 没有可识别的目录书签。"}</p> : null}
  </>;
  const panels = [
    ...(["publication", "contents"].includes(presentation) ? [{ id: "summary", label: "内容简介", content: <>{presentation === "contents" ? <h2>内容简介</h2> : null}<p>{work.summary}</p></> }] : []),
    ...(presentation === "contents" ? [{ id: "authors", label: "作者介绍", content: authorIntroduction }] : []),
    { id: "outline", label: "目录", content: outline },
    ...(presentation === "reading" ? [{ id: "authors", label: "作者简介", content: authorIntroduction }] : []),
    { id: "edition", label: "版本信息", content: <><dl className={styles.metadata}>{[["出版信息", publication], ["文献类型", work.kind], ["语言", languageLabel], ["ISBN", work.isbn], ["页数", work.pages || ""]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || "—"}</dd></div>)}</dl>{!preview && work.editionId ? <WorkCitationPanel editionId={work.editionId}/> : null}</> },
    { id: "related", label: presentation === "contents" || presentation === "reading" ? "相关图书" : presentation === "bibliography" ? "相关推荐" : "相关书目", content: preview ? null : <div className="four-book-grid">{relatedWorks.slice(0, 4).map(item => <BookCard work={item} key={item.id}/>)}{!relatedWorks.length ? <p className="empty-state">尚无依据已确认流派或主题关联的其他公开馆藏。</p> : null}</div> },
    ...(presentation === "publication" ? [{ id: "topics", label: "相关主题", content: renderTags((work.topics ?? []).map(item => item.name)) }] : []),
  ];
  const curatedGroups = [
    { key: "core_viewpoint", title: "核心观点", claims: work.curatedClaims?.core_viewpoint ?? [] },
    { key: "major_criticism", title: "主要批评", claims: work.curatedClaims?.major_criticism ?? [] },
    { key: "major_response", title: "主要回应", claims: work.curatedClaims?.major_response ?? [] },
  ] as const;

  return (
    <>
      <div className={`page-shell work-detail ${styles.detail}`}>
        {presentation !== "contents" && presentation !== "bibliography" ? <p className={`breadcrumbs ${styles.breadcrumbs}`}>
          {preview ? <>首页 / 馆藏 / {work.title}</> : <><Link href="/">首页</Link> / <Link href="/explore">馆藏</Link> / {work.title}</>}
        </p> : null}
        <WorkDetailTabs presentation={presentation} panels={panels}
          aside={presentation === "publication" ? <><h2>关于本书</h2><WorkDetailSummary summary={work.summary}/><h2>相关主题</h2>{renderTags(tags)}</> : presentation === "reading" ? <><h2>在本馆阅读</h2>{actions}</> : undefined}
          introduction={presentation === "reading" ? <><h2>简介</h2><p className="work-summary">{work.summary}</p></> : undefined}>
          <section className={`work-hero ${styles.hero}`}>
            <div className={styles.cover}>{work.coverImage ? <BookCover work={work} size="large"/> : <div className={styles.emptyCover} aria-label="封面待补"/>}</div>
            <div className={styles.bibliography}>
              <h1>{work.title}</h1>
              {work.subtitle ? <p className="work-subtitle">{work.subtitle}</p> : null}
              {work.originalTitle && presentation !== "bibliography" ? <p className="original-title">{work.originalTitle}</p> : null}
              {primaryAuthor && !preview ? <Link className="work-author-link" href={`/scholars/${primaryAuthor.slug}`}>{work.author}<ArrowRight size={15}/></Link> : <p className="work-author-link">{work.author}</p>}
              {presentation === "bibliography" && work.authors?.some(author => author.originalName) ? <p className={styles.authorOriginal}>{work.authors.map(author => author.originalName).filter(Boolean).join("、")}</p> : null}
              {work.translators?.length && presentation === "publication" ? <p className="work-translators">{work.translators.map((translator, index) => <span key={`${translator.name}-${index}`}>{index ? "、" : ""}{translator.slug && !preview ? <Link href={`/scholars/${translator.slug}`}>{translator.name}</Link> : translator.name}</span>)} 译</p> : null}
              {presentation !== "publication" ? <p className={styles.publication}>{publication}</p> : null}
              {presentation !== "bibliography" ? <dl className={styles.metadata}>{metadata.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || "—"}</dd></div>)}</dl> : null}
              {presentation === "publication" || presentation === "bibliography" || !preview && presentation === "contents" ? actions : null}
              {presentation === "bibliography" ? <section className={styles.introduction}><h2>简介</h2><p className="work-summary">{work.summary}</p></section> : null}
            </div>
          </section>
        </WorkDetailTabs>
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
      </div>
      {preview ? <div inert>{footer}</div> : footer}
    </>
  );
}
