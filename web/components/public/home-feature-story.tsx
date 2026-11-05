"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, BookOpen, FileText, FolderOpen, NotebookPen, Search } from "lucide-react";
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

export function HomeFeatureStory({ books }: { books: StoryBook[] }) {
  const [active, setActive] = useState(0);
  const chapterRefs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 900px) and (min-height: 650px)");
    let observer: IntersectionObserver | undefined;
    const observe = () => {
      observer?.disconnect();
      if (!desktop.matches) return;
      const midpoint = Math.round(window.innerHeight / 2);
      observer = new IntersectionObserver(entries => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(Number((entry.target as HTMLElement).dataset.chapter));
        }
      }, { rootMargin: `-${midpoint}px 0px -${window.innerHeight - midpoint - 1}px 0px`, threshold: 0 });
      chapterRefs.current.forEach(element => { if (element) observer!.observe(element); });
    };
    observe();
    desktop.addEventListener("change", observe);
    window.addEventListener("resize", observe);
    return () => { observer?.disconnect(); desktop.removeEventListener("change", observe); window.removeEventListener("resize", observe); };
  }, []);

  return <section id="library-features" className={styles.story} aria-labelledby="library-features-title">
    <header className={styles.heading}><h2 id="library-features-title">让阅读成为研究</h2><Link href="/">浏览馆藏 <ArrowRight size={16} aria-hidden="true" /></Link></header>
    <div className={styles.layout}>
      <div className={styles.chapters}>{chapters.map((chapter, index) => <article className={styles.chapter} key={chapter.href} data-chapter={index} data-active={active === index || undefined} ref={element => { chapterRefs.current[index] = element; }}>
        <div className={styles.chapterCopy}><span className={styles.chapterNumber} aria-hidden="true">0{index + 1}</span><h3>{chapter.title}</h3><p>{chapter.text}</p><Link href={chapter.href} onFocus={() => setActive(index)}>{chapter.action} <ArrowRight size={17} aria-hidden="true" /></Link></div>
        <div className={styles.mobileScene}><StoryScene chapter={index} books={books} /></div>
      </article>)}</div>
      <div className={styles.stageRail} aria-hidden="true"><div className={styles.stage}>
        {chapters.map((chapter, index) => <div key={chapter.href} className={styles.sceneLayer} data-active={active === index || undefined}><StoryScene chapter={index} books={books} /></div>)}
        <div className={styles.stageFoot}><span>功能演示</span><span>0{active + 1} / 04</span></div>
      </div></div>
    </div>
  </section>;
}
