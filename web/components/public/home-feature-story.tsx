"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState, type CSSProperties } from "react";
import { ArrowRight, BookOpen, Check, FileText, FolderOpen, NotebookPen, Pause, Play, Plus, RotateCcw, Search } from "lucide-react";
import { BrandImage } from "@/components/brand-image";
import { ScholarPortraitFallback } from "@/components/default-scholar-portrait";
import type { SiteConfig } from "@/lib/site-config";
import styles from "./home-feature-story.module.css";
import { EditorialDiscoveryArt, ScholarDiscoveryArt, TheoryDiscoveryArt } from "./welcome-discovery-art";
import { editorialImageSources } from "@/lib/performance-assets";

import { welcomeContent, type WelcomeConfig, type WelcomeCopy, type WelcomeBook as StoryBook, type WelcomeDiscovery } from "@/lib/welcome";
type BrandConfig = Pick<SiteConfig, "site_name" | "wordmark_lines">;

function TextLines({ highlighted = false }: { highlighted?: boolean }) {
  return <div className={styles.lines} data-highlighted={highlighted || undefined}>
    <i /><i /><i /><i /><i />
  </div>;
}

// These are illustrations of the workflow, never generated quotations or query results.
function StoryScene({ chapter, books }: { chapter: number; books: StoryBook[] }) {
  const book = books[0];
  return <div className={styles.scene} data-scene={chapter} aria-hidden="true">
    {chapter === 0 ? <>
      <div className={styles.question}><Search size={21} strokeWidth={1.5} /><span>社会如何被理解？</span><ArrowRight size={20} /></div>
      <div className={styles.excerptList}>{(books.length ? books.slice(0, 2) : [{ id: "empty", title: "原文节选", author: "" }]).map(entry => <div key={entry.id}><TextLines highlighted /><footer><span>{entry.title}</span><ArrowRight size={17} /></footer></div>)}</div>
    </> : null}
    {chapter === 1 ? <div className={styles.readingDesk}>
      <div className={styles.sourceSlip}><BookOpen size={21} strokeWidth={1.4} /><span>{book?.title || "原文阅读"}</span></div>
      <div className={styles.openPages}><div className={styles.paperPage}><span className={styles.paperHeading}>原文</span><TextLines /><TextLines highlighted /><TextLines /></div><div className={styles.paperPage}><span className={styles.paperHeading}>前后文</span><TextLines /><TextLines /><TextLines /></div></div>
    </div> : null}
    {chapter === 2 ? <div className={styles.citationDesk}>
      <div className={styles.citationSheet}><span className={styles.paperHeading}>引文</span><TextLines highlighted /><TextLines /><span className={styles.citationRule} /></div>
      <div className={styles.sourceCard}><FileText size={23} strokeWidth={1.3} /><strong>{book?.title || "引用来源"}</strong><span>{book?.author}</span><div className={styles.sourceFields}><span>作者与版本</span><span>原文与页码</span><span>引用上下文</span></div></div>
    </div> : null}
    {chapter === 3 ? <div className={styles.continuousResearch}>
      <div className={styles.researchThread}><span>已有研究</span><strong>社会如何被理解？</strong><div className={styles.researchSources}><FileText size={16} />原文<NotebookPen size={16} />笔记</div></div>
      <div className={styles.researchFollowUp}><span>继续追问</span><strong>不同学者如何解释这个问题？</strong><ArrowRight size={19} /></div>
    </div> : null}
  </div>;
}

function DiscoveryView({ kind, discovery, interactive = false }: { kind: "scholars" | "theories" | "topics" | "issue"; discovery: WelcomeDiscovery; interactive?: boolean }) {
  if (kind === "scholars") return <div className={styles.scholarRegister} inert={!interactive}>
    {discovery.scholars.length ? discovery.scholars.map(person => <Link href={`/scholars/${person.slug}`} className={styles.scholarEntry} key={person.slug}>
      <div><strong>{person.name}</strong>{person.originalName !== person.name ? <span>{person.originalName}</span> : null}{!person.portrait && person.years ? <span className={styles.scholarYears}>{person.years}</span> : null}</div>
      {person.portrait ? <img src={person.portrait} srcSet={person.portraitSources?.map(row => `${row.url} ${row.width}w`).join(", ")} sizes="62px" alt="" width={62} height={70} loading="lazy" decoding="async" /> : <ScholarPortraitFallback name={person.name} identity={person.slug} className={styles.scholarFallback}/>}
    </Link>) : <div className={styles.organizingView}><span>生平与著述</span><TextLines /><span>研究问题</span><TextLines /></div>}
    <div className={styles.registerFooter}><span>生平</span><span>著述</span><span>思想与论争</span></div>
  </div>;
  if (kind === "theories") return <div className={styles.theoryRegister} inert={!interactive}>
    <div className={styles.theoryIndex}>{discovery.theories.length ? discovery.theories.map(theory => <Link href={`/theories/nodes/${theory.slug}`} key={theory.slug}><span className={styles.indexMark} /><strong>{theory.name}</strong><ArrowRight size={17} /></Link>) : <div><span className={styles.indexMark} /><strong>理论传统</strong><ArrowRight size={17} /></div>}</div>
    <div className={styles.conceptIndex}><span>核心概念</span><span>代表论著</span><span>不同解释</span></div>
  </div>;
  if (kind === "topics") return <div className={styles.topicIndex} inert={!interactive}>{discovery.topics.length ? discovery.topics.map(topic => <Link href={`/topics/${topic.slug}`} key={topic.slug}><span>{topic.name}</span><ArrowRight size={18} /></Link>) : <div><span>从关心的问题出发</span><ArrowRight size={18} /></div>}</div>;
  return <Link href={discovery.issue?.href || '/recommendations'} className={styles.issueFeature} inert={!interactive}>
    <img src={discovery.issue?.coverImage || "/editorial/generated-20261030/editorial.webp"} {...editorialImageSources(discovery.issue?.coverImage || "/editorial/generated-20261030/editorial.webp", "(max-width: 760px) 100vw, 50vw")} alt="" width={720} height={460} loading="lazy" decoding="async" />
    <div><strong>{discovery.issue?.title || "跟随策划，展开阅读"}</strong>{discovery.issue?.introduction ? <p>{discovery.issue.introduction}</p> : null}<ArrowRight size={21} /></div>
  </Link>;
}

function GrainField() {
  const id = useId().replace(/:/g, "");
  return <svg className={styles.grain} viewBox="0 0 1200 600" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
    <defs><pattern id={id} width="19" height="17" patternUnits="userSpaceOnUse" patternTransform="rotate(12)">
      <circle cx="2" cy="3" r="1.4" /><circle cx="12" cy="6" r=".9" /><circle cx="7" cy="13" r="1.1" /><circle cx="17" cy="15" r=".65" />
    </pattern></defs>
    <g fill={`url(#${id})`}>
      <path d="M-160 70C120-180 310-80 440 110S640 420 910 260 1210 230 1380 500L1300 740C1000 380 940 520 710 540S380 530 250 290 50 120-120 350Z" />
      <path opacity=".45" d="M-110 460C110 200 210 460 420 460S690 40 940 10 1160 110 1330-70L1330 160C1110 420 1000 140 840 230S650 690 380 640 160 370-110 690Z" />
    </g>
  </svg>;
}

function WorkflowDemo({ books, brandConfig, copy, history, discovery }: { books: StoryBook[]; brandConfig: BrandConfig; copy: WelcomeCopy; history: ReturnType<typeof welcomeContent>["texts"]; discovery: WelcomeDiscovery }) {
  const ref = useRef<HTMLElement>(null);
  const [canAnimate, setCanAnimate] = useState(false);
  const [paused, setPaused] = useState(false);
  const [replay, setReplay] = useState(0);
  const book = books[0];

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    let inView = false;
    const update = () => setCanAnimate(inView && !document.hidden && !preference.matches);
    const observer = new IntersectionObserver(([entry]) => { inView = entry.isIntersecting; update(); }, { threshold: .15 });
    observer.observe(node);
    preference.addEventListener("change", update);
    document.addEventListener("visibilitychange", update);
    return () => { observer.disconnect(); preference.removeEventListener("change", update); document.removeEventListener("visibilitychange", update); };
  }, []);

  return <figure ref={ref} className={styles.demo} data-playing={canAnimate && !paused} aria-label="功能演示：认识学者、理论流派、主题与特别策划，提出问题，阅读原文，保存材料与笔记，继续追问">
    <div className={styles.timeline} key={`${copy.id}-${replay}`} aria-hidden="true">
      <GrainField /><div className={styles.demoFrame} />
      <div className={styles.brandPanel}><BrandImage config={brandConfig} alt="" /></div>
      <div className={`${styles.demoPanel} ${styles.historyPanel}`}>
        <div className={styles.historyHeading}><h2>{history.history_title}</h2><div>{history.history_subjects.split("、").filter(Boolean).slice(0, 3).map(subject => <span key={subject}>{subject}</span>)}</div></div>
        <ScholarDiscoveryArt discovery={discovery} />
      </div>
      <div className={`${styles.demoPanel} ${styles.theoryPanel}`}>
        <div className={styles.historyHeading}><h2>{history.discovery_theory_title}</h2></div>
        <TheoryDiscoveryArt discovery={discovery} />
      </div>
      <div className={`${styles.demoPanel} ${styles.discoveryPanel}`}>
        <div className={styles.historyHeading}><h2>{history.discovery_issue_title}</h2></div>
        <EditorialDiscoveryArt discovery={discovery} />
      </div>
      <div className={`${styles.demoPanel} ${styles.askPanel}`}>
        <span className={styles.demoEyebrow}><Search size={17} /> 观点检索</span>
        <div className={styles.typedQuestion} aria-label={copy.question}>{Array.from(copy.question).map((letter, index) => <span aria-hidden="true" key={index} style={{ "--letter-delay": `${index * 0.065}s` } as CSSProperties}>{letter}</span>)}</div>
        <div className={styles.askTools}><span><Plus size={16} /> 选择文献</span><span className={styles.sendArrow}><ArrowRight size={20} /></span></div>
      </div>
      <div className={`${styles.demoPanel} ${styles.workingPanel}`}><span className={styles.spinner} /><span>正在寻找相关原文</span></div>
      <div className={`${styles.demoPanel} ${styles.resultsPanel}`}>
        <div className={styles.demoBar}><Search size={17} /><span>{copy.results}</span><span>原文节选</span></div>
        <div className={styles.demoResults}>{books.length ? books.map((entry, index) => <div className={styles.resultRow} key={entry.id} data-row={index}>
          {entry.coverImage ? <img src={entry.coverImage} srcSet={entry.coverSources?.map(row => `${row.url} ${row.width}w`).join(", ")} sizes="46px" alt="" width={46} height={64} decoding="async" /> : <BookOpen size={28} />}
          <div><strong>{entry.title}</strong><span>{entry.author}</span><TextLines highlighted={index === 0} /></div><ArrowRight size={17} />
        </div>) : <div className={styles.emptyIllustration}><BookOpen size={32} /><span>查找文献与原文</span><TextLines highlighted /></div>}</div>
      </div>
      <div className={`${styles.demoPanel} ${styles.readerPanel}`}>
        <div className={styles.demoBar}><BookOpen size={17} /><span>{book?.title || "原文阅读"}</span><span>{history.history_works}</span></div>
        <div className={styles.readerBody}><div><strong>原文</strong><TextLines /><TextLines highlighted /><TextLines /></div><aside><FileText size={23} /><strong>{copy.reader}</strong><span>查看前后文</span><span>核对版本与页码</span><span>复制引用</span></aside></div>
      </div>
      <div className={`${styles.demoPanel} ${styles.savedPanel}`}>
        <div className={styles.demoBar}><FolderOpen size={17} /><span>我的研究</span><Check size={17} /></div>
        <div className={styles.continuousResearch}>
          <div className={styles.researchThread}><span>上次的问题</span><strong>{copy.question}</strong><div className={styles.researchSources}><FileText size={16} />原文<NotebookPen size={16} />笔记<Check size={14} /></div></div>
          <div className={styles.researchFollowUp}><span>继续研究</span><strong>还有哪些不同的解释？</strong><ArrowRight size={19} /></div>
        </div>
        <div className={styles.savedFooter}><Check size={16} /> {copy.saved}</div>
      </div>
    </div>
    <div className={styles.playback}><button type="button" aria-label={paused ? "播放演示" : "暂停演示"} onClick={() => setPaused(value => !value)}>{paused ? <Play size={17} /> : <Pause size={17} />}</button><button type="button" aria-label="重新播放演示" onClick={() => { setReplay(value => value + 1); setPaused(false); }}><RotateCcw size={17} /></button></div>
  </figure>;
}

export function HomeFeatureStory({ books, closingImage, brandConfig, compareCopy = false, initialCopy = 0, content, discovery }: { books: StoryBook[]; closingImage: string; brandConfig: BrandConfig; compareCopy?: boolean; initialCopy?: number; content?: WelcomeConfig; discovery: WelcomeDiscovery }) {
  const { copies: copyOptions, chapters, texts } = welcomeContent(content);
  const [copyIndex, setCopyIndex] = useState(initialCopy);
  const copy = copyOptions[copyIndex];
  return <div className={styles.story}>
    <section className={styles.hero} aria-labelledby="welcome-title">
      <div className={styles.heroCopy}>
        {compareCopy ? <div className={styles.copyOptions} id="welcome-copy" role="group" aria-label="欢迎卡片文案方案">{copyOptions.map((option, index) => <button type="button" key={option.id} aria-pressed={copyIndex === index} onClick={() => setCopyIndex(index)}>{option.label}</button>)}</div> : null}
        <h1 id="welcome-title">{copy.title.map((line, index) => <span key={index}>{line}</span>)}</h1><p>{copy.lead}</p><a data-library-entry href="/home" className={styles.primary}>{texts.enter_label} <ArrowRight size={21} aria-hidden="true" /></a></div>
      <WorkflowDemo books={books} brandConfig={brandConfig} copy={copy} history={texts} discovery={discovery} />
      <nav className={styles.topicTrail} aria-label="探索书库"><Link href="/scholars">学者</Link><Link href="/theories">理论流派</Link><Link href="/topics">主题</Link><Link href="/explore/original">原文</Link><Link href="/recommendations">特别策划</Link></nav>
    </section>
    <section className={styles.philosophy} aria-labelledby="welcome-philosophy"><GrainField /><div><h2 id="welcome-philosophy">{texts.philosophy_title}</h2><p>{texts.philosophy_body}</p></div></section>
    <section className={styles.collections} aria-label="认识书库">
      <header className={styles.sectionHeading}><h2>{texts.discovery_theory_title}</h2><p>{texts.discovery_theory_body}</p></header>
      <div className={styles.collectionPair}>{([['scholars', '/scholars', texts.history_scholars], ['theories', '/theories', texts.history_theories]] as const).map(([kind, href, title]) => <article key={kind}><Link href={href} className={styles.collectionHeading}><h3>{title}</h3><ArrowRight size={21} /></Link><DiscoveryView kind={kind} discovery={discovery} interactive /></article>)}</div>
      <header className={styles.sectionHeading}><h2>{texts.discovery_issue_title}</h2><p>{texts.discovery_issue_body}</p></header>
      <div className={styles.collectionPair}><article><Link href="/topics" className={styles.collectionHeading}><h3>主题</h3><ArrowRight size={21} /></Link><DiscoveryView kind="topics" discovery={discovery} interactive /></article><article><Link href="/recommendations" className={styles.collectionHeading}><h3>特别策划</h3><ArrowRight size={21} /></Link><DiscoveryView kind="issue" discovery={discovery} interactive /></article></div>
    </section>
    <section className={styles.features} id="library-features" aria-labelledby="welcome-features">
      <header className={styles.sectionHeading}><h2 id="welcome-features">{texts.features_title}</h2><p>{texts.features_body}</p></header>
      {chapters.map((chapter, index) => <article className={styles.featureRow} key={chapter.href} aria-labelledby={`welcome-feature-${index}`}>
        <div className={styles.featureCopy}><h3 id={`welcome-feature-${index}`}>{chapter.title}</h3><p>{chapter.text}</p><Link href={chapter.href} className={styles.textLink}>{chapter.action} <ArrowRight size={18} aria-hidden="true" /></Link></div>
        <div className={styles.visual}><StoryScene chapter={index} books={books} /></div>
      </article>)}
    </section>
    <section className={styles.principles} aria-labelledby="welcome-principles"><div className={styles.sectionHeading}><h2 id="welcome-principles">{texts.principles_title}</h2></div><div className={styles.principleGrid}>
      <div><h3>{texts.principle_source_title}</h3><p>{texts.principle_source_body}</p></div><div><h3>{texts.principle_context_title}</h3><p>{texts.principle_context_body}</p></div><div><h3>{texts.principle_debate_title}</h3><p>{texts.principle_debate_body}</p></div><div><h3>{texts.principle_judgment_title}</h3><p>{texts.principle_judgment_body}</p></div>
    </div></section>
    <section className={styles.invitation} aria-labelledby="welcome-invitation"><div><h2 id="welcome-invitation">{texts.invitation_title}</h2><p>{texts.invitation_body}</p><Link href="/explore" className={styles.textLink}>浏览馆藏 <ArrowRight size={18} aria-hidden="true" /></Link></div><img src={closingImage} {...editorialImageSources(closingImage, "(max-width: 760px) 100vw, 50vw")} alt="" width={1536} height={1024} loading="lazy" decoding="async" /></section>
    <section className={styles.faq} aria-labelledby="welcome-faq"><h2 id="welcome-faq">{texts.faq_title}</h2><div>
      <section data-content-section><header data-section-heading>{texts.faq_read_title}<Plus size={20} aria-hidden="true" /></header><p>{texts.faq_read_body}</p></section>
      <section data-content-section><header data-section-heading>{texts.faq_cite_title}<Plus size={20} aria-hidden="true" /></header><p>{texts.faq_cite_body}</p></section>
      <section data-content-section><header data-section-heading>{texts.faq_private_title}<Plus size={20} aria-hidden="true" /></header><p>{texts.faq_private_body}</p></section>
    </div></section>
    <section className={styles.closing} aria-labelledby="welcome-enter"><GrainField /><h2 id="welcome-enter">{texts.closing_title}</h2><a data-library-entry href="/home" className={styles.primary}>{texts.enter_label} <ArrowRight size={21} aria-hidden="true" /></a></section>
  </div>;
}
