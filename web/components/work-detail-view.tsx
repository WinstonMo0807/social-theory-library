"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, BookOpenText, ChevronDown, Copy, ExternalLink, Eye, Info, Share2, ShieldCheck, X } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { AssetDownloadButton } from "./asset-download-button";
import { AddWorkToListButton } from "./add-work-to-list-button";
import { SaveWorkButton } from "./save-work-button";
import { SharedCitationButton } from "./shared-citation-overlay";
import { WorkCitationPanel } from "./work-citation-panel";
import { MediaPlacement } from "./media-placement";
import { WorkDetailEvidence } from "./work-detail-evidence";
import { BookCard, BookCover } from "./ui";
import { Dialog } from "./ui/dialog";
import { Tabs } from "./ui/tabs";
import type { Work, WorkVersion } from "@/lib/data";
import styles from "./work-detail-view.module.css";

type Props = {
  work: Work; relatedWorks?: Work[]; footer: ReactNode;
  preview?: { publicationState: string; pdfPreviewUrl: string; returnHref: string; draftRevision?: { revision: number; changedFields: string[]; hasConflict: boolean } | null };
};
const mobileQuery = "(max-width: 680px)";
const subscribeMobile = (listener: () => void) => {
  const media = window.matchMedia(mobileQuery);
  media.addEventListener("change", listener);
  return () => media.removeEventListener("change", listener);
};
const mobileSnapshot = () => window.matchMedia(mobileQuery).matches;
const serverSnapshot = () => false;
const languageLabel = (value?: string) => ({ "zh-CN": "简体中文", "zh-TW": "繁体中文", zh: "中文", en: "英文", fr: "法文", de: "德文", ja: "日文" }[value ?? ""] || value || "待补充");
const versionHref = (version: WorkVersion) => `/works/${encodeURIComponent(version.public_slug || version.id)}`;
const accessLabel = (version: WorkVersion) => version.readable_asset ? "可在线阅读" : ({ registered: "限登录读者", restricted: "访问受限", unavailable: "暂不可用" }[version.access_state || ""] || "仅书目");
const versionName = (version: WorkVersion) => version.version_label || `${version.publication_year || "年份待补"} · ${languageLabel(version.language)}`;

export function WorkDetailView(props: Props) {
  return <WorkDetailContent key={`${props.work.editionId || props.work.slug}:${props.preview?.draftRevision?.revision || ""}`} {...props} />;
}

function WorkDetailContent({ work, relatedWorks = [], preview, footer }: Props) {
  const mobile = useSyncExternalStore(subscribeMobile, mobileSnapshot, serverSnapshot);
  const article = work.kind === "期刊论文";
  const [active, setActive] = useState("versions");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({ versions: true });
  const [coverOpen, setCoverOpen] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 760px)");
    const close = () => setCoverOpen(false);
    media.addEventListener("change", close);
    return () => media.removeEventListener("change", close);
  }, []);
  const coverClose = useRef<HTMLButtonElement>(null);
  const version = work.version;
  const versions = work.versions?.length ? work.versions : version ? [version] : [];
  const readable = Boolean(!preview && work.readerHref);
  const translators = version?.contributors.filter(row => row.role === "translator" && row.scope?.kind !== "chapter").map(row => row.person.preferred_name).join("、");
  const tags = [...(work.theories ?? []).map(row => ({ ...row, href: `/theories/nodes/${row.slug}` })), ...(work.topics ?? []).map(row => ({ ...row, href: `/topics/${row.slug}` }))];
  const missing = [!work.author || work.author === "作者待补" ? "作者" : "", !version?.publication_year ? "出版年" : "", !version?.publisher ? "出版机构" : ""].filter(Boolean);
  const relations = work.relations;
  const primaryScholar = relations?.scholars.find(row => row.roles.includes("author") && version?.contributors.some(person => person.person.id === row.person.id && person.role === "author" && person.scope?.kind !== "chapter"));
  const related = work.relatedWorks ?? relatedWorks;
  useEffect(() => {
    const followHash = () => { const section = window.location.hash.slice(1); if (["citation", "scholars"].includes(section)) { setActive(article && section === "scholars" ? "related" : section); setExpanded(current => ({ ...current, [section]: true })); } };
    const timer = window.setTimeout(followHash, 0);
    window.addEventListener("hashchange", followHash);
    return () => { window.clearTimeout(timer); window.removeEventListener("hashchange", followHash); };
  }, [article]);

  const baseSections = [
    { key: "versions", title: article ? "版本与获取" : "版本信息", content: <div className={article && relations?.journal_issues.length ? styles.issueLayout : undefined}><VersionTable versions={versions} selectedId={work.editionId} preview={Boolean(preview)} />{article ? <JournalIssues work={work} preview={Boolean(preview)} /> : null}</div> },
    { key: "chapters", title: article ? "章节与内容" : "章节预览", content: <WorkContents work={work} preview={Boolean(preview)} /> },
    { key: "scholars", title: "相关学者", content: <><ContributorRoles version={version} preview={Boolean(preview)} /><RelatedSidebar work={work} preview={Boolean(preview)} /></> },
    { key: "related", title: "相关著作", content: <div className={styles.relatedBooks}>{related.length ? related.map(item => <BookCard key={item.workId || item.id} work={item} />) : <Empty>尚无已确认的相关公开著作。</Empty>}</div> },
    { key: "concepts", title: "相关概念", content: <div className={styles.linkRows}>{relations?.concepts.length ? relations.concepts.map(row => <RelationLink key={row.id} href={`/theories/nodes/${row.slug}`} title={row.name} summary={row.summary} preview={Boolean(preview)} />) : <Empty>尚无已确认的公开概念关联。</Empty>}</div> },
    { key: "topics", title: "相关专题", content: <RelationCards work={work} kind="curations" preview={Boolean(preview)} /> },
    { key: "paths", title: "学习路径", content: <RelationCards work={work} kind="reading_paths" preview={Boolean(preview)} /> },
    { key: "citation", title: article ? "摘要与引用" : "研究资料", content: <><WorkDetailEvidence work={work} preview={Boolean(preview)} />{preview ? <Empty>草稿预览不执行公共引用、收藏和下载。</Empty> : work.editionId ? <WorkCitationPanel editionId={work.editionId} /> : <Empty>当前尚无可引用的公开版本。</Empty>}</> },
  ];
  const section = (key: string) => baseSections.find(row => row.key === key)!;
  const contributorDetails = <details className={styles.contributorDetails}><summary>版本责任者</summary><ContributorRoles version={version} preview={Boolean(preview)} /></details>;
  const sections = article ? [section("versions"), section("chapters"), { ...section("citation"), content: <>{section("citation").content}{!preview ? <ShareWork title={work.title} slug={work.slug} /> : null}</> },
    { key: "related", title: "相关内容", content: <>{contributorDetails}<RelatedSidebar work={work} preview={Boolean(preview)} />{section("related").content}{section("topics").content}{section("paths").content}</> },
    { key: "references", title: "参考文献", content: <WorkReferences work={work} preview={Boolean(preview)} /> },
  ] : baseSections.filter(row => row.key !== "scholars" || mobile || active === "scholars").map(row => row.key === "citation" ? { ...row, content: <>{row.content}{contributorDetails}</> } : row);
  const mobileSections = [{ key: "summary", title: "内容简介", content: <Summary text={work.summary} /> }, ...sections];
  return <>
    <div className={`page-shell work-detail ${styles.page} ${article ? styles.article : ""}`} data-work-kind={article ? "article" : "book"} data-work-readable={readable}>
      {preview ? <div className="admin-page-preview-banner" role="status"><ShieldCheck size={16} /><strong>草稿预览</strong><span>{preview.draftRevision ? `已保存草稿第 ${preview.draftRevision.revision} 版` : "当前编目草稿"}{preview.draftRevision?.hasConflict ? "，存在待处理冲突" : "，尚未向读者公开"}</span><Link href={preview.returnHref}>返回编辑</Link></div> : null}
      <nav className={`breadcrumbs ${styles.breadcrumbs}`} aria-label="当前位置">{preview ? <span>前台页面效果 / {work.title}</span> : <><Link href="/">首页</Link><span>›</span><Link href="/explore">探索</Link><span>›</span><span>{work.kind}</span><span>›</span><span aria-current="page">{work.title}</span></>}</nav>
      <section className={`work-hero ${styles.hero}`}>
        <div className={styles.coverColumn}>{work.coverImage ? <BookCover work={work} size="large" placement="detail" /> : <div className={styles.noCover}><BookOpenText size={34} strokeWidth={1} /><span>暂无封面</span></div>}{work.coverImage ? <MediaPlacement uses={work.coverDisplayUses} placement="detail"><button className={styles.coverPreview} type="button" onClick={() => setCoverOpen(true)}><Eye size={14} />预览封面</button></MediaPlacement> : null}</div>
        <div className={styles.identity}>
          <span className={styles.kind}>{article ? "期刊文章" : work.kind}</span><h1>{work.title}</h1>
          {work.subtitle ? <p className={styles.subtitle}>{work.subtitle}</p> : null}
          {work.originalTitle && work.originalTitle !== work.title ? <p className={styles.original}>{work.originalTitle}</p> : null}
          <div className={`work-author-link ${styles.authorLine}`}>{article && primaryScholar?.person.portrait ? <MediaPlacement uses={primaryScholar.person.portrait_media?.display_uses}><img src={primaryScholar.person.portrait} alt="" width={48} height={48} /></MediaPlacement> : null}{work.authors?.length ? work.authors.map((author, index) => <span key={`${author.name}-${index}`}>{!preview && author.slug ? <Link href={`/scholars/${author.slug}`}>{author.name}<ArrowRight size={13} /></Link> : author.name}</span>) : <span>{work.author}</span>}{article && primaryScholar ? <small>{[primaryScholar.person.original_name, primaryScholar.person.birth_year ? `${primaryScholar.person.birth_year}—${primaryScholar.person.death_year || ""}` : "", primaryScholar.short_description].filter(Boolean).join(" · ")}</small> : null}</div>
          {!article ? <div className={styles.metadataColumns}>{work.originalTitle || work.firstPublicationDate || work.originalLanguage ? <section><h2>原作信息</h2><Facts rows={[["原名", work.originalTitle], ["原作语言", work.originalLanguage ? languageLabel(work.originalLanguage) : ""], ["首次出版", work.firstPublicationDate]]} /></section> : null}<section><h2>{version?.version_label || "当前版本"}</h2><Facts rows={[["作者", work.author], ...(translators ? [["译者", translators] as [string, string]] : []), ["出版社", version?.publisher], ["出版年", version?.publication_year], ["页数", work.pages > 0 ? `${work.pages} 页` : version?.extent], ["语言", languageLabel(work.language)]]} /></section></div> : <Summary text={work.summary} />}
        </div>
        <aside className={styles.sidebar}>
          <div className={styles.actions}>{preview ? preview.pdfPreviewUrl ? <a className={styles.primaryAction} href={preview.pdfPreviewUrl} target="_blank" rel="noreferrer"><Eye size={17} />后台 PDF<ArrowRight size={16} /></a> : <span className={styles.unavailable}>PDF 尚未就绪</span> : readable ? <Link className={styles.primaryAction} href={work.readerHref!}><BookOpen size={18} />{article ? "在线阅读" : "开始阅读"}{version?.version_label ? <small>（{version.version_label}）</small> : null}<ArrowRight size={17} /></Link> : work.workId ? <div className={styles.primaryList}><AddWorkToListButton workId={work.workId} title={work.title}><BookOpen size={18} />加入书单<ArrowRight size={17} /></AddWorkToListButton></div> : null}
            {!preview ? <div className={styles.actionGrid}><SaveWorkButton workId={work.workId} icon={readable && !article ? "star" : "bookmark"} />{readable && work.workId ? <AddWorkToListButton workId={work.workId} title={work.title} /> : null}{!article && !readable && work.editionId ? <SharedCitationButton editionId={work.editionId}>引用</SharedCitationButton> : null}{!article ? <ShareWork title={work.title} slug={work.slug} /> : null}</div> : null}
          </div>
          {article ? <Facts rows={[["刊名", version?.journal_title], ["卷期", [version?.volume, version?.issue].filter(Boolean).join(" · ")], ["页码", version?.page_range], ["出版年", version?.publication_year], ["DOI", version?.doi ? <a href={`https://doi.org/${encodeURIComponent(version.doi)}`} target="_blank" rel="noreferrer">{version.doi}<ExternalLink size={12} /></a> : ""], ["语言", languageLabel(work.language)], ["材料类型", work.kind]]} /> : <RelatedSidebar work={work} preview={Boolean(preview)} />}
        </aside>
        {tags.length ? <div className={styles.tags}>{tags.map(tag => preview ? <span key={tag.href}>{tag.name}</span> : <Link key={tag.href} href={tag.href}>{tag.name}</Link>)}</div> : null}
        {!article ? <div className={`work-summary ${styles.summary}`}><h2>内容简介</h2><Summary text={work.summary} /></div> : null}
        {!preview && (!readable || missing.length > 0) ? <div className={styles.sourceNotice}><Info size={16} /><p>{!readable ? "当前版本暂无可在线阅读的公开文件，可查看书目信息及其他版本。" : ""}{missing.length > 0 ? ` ${missing.join("、")}信息尚待补充。` : ""}</p></div> : null}
      </section>
      <div className={`work-body ${styles.body}`}>
        {mobile && !article ? <div className={styles.accordions}>{mobileSections.map(row => <details key={row.key} open={Boolean(expanded[row.key])} onToggle={event => { const open = event.currentTarget.open; setExpanded(current => current[row.key] === open ? current : { ...current, [row.key]: open }); }}><summary>{row.title}<ChevronDown size={16} /></summary>{expanded[row.key] ? <div id={`work-section-${row.key}`}>{row.content}</div> : null}</details>)}</div> : <><Tabs className={styles.tabs} aria-label="作品详情" items={sections.map(row => ({ value: row.key, label: row.title, id: `work-tab-${row.key}`, panelId: `work-section-${row.key}` }))} value={active} onChange={setActive} />{sections.map(row => <section className={styles.tabPanel} id={`work-section-${row.key}`} role="tabpanel" aria-labelledby={`work-tab-${row.key}`} tabIndex={0} hidden={active !== row.key} key={row.key}>{active === row.key ? <><h2>{row.title}</h2>{row.content}</> : null}</section>)}</>}
      </div>
      {article ? <div className={styles.articleRelated}><RelatedSidebar work={work} preview={Boolean(preview)} /><section><h2>相关专题</h2><RelationCards work={work} kind="curations" preview={Boolean(preview)} /></section><section><h2>学习路径</h2><RelationCards work={work} kind="reading_paths" preview={Boolean(preview)} /></section></div> : null}
      {preview ? <p className={styles.previewNote}>当前展示编目草稿。公共阅读、收藏、书单和引用须在发布后按实际权限开放。</p> : null}
    </div>
    {coverOpen && work.coverImage ? <Dialog open aria-label="封面预览" className={styles.coverDialog} onRequestClose={() => setCoverOpen(false)} initialFocusRef={coverClose}><header><h2>{work.title}</h2><button type="button" ref={coverClose} onClick={() => setCoverOpen(false)} aria-label="关闭封面预览"><X size={20} /></button></header><img src={work.coverImage} alt={work.coverAlt || `${work.title}封面`} /></Dialog> : null}
    {footer}
  </>;
}

function Empty({ children }: { children: ReactNode }) { return <p className={styles.empty}>{children}</p>; }
function Facts({ rows }: { rows: [string, ReactNode][] }) { return <dl className={styles.facts}>{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || "待补充"}</dd></div>)}</dl>; }
function Summary({ text }: { text: string }) { return <details className={styles.summaryDisclosure}><summary><span>{text}</span><small>展开 / 收起<ChevronDown size={12} /></small></summary></details>; }
function ShareWork({ title, slug }: { title: string; slug: string }) {
  const [open, setOpen] = useState(false); const [url, setUrl] = useState(""); const [message, setMessage] = useState(""); const input = useRef<HTMLInputElement>(null);
  return <><button type="button" onClick={() => { setUrl(new URL(`/works/${encodeURIComponent(slug)}`, window.location.origin).href); setMessage(""); setOpen(true); }}><Share2 size={15} />分享</button><Dialog open={open} onRequestClose={() => setOpen(false)} className={styles.shareDialog} aria-label="分享公开作品链接" initialFocusRef={input}><header><h2>分享作品</h2><button type="button" onClick={() => setOpen(false)} aria-label="关闭分享"><X size={20} /></button></header><p>{title}</p><label>公开作品链接<input ref={input} readOnly value={url} onFocus={event => event.currentTarget.select()} /></label><button className={styles.primaryAction} type="button" onClick={async () => { try { await navigator.clipboard.writeText(url); setMessage("链接已复制。"); } catch { input.current?.focus(); input.current?.select(); setMessage("浏览器未允许复制，请手动复制选中的链接。"); } }}><Copy size={15} />复制链接</button><p role="status">{message || "链接只包含当前公开版本，不包含你的收藏、笔记或阅读记录。"}</p></Dialog></>;
}
function VersionTable({ versions, selectedId, preview }: { versions: WorkVersion[]; selectedId?: string; preview: boolean }) {
  if (!versions.length) return <Empty>版本信息尚待补充。</Empty>;
  return <div><p className={styles.sectionIntro}>选择版本查看对应书目与原文。</p><div className={styles.versionTable}><table><thead><tr><th scope="col">版本</th><th scope="col">出版信息</th><th scope="col">语言</th><th scope="col">ISBN / DOI</th><th scope="col">获取状态</th><th scope="col">操作</th></tr></thead><tbody>{versions.map(version => {
    const selected = version.id === selectedId; const asset = version.readable_asset;
    return <tr key={version.id} className={selected ? styles.selectedVersion : undefined}><th scope="row">{preview ? <strong>{versionName(version)}</strong> : <Link className={styles.versionIdentity} href={versionHref(version)} aria-current={selected ? "page" : undefined}><span className={`${styles.radioMark} ${selected ? styles.checked : ""}`} aria-hidden="true" />{versionName(version)}<span className="sr-only">{selected ? "，当前版本" : "，查看版本信息"}</span></Link>}{version.contributors.filter(row => row.role === "translator" && row.scope?.kind !== "chapter").map(row => <small key={`${row.person.id}-${row.role}`}>{row.person.preferred_name} 译</small>)}</th><td>{version.publisher || "出版机构待补"}<small>{version.publication_date || version.publication_year || "出版年待补"}</small></td><td>{languageLabel(version.language)}</td><td className={styles.identifier}>{version.isbn13 || version.isbn10 || version.isbn || version.doi || "—"}</td><td><span className={asset ? styles.available : styles.metadataOnly}>{asset ? <><i />可在线阅读</> : accessLabel(version)}</span></td><td><div className={styles.versionActions}>{preview ? <span>草稿预览</span> : <>{asset ? <Link className={selected ? styles.primaryAction : styles.secondaryAction} href={`/reader/${asset.id}`}><BookOpen size={14} />开始阅读<ArrowRight size={14} /></Link> : <Link className={styles.secondaryAction} href={versionHref(version)}>查看版本信息<ArrowRight size={14} /></Link>}<details><summary aria-label={`${versionName(version)}的更多操作`}>···</summary><div>{asset ? <AssetDownloadButton assetId={asset.id} /> : null}<SharedCitationButton editionId={version.id}>引用此版本</SharedCitationButton><Link href={versionHref(version)}>版本详情</Link></div></details></>}</div></td></tr>;
  })}</tbody></table></div></div>;
}
function WorkContents({ work, preview }: { work: Work; preview: boolean }) {
  const outline = work.outline ?? []; const issue = work.journalContents ?? [];
  return <div><p className={styles.sectionIntro}>{work.version ? versionName(work.version) : "当前版本"}{outline.length ? ` · ${outline.length} 条目录` : ""}</p>{issue.map((item, index) => <div className={styles.contentsRow} key={item.id || index}><span>{String(index + 1).padStart(2, "0")}</span><div>{!preview && item.article_href ? <Link href={item.article_href}>{item.title}</Link> : <strong>{item.title}</strong>}{item.author_display ? <small>{item.author_display}</small> : null}</div><small>{item.page_range}</small></div>)}{outline.map((item, index) => <div className={styles.contentsRow} key={`${item.index}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span>{!preview && work.readerHref ? <Link href={`${work.readerHref}?page=${item.index}`}>{item.chapter_title}<ArrowRight size={14} /></Link> : <strong>{item.chapter_title}</strong>}<small>{item.printed_label ? `p. ${item.printed_label}` : `PDF ${item.index}`}</small></div>)}{!outline.length && !issue.length ? <Empty>{work.readerHref ? "当前版本尚无可用的章节目录。可直接打开原文阅读。" : "当前版本没有可在线阅读的公开文件，暂不提供章节预览。"}</Empty> : null}</div>;
}
function WorkReferences({ work, preview }: { work: Work; preview: boolean }) {
  const entries = (work.outline || []).filter(row => /参考文献|引用文献|bibliography|references/i.test(row.chapter_title));
  return <div><p className={styles.sectionIntro}>以下入口来自当前版本的目录，直接回到原文参考文献。</p>{entries.length ? entries.map((row, index) => <div className={styles.contentsRow} key={`${row.index}-${index}`}><span>{index + 1}</span>{!preview && work.readerHref ? <Link href={`${work.readerHref}?page=${row.index}`}>{row.chapter_title}<ArrowRight size={14} /></Link> : <strong>{row.chapter_title}</strong>}<small>{row.printed_label ? `p. ${row.printed_label}` : `PDF ${row.index}`}</small></div>) : <Empty>当前目录尚未标出参考文献。{!preview && work.readerHref ? <Link href={work.readerHref}>打开原文核对 <ArrowRight size={14} /></Link> : "可阅读文件就绪后，可在原文中核对。"}</Empty>}</div>;
}
function RelationLink({ href, title, summary, image, uses, preview }: { href: string; title: string; summary?: string; image?: string; uses?: Work["coverDisplayUses"]; preview: boolean }) {
  const content = <>{image ? <MediaPlacement uses={uses}><img src={image} alt="" loading="lazy" /></MediaPlacement> : null}<span><strong>{title}</strong>{summary ? <small>{summary}</small> : null}</span><ArrowRight size={15} /></>;
  return preview ? <div className={styles.relationLink}>{content}</div> : <Link className={styles.relationLink} href={href}>{content}</Link>;
}
function RelatedSidebar({ work, preview }: { work: Work; preview: boolean }) {
  const relations = work.relations;
  const excerpt = work.curatedClaims?.core_viewpoint.flatMap(row => row.evidence).find(row => row.source.edition_id === work.editionId);
  return <div className={styles.relatedSidebar}>{excerpt && !preview ? <blockquote className={styles.excerpt}><p>{excerpt.text}</p><Link href={excerpt.reader_url}>查看原文 · {excerpt.locator.printed_page_label ? `p. ${excerpt.locator.printed_page_label}` : `PDF ${excerpt.locator.page}`}<ArrowRight size={13} /></Link></blockquote> : null}<section><h2>相关学者</h2>{relations?.scholars.length ? relations.scholars.map(row => <RelationLink key={row.id} href={`/scholars/${row.slug}`} title={row.person.preferred_name} summary={row.person.original_name || row.short_description} image={row.person.portrait || undefined} uses={row.person.portrait_media?.display_uses} preview={preview} />) : <Empty>尚无公开学者资料。</Empty>}</section><section><h2>相关主题</h2><div className={styles.tags}>{work.topics?.length ? work.topics.map(topic => preview ? <span key={topic.slug}>{topic.name}</span> : <Link key={topic.slug} href={`/topics/${topic.slug}`}>{topic.name}</Link>) : <Empty>尚无已确认主题。</Empty>}</div></section>{relations?.concepts.length ? <section><h2>相关概念</h2>{relations.concepts.map(row => <RelationLink key={row.id} href={`/theories/nodes/${row.slug}`} title={row.name} preview={preview} />)}</section> : null}</div>;
}
function RelationCards({ work, kind, preview }: { work: Work; kind: "curations" | "reading_paths"; preview: boolean }) {
  const rows = work.relations?.[kind] ?? [];
  return <div className={styles.linkRows}>{rows.length ? rows.map(row => <RelationLink key={row.id} href={kind === "curations" ? `/recommendations/${row.slug}` : `/theories/reading-paths/${row.slug}`} title={row.title} summary={"summary" in row ? row.summary : row.introduction} image={row.cover_url || undefined} uses={row.cover_media?.display_uses} preview={preview} />) : <Empty>{kind === "curations" ? "尚无与该作品关联的公开专题。" : "尚无与该作品关联的公开学习路径。"}</Empty>}</div>;
}
function JournalIssues({ work, preview }: { work: Work; preview: boolean }) {
  const issues = work.relations?.journal_issues ?? [];
  if (!issues.length) return null;
  return <aside className={styles.journalIssues}><h2>本期目录</h2>{issues.map(issue => <section key={`${issue.id}-${issue.edition.id}`}><RelationLink href={`/works/${issue.slug}`} title={issue.title} summary={[issue.edition.volume, issue.edition.issue, issue.edition.publication_year].filter(Boolean).join(" · ")} image={issue.cover_url || undefined} uses={issue.cover_media?.display_uses} preview={preview} />{issue.contents.map((row, index) => <div className={row.article_work_id === work.workId ? styles.currentArticle : undefined} key={row.id || index}>{row.article_href && !preview ? <Link href={row.article_href}>{row.title}</Link> : <strong>{row.title}</strong>}<small>{row.author_display}{row.page_range ? ` · ${row.page_range}` : ""}</small></div>)}</section>)}</aside>;
}


function ContributorRoles({ version, preview }: { version?: WorkVersion; preview: boolean }) {
  const roles: Record<string, string> = { author: "作者", chief_editor: "主编", editor: "编者", translator: "译者", annotator: "校注", photographer: "摄影", advisor: "导师", subject: "研究对象", other: "其他贡献者" };
  return <section className={styles.linkRows} aria-label="当前出版版本的责任者"><p>以下职责只属于当前出版版本。章节责任单独注明范围，不等同于整部著作的作者。</p>{version?.contributors.length ? version.contributors.map(row => <div className={styles.contentsRow} key={`${row.person.id}:${row.role}`}><span>{row.scope?.kind === "chapter" ? "章节" : ""}{roles[row.role] || row.role}</span><div>{!preview && row.person.scholar_slug ? <Link href={`/scholars/${encodeURIComponent(row.person.scholar_slug)}`}>{row.person.preferred_name}</Link> : <strong>{row.person.preferred_name}</strong>}{row.person.original_name ? <small>{row.person.original_name}</small> : null}{row.scope?.kind === "chapter" ? row.scope.status === "available" ? <ul>{row.scope.chapters.map(chapter => <li key={`${chapter.outline_revision_id}:${chapter.outline_node_id}`}>{!preview && chapter.reader_href ? <Link href={chapter.reader_href}>{chapter.title}</Link> : chapter.title} · PDF {chapter.page_start}–{chapter.page_end}</li>)}</ul> : <p>{row.scope.notice || "章节来源当前不可用。"}</p> : null}</div></div>) : <Empty>此版本尚无确认的责任者资料。</Empty>}</section>;
}
