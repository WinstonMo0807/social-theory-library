"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { ArrowDown, ArrowUp, ArrowRight, BookOpen, FileText, FolderOpen, NotebookPen, Search } from "lucide-react";
import styles from "./home-feature-story.module.css";

type StoryBook = { id: string; title: string; author: string; coverImage?: string };
const chapters = [
  { title: "先提出你的问题", text: "用自己的话检索观点，也可以沿着学者、流派与主题找到书。", href: "/explore/opinions", action: "检索观点" },
  { title: "读到观点的来处", text: "从原文节选打开 PDF，连同前后文一起阅读。", href: "/explore/original", action: "查找原文" },
  { title: "让引文有据可查", text: "回到具体版本与页码，核对原文，再决定如何引用。", href: "/account/citation-audits", action: "核对引文" },
  { title: "留下自己的思考", text: "把材料、笔记与阅读计划保存在读者中心，下次接着读。", href: "/account", action: "进入读者中心" },
];

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

export function HomeFeatureStory({ books, closingTitle, closingImage }: { books: StoryBook[]; closingTitle: string[]; closingImage: string }) {
  const [active, setActive] = useState(0);
  const viewport = useRef<HTMLDivElement>(null);
  const chapterRefs = useRef<(HTMLElement | null)[]>([]);
  const labels = [...chapters.map(chapter => chapter.title), "进入书库"];

  function goTo(index: number, keyboard: boolean) {
    const target = chapterRefs.current[index];
    if (!target || !viewport.current) return;
    viewport.current.scrollTo({ top: target.offsetTop, behavior: keyboard || window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
  }

  return <section id="library-features" className={styles.story} data-welcome-deck aria-labelledby="welcome-title">
    <h1 id="welcome-title" className="sr-only">欢迎来到社会理论书库</h1>
    <div className={styles.viewport} ref={viewport} tabIndex={0} role="region" aria-label="书库介绍，向下滚动查看下一张卡片" onScroll={() => {
      const node = viewport.current;
      if (!node) return;
      const midpoint = node.scrollTop + node.clientHeight / 2;
      const index = chapterRefs.current.findIndex(element => element && midpoint >= element.offsetTop && midpoint < element.offsetTop + element.offsetHeight);
      if (index >= 0) setActive(index);
    }}>
      {chapters.map((chapter, index) => <article className={styles.slide} key={chapter.href} aria-labelledby={`welcome-chapter-${index}`} ref={element => { chapterRefs.current[index] = element; }}>
        <div className={styles.card}>
          <div className={styles.chapterCopy}><h2 id={`welcome-chapter-${index}`}>{chapter.title}</h2><p>{chapter.text}</p><Link href={chapter.href}>{chapter.action} <ArrowRight size={18} aria-hidden="true" /></Link></div>
          <div className={styles.visual}><StoryScene chapter={index} books={books} /><span className={styles.sceneCaption}>功能示意</span></div>
        </div>
      </article>)}
      <article className={styles.slide} aria-labelledby="welcome-enter-title" ref={element => { chapterRefs.current[4] = element; }}>
        <div className={`${styles.card} ${styles.closing}`}>
          <div className={styles.chapterCopy}><h2 id="welcome-enter-title">{closingTitle.map((line, index) => <span key={index}>{line}</span>)}</h2><p>从这里，开始你的阅读与研究。</p><Link href="/" className={styles.enter}>进入书库 <ArrowRight size={20} aria-hidden="true" /></Link></div>
          <div className={styles.closingImage}><img src={closingImage} alt="" width={1536} height={1024} loading="lazy" /></div>
        </div>
      </article>
    </div>
    <div className={styles.controls}>
      <span className={styles.count} aria-hidden="true">0{active + 1}<span> / 05</span></span>
      <nav className={styles.pagination} aria-label="欢迎页卡片">{labels.map((label, index) => <button key={label} type="button" aria-label={`第${index + 1}张：${label}`} aria-current={active === index ? "step" : undefined} onClick={event => goTo(index, event.detail === 0)}><span /></button>)}</nav>
      <div className={styles.arrows}><button type="button" aria-label="上一张" disabled={active === 0} onClick={event => goTo(active - 1, event.detail === 0)}><ArrowUp size={18} /></button><button type="button" aria-label="下一张" disabled={active === 4} onClick={event => goTo(active + 1, event.detail === 0)}><ArrowDown size={18} /></button></div>
    </div>
  </section>;
}
