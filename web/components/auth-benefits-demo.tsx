"use client";

import { ArrowDownToLine, ArrowRight, Bookmark, BookOpen, FileText, NotebookPen, Pause, Play, Search } from "lucide-react";
import { useEffect, useState } from "react";
import styles from "./auth-session-dialog.module.css";

const chapters = [
  { title: "从问题找到原文", label: "观点检索", detail: "带着问题，读到不同的解释。" },
  { title: "把原文放回上下文", label: "阅读与下载", detail: "打开 PDF，连同前后文一起读。" },
  { title: "让研究接着往下走", label: "连续研究", detail: "留下原文与笔记，下次从这里继续。" },
];

function Lines({ highlight = false }: { highlight?: boolean }) {
  return <div className={styles.lines} data-highlight={highlight || undefined}><i /><i /><i /><i /></div>;
}

/** Workflow illustration only: no simulated research is sent to an API. */
export function AuthBenefitsDemo() {
  const [chapter, setChapter] = useState(0);
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(true);
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const updateMotion = () => setReduced(media.matches);
    const updateVisibility = () => setVisible(document.visibilityState === "visible");
    updateMotion(); updateVisibility();
    media.addEventListener("change", updateMotion);
    document.addEventListener("visibilitychange", updateVisibility);
    return () => { media.removeEventListener("change", updateMotion); document.removeEventListener("visibilitychange", updateVisibility); };
  }, []);
  useEffect(() => {
    if (paused || reduced || !visible) return;
    const timer = window.setInterval(() => setChapter(value => (value + 1) % chapters.length), 5200);
    return () => window.clearInterval(timer);
  }, [paused, reduced, visible]);
  return <aside className={styles.benefits} aria-label="登录后可使用的功能" data-paused={paused || reduced || !visible}>
    <div className={styles.demoTop}><span>你的阅读与研究</span><button onClick={() => setPaused(value => !value)} disabled={reduced} aria-label={paused || reduced ? "播放功能介绍" : "暂停功能介绍"}>{paused || reduced ? <Play size={15} /> : <Pause size={15} />}</button></div>
    <div className={styles.stage} aria-hidden="true">
      <div className={styles.scene} data-active={chapter === 0}>
        <div className={styles.search}><Search size={18} /><span>技术如何改变日常生活？</span><ArrowRight size={17} /></div>
        <div className={styles.excerpt}><span><FileText size={16} />原文节选</span><Lines highlight /><div className={styles.paperFooter}><span>查看上下文</span><ArrowRight size={16} /></div></div>
        <div className={styles.secondExcerpt}><Lines /></div>
      </div>
      <div className={styles.scene} data-active={chapter === 1}>
        <div className={styles.readerBar}><BookOpen size={18} /><span>原文阅读</span><Bookmark size={17} /><ArrowDownToLine size={17} /></div>
        <div className={styles.pages}><div><Lines /><Lines highlight /><Lines /></div><div><Lines /><Lines /><Lines /></div></div>
      </div>
      <div className={styles.scene} data-active={chapter === 2}>
        <div className={styles.research}><span>我的研究</span><strong>技术与日常生活</strong><div><span><FileText size={16} />原文</span><span><NotebookPen size={16} />笔记</span></div><Lines /></div>
        <div className={styles.followUp}><span>接着上次，继续追问</span><ArrowRight size={18} /></div>
      </div>
    </div>
    <div className={styles.caption}><h3>{chapters[chapter].title}</h3><p>{chapters[chapter].detail}</p></div>
    <div className={styles.chapters} role="group" aria-label="选择功能介绍">{chapters.map((item, index) => <button key={item.label} aria-pressed={chapter === index} onClick={() => { setChapter(index); setPaused(true); }}>{item.label}</button>)}</div>
  </aside>;
}
