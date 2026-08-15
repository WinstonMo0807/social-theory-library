import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight, Eye } from "lucide-react";
import { AssetDownloadButton } from "@/components/asset-download-button";
import { SaveWorkButton } from "@/components/save-work-button";
import { WorkCitationPanel } from "@/components/work-citation-panel";
import { SiteFooter } from "@/components/site-footer";
import { BookCard, BookCover, SectionHeading, TagList } from "@/components/ui";
import { loadWork, loadWorks } from "@/lib/server-api";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const work = await loadWork(slug);
  return { title: work?.title ?? "文献详情" };
}

export default async function WorkDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [work, works] = await Promise.all([loadWork(slug), loadWorks()]);
  if (!work) notFound();
  const primaryAuthor = work.authors?.find((author) => author.slug);
  const tags = [
    ...(work.theories ?? []).map((item) => item.name),
    ...(work.topics ?? []).map((item) => item.name),
  ];
  const relatedWorks = works.filter((item) => (
    item.id !== work.id
    && (
      (item.theories ?? []).some((candidate) => (work.theories ?? []).some((current) => current.slug === candidate.slug))
      || (item.topics ?? []).some((candidate) => (work.topics ?? []).some((current) => current.slug === candidate.slug))
    )
  ));
  const languageLabel = ({
    "zh-CN": "简体中文",
    "zh-TW": "繁体中文",
    en: "英文",
  } as Record<string, string>)[work.language ?? "zh-CN"] ?? work.language;
  return (
    <>
      <div className="page-shell work-detail">
        <p className="breadcrumbs"><Link href="/">首页</Link> / <Link href="/explore">馆藏</Link> / {work.title}</p>
        <section className="work-hero">
          <BookCover work={work} size="large" />
          <div>
            <p className="eyebrow">{work.kind} · {work.school}</p>
            <h1>{work.title}</h1>
            {work.originalTitle ? <p className="original-title">{work.originalTitle}</p> : null}
            {primaryAuthor ? (
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
              <div><dt>文本状态</dt><dd>全文可检索</dd></div>
              <div><dt>语言</dt><dd>{languageLabel}</dd></div>
            </dl>
            <Link className="button" href={`/reader/${work.id}`}><Eye size={16} /> 在线阅读</Link>
            <AssetDownloadButton assetId={work.id} />
            <div className="button secondary work-save-control"><SaveWorkButton workId={work.workId} /></div>
          </aside>
        </section>

        <div className="work-body">
          <section className="panel">
            <SectionHeading title="内容简介" />
            <p>{work.summary} 馆藏版本已经建立逐页规范文本。全文搜索结果、文档内搜索、干净复制和页码引用均使用同一份页级记录。</p>
            <h2>目录</h2>
            {(work.outline ?? []).map((item, index) => (
              <Link className="toc-row" href={`/reader/${work.id}?page=${item.index}`} key={`${item.index}-${item.chapter_title}`}>
                <span>{String(index + 1).padStart(2, "0")}</span><strong>{item.chapter_title}</strong><small>{item.printed_label || item.index}</small>
              </Link>
            ))}
            {!work.outline?.length ? <p className="empty-state">该 PDF 没有可识别的目录书签。</p> : null}
          </section>
          <WorkCitationPanel editionId={work.editionId} />
        </div>
        {work.theoryAssociations?.length ? (
          <section className="detail-section work-theory-associations">
            <SectionHeading title="理论关联" />
            <div className="work-theory-association-list">
              {work.theoryAssociations.map((association) => (
                <article key={association.id}>
                  <header>
                    <div>
                      <span>{association.role_label}</span>
                      <h2><Link href={`/theories/nodes/${association.node.slug}`}>{association.node.name}</Link></h2>
                      {association.node.foreign_name ? <p>{association.node.foreign_name}</p> : null}
                    </div>
                    <small>人工审核通过</small>
                  </header>
                  {association.evidence.length ? (
                    <div className="work-theory-evidence-list">
                      {association.evidence.slice(0, 3).map((evidence) => (
                        <div key={evidence.id}>
                          <p>{evidence.quote}</p>
                          <Link href={evidence.reader_href}>
                            PDF 第 {evidence.page_number}{evidence.page_end && evidence.page_end !== evidence.page_number ? `–${evidence.page_end}` : ""} 页
                            <ArrowRight size={14} />
                          </Link>
                        </div>
                      ))}
                    </div>
                  ) : <p className="empty-state">该关系已确认，页码证据仍待补充。</p>}
                </article>
              ))}
            </div>
          </section>
        ) : null}
        <section className="detail-section">
          <SectionHeading title="相关馆藏" href={`/explore?q=${work.school}`} />
          <div className="four-book-grid">
            {relatedWorks.slice(0, 4).map((item) => <BookCard work={item} key={item.id} />)}
            {!relatedWorks.length ? <p className="empty-state">尚无依据已确认流派或主题关联的其他公开馆藏。</p> : null}
          </div>
        </section>
      </div>
      <SiteFooter />
    </>
  );
}
