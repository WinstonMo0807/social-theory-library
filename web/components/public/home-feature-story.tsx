"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { ArrowRight, BookOpen, Check, FileText, FolderOpen, NotebookPen, Pause, Play, Plus, RotateCcw, Search } from "lucide-react";
import { BrandImage } from "@/components/brand-image";
import type { SiteConfig } from "@/lib/site-config";
import styles from "./home-feature-story.module.css";

import { welcomeContent, type WelcomeConfig, type WelcomeCopy, type WelcomeBook as StoryBook } from "@/lib/welcome";
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
      <div className={styles.bookShelf}>{(books.length ? books : [{ id: "empty", title: "社会理论", author: "" }]).map((entry) => <div className={styles.book} key={entry.id}>
        {entry.coverImage ? <img src={entry.coverImage} alt="" loading="lazy" width={124} height={178} /> : <div className={styles.bookFallback}><BookOpen size={32} strokeWidth={1} /><span>{entry.title}</span></div>}
        <strong>{entry.title}</strong><span>{entry.author}</span>
      </div>)}</div>
      <div className={styles.discoveryTerms}><span>学者</span><i /><span>理论</span><i /><span>主题</span></div>
    </> : null}
    {chapter === 1 ? <div className={styles.readingDesk}>
      <div className={styles.sourceSlip}><BookOpen size={21} strokeWidth={1.4} /><span>{book?.title || "原文阅读"}</span></div>
      <div className={styles.openPages}><div className={styles.paperPage}><span className={styles.paperHeading}>原文</span><TextLines /><TextLines highlighted /><TextLines /></div><div className={styles.paperPage}><span className={styles.paperHeading}>前后文</span><TextLines /><TextLines /><TextLines /></div></div>
    </div> : null}
    {chapter === 2 ? <div className={styles.citationDesk}>
      <div className={styles.citationSheet}><span className={styles.paperHeading}>引文</span><TextLines highlighted /><TextLines /><span className={styles.citationRule} /></div>
      <div className={styles.sourceCard}><FileText size={23} strokeWidth={1.3} /><strong>{book?.title || "引用来源"}</strong><span>{book?.author}</span><div className={styles.sourceFields}><span>作者与版本</span><span>原文与页码</span><span>引用上下文</span></div></div>
    </div> : null}
    {chapter === 3 ? <div className={styles.researchDesk}>
      <div className={styles.researchFolder}><FolderOpen size={26} strokeWidth={1.2} /><span>我的研究</span><div className={styles.folderTabs}><span>原文</span><span>书单</span><span>阅读计划</span></div><TextLines /></div>
      <div className={styles.notebook}><NotebookPen size={25} strokeWidth={1.2} /><span>笔记</span><TextLines /><TextLines highlighted /></div>
    </div> : null}
  </div>;
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

function WorkflowDemo({ books, brandConfig, copy, history }: { books: StoryBook[]; brandConfig: BrandConfig; copy: WelcomeCopy; history: ReturnType<typeof welcomeContent>["texts"] }) {
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

  return <figure ref={ref} className={styles.demo} data-playing={canAnimate && !paused} aria-label="功能演示：沿学科史认识学者与流派，提出问题，查找文献，阅读原文，保存材料与笔记">
    <div className={styles.timeline} key={`${copy.id}-${replay}`} aria-hidden="true">
      <GrainField /><div className={styles.demoFrame} />
      <div className={styles.brandPanel}><BrandImage config={brandConfig} alt="" /></div>
      <div className={`${styles.demoPanel} ${styles.historyPanel}`}>
        <h2>{history.history_title}</h2>
        <div className={styles.historySubjects}>{history.history_subjects.split("、").filter(Boolean).slice(0, 3).map(subject => <span key={subject}>{subject}</span>)}</div>
        <div className={styles.historyRelations}><span>{history.history_scholars}</span><i /><span>{history.history_theories}</span></div>
        <div className={styles.historyBooks}><span>{history.history_works}</span><div>{books.map(entry => <span key={entry.id}>{entry.coverImage ? <img src={entry.coverImage} width={38} height={54} alt="" /> : <BookOpen size={28} />}<strong>{entry.title}</strong></span>)}</div></div>
      </div>
      <div className={`${styles.demoPanel} ${styles.askPanel}`}>
        <span className={styles.demoEyebrow}><Search size={17} /> 观点检索</span>
        <div className={styles.typedQuestion}><span>{copy.question}</span></div>
        <div className={styles.askTools}><span><Plus size={16} /> 选择文献</span><span className={styles.sendArrow}><ArrowRight size={20} /></span></div>
      </div>
      <div className={`${styles.demoPanel} ${styles.workingPanel}`}><span className={styles.spinner} /><span>正在寻找相关原文</span></div>
      <div className={`${styles.demoPanel} ${styles.resultsPanel}`}>
        <div className={styles.demoBar}><Search size={17} /><span>{copy.results}</span><span>原文节选</span></div>
        <div className={styles.demoResults}>{books.length ? books.map((entry, index) => <div className={styles.resultRow} key={entry.id} data-row={index}>
          {entry.coverImage ? <img src={entry.coverImage} alt="" width={46} height={64} /> : <BookOpen size={28} />}
          <div><strong>{entry.title}</strong><span>{entry.author}</span><TextLines highlighted={index === 0} /></div><ArrowRight size={17} />
        </div>) : <div className={styles.emptyIllustration}><BookOpen size={32} /><span>查找文献与原文</span><TextLines highlighted /></div>}</div>
      </div>
      <div className={`${styles.demoPanel} ${styles.readerPanel}`}>
        <div className={styles.demoBar}><BookOpen size={17} /><span>{book?.title || "原文阅读"}</span><span>原文与出处</span></div>
        <div className={styles.readerBody}><div><strong>原文</strong><TextLines /><TextLines highlighted /><TextLines /></div><aside><FileText size={23} /><strong>{copy.reader}</strong><span>查看前后文</span><span>核对版本与页码</span><span>复制引用</span></aside></div>
      </div>
      <div className={`${styles.demoPanel} ${styles.savedPanel}`}>
        <div className={styles.demoBar}><FolderOpen size={17} /><span>我的研究</span><Check size={17} /></div>
        <div className={styles.savedBody}><div><NotebookPen size={25} /><strong>阅读笔记</strong><TextLines highlighted /></div><div><BookOpen size={25} /><strong>参考文献</strong>{books.slice(0, 3).map(entry => <span key={entry.id}>{entry.title}</span>)}</div></div>
        <div className={styles.savedFooter}><Check size={16} /> {copy.saved}</div>
      </div>
    </div>
    <div className={styles.playback}><button type="button" aria-label={paused ? "播放演示" : "暂停演示"} onClick={() => setPaused(value => !value)}>{paused ? <Play size={17} /> : <Pause size={17} />}</button><button type="button" aria-label="重新播放演示" onClick={() => { setReplay(value => value + 1); setPaused(false); }}><RotateCcw size={17} /></button></div>
  </figure>;
}

export function HomeFeatureStory({ books, closingImage, brandConfig, compareCopy = false, initialCopy = 0, content }: { books: StoryBook[]; closingImage: string; brandConfig: BrandConfig; compareCopy?: boolean; initialCopy?: number; content?: WelcomeConfig }) {
  const { copies: copyOptions, chapters, texts } = welcomeContent(content);
  const [copyIndex, setCopyIndex] = useState(initialCopy);
  const copy = copyOptions[copyIndex];
  return <div className={styles.story}>
    <section className={styles.hero} aria-labelledby="welcome-title">
      <div className={styles.heroCopy}>
        {compareCopy ? <div className={styles.copyOptions} id="welcome-copy" role="group" aria-label="欢迎卡片文案方案">{copyOptions.map((option, index) => <button type="button" key={option.id} aria-pressed={copyIndex === index} onClick={() => setCopyIndex(index)}>{option.label}</button>)}</div> : null}
        <h1 id="welcome-title">{copy.title.map((line, index) => <span key={index}>{line}</span>)}</h1><p>{copy.lead}</p><Link href="/" className={styles.primary}>{texts.enter_label} <ArrowRight size={21} aria-hidden="true" /></Link></div>
      <WorkflowDemo books={books} brandConfig={brandConfig} copy={copy} history={texts} />
      <nav className={styles.topicTrail} aria-label="探索书库"><Link href="/scholars">学者</Link><Link href="/theories">理论流派</Link><Link href="/topics">主题</Link><Link href="/explore/original">原文</Link><Link href="/recommendations">特别策划</Link></nav>
    </section>
    <section className={styles.philosophy} aria-labelledby="welcome-philosophy"><GrainField /><div><h2 id="welcome-philosophy">{texts.philosophy_title}</h2><p>{texts.philosophy_body}</p></div></section>
    <section className={styles.features} id="library-features" aria-labelledby="welcome-features">
      <header className={styles.sectionHeading}><h2 id="welcome-features">{texts.features_title}</h2><p>{texts.features_body}</p></header>
      {chapters.map((chapter, index) => <article className={styles.featureRow} key={chapter.href} aria-labelledby={`welcome-feature-${index}`}>
        <div className={styles.featureCopy}><h3 id={`welcome-feature-${index}`}>{chapter.title}</h3><p>{chapter.text}</p><Link href={chapter.href} className={styles.textLink}>{chapter.action} <ArrowRight size={18} aria-hidden="true" /></Link></div>
        <div className={styles.visual}><StoryScene chapter={index} books={books} /></div>
      </article>)}
      <div className={styles.discoveryGrid}>
        <article><Link href="/theories" className={styles.discoveryImage} aria-label="探索理论"><img src="/editorial/generated-20261030/theories.webp" alt="" width={1024} height={640} loading="lazy" /></Link><h3>{texts.discovery_theory_title}</h3><p>{texts.discovery_theory_body}</p><Link href="/theories" className={styles.textLink}>探索理论 <ArrowRight size={18} aria-hidden="true" /></Link></article>
        <article><Link href="/recommendations" className={styles.discoveryImage} aria-label="阅读策划"><img src="/editorial/generated-20261030/editorial.webp" alt="" width={1024} height={640} loading="lazy" /></Link><h3>{texts.discovery_issue_title}</h3><p>{texts.discovery_issue_body}</p><Link href="/recommendations" className={styles.textLink}>阅读策划 <ArrowRight size={18} aria-hidden="true" /></Link></article>
      </div>
    </section>
    <section className={styles.principles} aria-labelledby="welcome-principles"><div className={styles.sectionHeading}><h2 id="welcome-principles">{texts.principles_title}</h2></div><div className={styles.principleGrid}>
      <div><h3>{texts.principle_source_title}</h3><p>{texts.principle_source_body}</p></div><div><h3>{texts.principle_context_title}</h3><p>{texts.principle_context_body}</p></div><div><h3>{texts.principle_debate_title}</h3><p>{texts.principle_debate_body}</p></div><div><h3>{texts.principle_judgment_title}</h3><p>{texts.principle_judgment_body}</p></div>
    </div></section>
    <section className={styles.invitation} aria-labelledby="welcome-invitation"><div><h2 id="welcome-invitation">{texts.invitation_title}</h2><p>{texts.invitation_body}</p><Link href="/explore" className={styles.textLink}>浏览馆藏 <ArrowRight size={18} aria-hidden="true" /></Link></div><img src={closingImage} alt="" width={1536} height={1024} loading="lazy" /></section>
    <section className={styles.faq} aria-labelledby="welcome-faq"><h2 id="welcome-faq">{texts.faq_title}</h2><div>
      <details><summary>{texts.faq_read_title}<Plus size={20} aria-hidden="true" /></summary><p>{texts.faq_read_body}</p></details>
      <details><summary>{texts.faq_cite_title}<Plus size={20} aria-hidden="true" /></summary><p>{texts.faq_cite_body}</p></details>
      <details><summary>{texts.faq_private_title}<Plus size={20} aria-hidden="true" /></summary><p>{texts.faq_private_body}</p></details>
    </div></section>
    <section className={styles.closing} aria-labelledby="welcome-enter"><GrainField /><h2 id="welcome-enter">{texts.closing_title}</h2><Link href="/" className={styles.primary}>{texts.enter_label} <ArrowRight size={21} aria-hidden="true" /></Link></section>
  </div>;
}
