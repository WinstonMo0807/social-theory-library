"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { ArrowRight, BookOpen, Check, FileText, FolderOpen, NotebookPen, Pause, Play, Plus, RotateCcw, Search } from "lucide-react";
import { BrandImage } from "@/components/brand-image";
import type { WorkflowDemoProps } from "./welcome-demo";
import { GrainField, TextLines } from "./welcome-illustrations";
import { EditorialDiscoveryArt, ScholarDiscoveryArt, TheoryDiscoveryArt } from "./welcome-discovery-art";
import styles from "./home-feature-story.module.css";

export default function WorkflowDemo({ books, brandConfig, copy, history, discovery }: WorkflowDemoProps) {
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
          {entry.coverImage ? <img src={entry.coverImage} srcSet={entry.coverSources?.map(row => `${row.url} ${row.width}w`).join(", ")} sizes="46px" alt="" width={46} height={64} loading="lazy" decoding="async" /> : <BookOpen size={28} />}
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
