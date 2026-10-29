"use client";

import { useState } from "react";
import { ArrowRight, BookOpen, Search, X } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { SourceText } from "@/components/source-text";
import styles from "./preview.module.css";

const options = [
  { id: "line", number: "01", title: "书刊细线", copy: "以文字下划线为主，安静、明确。", use: "适合书名、学者姓名、正文链接与栏目入口。" },
  { id: "surface", number: "02", title: "温和底色", copy: "用浅底色与边框标出操作范围。", use: "适合管理导航、筛选按钮与可点击卡片。" },
  { id: "direction", number: "03", title: "轻盈指向", copy: "短线与箭头轻移，提示下一步。", use: "适合策展卡片、继续阅读与更多内容入口。" },
] as const;
const sample = "这是用于观察排版的自写示例，并非书中引文。原来被换行拆开的中\n文会连续排列，English words\nremain separated。\n\n第二段保留段落间距，脚注编号 [24] 与标点也保留。\n1. 列表保留独立行\n2. 页面位置与原始内容不变";

export default function InteractionPreviewPage() {
  const [variant, setVariant] = useState<string>("line");
  const [showHover, setShowHover] = useState(false);
  const [tab, setTab] = useState("全部");
  const [open, setOpen] = useState(false);
  const [original, setOriginal] = useState(false);
  const [feedback, setFeedback] = useState("");
  const current = options.find(option => option.id === variant)!;
  return <div className={styles.page}>
    <header className={styles.intro}><p className={styles.kicker}>交互设计预览 · 三种方案</p><h1>让可点击的地方，更清楚。</h1><p>把鼠标移到文字、卡片和按钮上，比较不同的反馈。也可以按 Tab 查看键盘焦点。</p></header>
    <div className={styles.choices} role="group" aria-label="悬浮方案">{options.map(option => <button key={option.id} type="button" aria-pressed={variant === option.id} onClick={() => { setVariant(option.id); setFeedback(""); }}><span className={styles.number}>{option.number}</span><strong>{option.title}</strong><span>{option.copy}</span></button>)}</div>
    <div className={styles.toolbar}><p>{current.use}</p><label><input type="checkbox" checked={showHover} onChange={event => setShowHover(event.target.checked)} />显示悬浮状态</label></div>
    <section className={styles.preview} data-variant={variant} data-show-hover={showHover} aria-label={`${current.title}交互示例`}>
      <div className={styles.previewHeader}><div><span className={styles.kicker}>工作列表 · 示例</span><h2>继续你的阅读与整理</h2></div><button type="button" className={styles.iconButton} aria-label="打开弹窗预览" onClick={() => setOpen(true)}><Search size={19} aria-hidden="true" /></button></div>
      <div className={styles.tabs} role="group" aria-label="示例分类">{["全部", "最近阅读", "待整理"].map(name => <button type="button" key={name} aria-pressed={tab === name} onClick={() => { setTab(name); setFeedback(`已切换至“${name}”示例。`); }}><span>{name}</span></button>)}</div>
      <div className={styles.examples}>
        <div className={styles.worklist}>
          <article className={styles.row}><div className={styles.book} aria-hidden="true"><BookOpen size={28} /></div><div><p className={styles.meta}>书籍 · 阅读记录示例</p><h3><button type="button" className={styles.textLink} onClick={() => setOpen(true)}>社会学方法的准则</button></h3><p>埃米尔·涂尔干</p></div><button type="button" className={styles.action} onClick={() => setOpen(true)}><span>继续阅读</span><ArrowRight size={17} /></button></article>
          <article className={styles.row}><div className={styles.book} aria-hidden="true"><BookOpen size={28} /></div><div><p className={styles.meta}>书籍 · 整理记录示例</p><h3><button type="button" className={styles.textLink} onClick={() => setOpen(true)}>国家的视角</button></h3><p>詹姆斯·C.斯科特</p></div><button type="button" className={styles.action} onClick={() => setOpen(true)}><span>查看详情</span><ArrowRight size={17} /></button></article>
          <div className={styles.controls}><button type="button" className={styles.outlineButton} onClick={() => setOpen(true)}>打开弹窗预览</button><button type="button" className={styles.outlineButton} disabled>暂无更多内容</button></div>
        </div>
        <button type="button" className={styles.featureCard} onClick={() => setOpen(true)}><span className={styles.meta}>特别策划 · 单一入口示例</span><span className={styles.cardTitle}>从清晰化<br />到地方知识</span><span className={styles.cardCopy}>以一本书为起点，走进国家、社会与日常经验之间的讨论。</span><span className={styles.cardAction}><span>打开策划</span><ArrowRight size={20} /></span></button>
      </div>
      <p className={styles.feedback} role="status">{feedback || "示例内容，仅用于比较样式，不会修改馆藏或阅读记录。"}</p>
    </section>
    <section className={styles.notes}><h2>按用途组合，会比全站套用一种更自然。</h2><p>书名与正文链接用细线，管理入口用底色，策展入口用轻移的箭头。纯正文不动，禁用按钮不响应；一行有多个操作时，只强调对应按钮。</p><p className={styles.sources}>方法参考：<a href="https://carbondesignsystem.com/components/link/usage/" target="_blank" rel="noreferrer">Carbon · 链接</a><a href="https://spectrum.adobe.com/page/motion/" target="_blank" rel="noreferrer">Spectrum · 动效</a><a href="https://designsystem.gov.scot/components/card" target="_blank" rel="noreferrer">Scottish Government · 卡片</a></p></section>
    <Dialog open={open} onRequestClose={() => setOpen(false)} className={styles.dialog} aria-labelledby="interaction-dialog-title"><header><div><p className={styles.meta}>交互预览</p><h2 id="interaction-dialog-title">原文排版示例</h2></div><button type="button" className={styles.iconButton} aria-label="关闭预览" onClick={() => setOpen(false)}><X size={19} /></button></header><div className={styles.dialogBody}><button type="button" className={styles.outlineButton} aria-pressed={original} onClick={() => setOriginal(value => !value)}>原始换行</button><blockquote><SourceText text={sample} original={original} /></blockquote><p className={styles.meta}>这是自写的排版示例，不是检索结果。按 Esc 或点窗口外侧可关闭。</p></div></Dialog>
  </div>;
}
