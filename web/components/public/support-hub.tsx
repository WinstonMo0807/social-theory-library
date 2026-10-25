"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, BookOpen, CircleHelp, MessageCircle, Search, Quote, Layers } from "lucide-react";
import type { PublicSiteContent } from "@/lib/site-content";
import { SiteAnnouncements, SitePublicExplanations } from "./site-public-copy";
import type { SiteConfig } from "@/lib/site-config";
import { supportFaqs, type SupportSection } from "@/lib/support-content";
import { SupportHero, SupportNavigation } from "./support-hero";
import { SupportCitationExample } from "./support-citation-example";

export function SupportHub({ config, section = "guide", unavailable = false, about }: { about?:PublicSiteContent|null; config: SiteConfig; section?: SupportSection; unavailable?: boolean }) {
  return <div className="stl4-support-page"><SupportHero title="使用帮助与反馈" intro="了解书库的内容与使用方法，获取阅读与引用支持，与我们一起完善更开放的社会理论知识空间。" /><SupportNavigation current={section} />{unavailable ? <p className="stl4-support-status" role="status">网站配置暂时无法加载，以下使用说明仍可阅读。</p> : null}
    {section === "guide" ? <SupportGuides /> : section === "faq" ? <SupportFaq /> : section === "content" ? <SitePublicExplanations config={config} about={about}/> : section === "source" ? <section className="stl4-support-section"><h2>来源纠错</h2><p className="stl4-support-lead">发现书目信息、识别文字或页码问题时，提供能够核对的位置。</p><ol className="stl4-support-checks"><li>确认作品、出版版本与当前阅读文件。</li><li>记下 PDF 物理页；有印刷页码时一并说明。</li><li>关联公开阅读页面，描述实际内容与预期内容。</li></ol><div className="stl4-support-notice"><CircleHelp size={23} /><div><h3>来源暂时不可用？</h3><p>先在原文页面重新读取，按实际提示区分访问限制与临时错误。这里不会替未选择的来源判断状态。</p><Link href="/help/source">查看来源说明 <ArrowRight size={15} /></Link></div><Link className="stl4-support-primary" href="/feedback?category=content">提交来源纠错</Link></div></section> : section === "updates" ? <SiteAnnouncements about={about}/> : <SupportGuides />}
    <div className="stl4-support-feedback-callout"><div><h2>仍有问题？</h2><p>告诉我们你遇到的具体情况，我们会尽快回复。</p></div><Link className="stl4-support-primary" href="/feedback"><MessageCircle size={18} />提交反馈 <ArrowRight size={16} /></Link></div>
  </div>;
}

function SupportGuides() {
  const [readingStep, setReadingStep] = useState(0);
  const readingHints = ["选择目录节点，跳到对应的正文页面。", "阅读章节正文，核对来源信息。", "核对 PDF 页序与书页上印出的页码。", "阅读完整段落，再保存笔记或复制引用。"];
  return <><section className="stl4-support-section"><header className="stl4-support-section-heading"><h2>使用指南</h2><p>三步开始你的阅读与研究</p></header><div className="stl4-support-card-grid">
    <article className="stl4-support-card"><header><Search /><span>01</span><div><h3>搜索资料</h3><p>输入书名、作者、概念或主题，从图书、专题与学者中找到相关内容。</p></div></header><div className="stl4-support-search-demo"><form action="/explore" role="search" aria-label="帮助页搜索书库"><input type="hidden" name="context" value="global" /><label><Search size={16} /><span className="sr-only">搜索书名、作者、概念、主题</span><input type="search" name="q" required placeholder="搜索书名、作者、概念、主题…" /></label><button type="submit">搜索</button></form></div><Link href="/help/search">搜索技巧 <ArrowRight size={14} /></Link></article>
    <article className="stl4-support-card"><header><BookOpen /><span>02</span><div><h3><Link href="/help/reading">阅读文献</Link></h3><p>进入图书或文献页面，在线阅读正文，查看章节结构与来源信息。</p></div></header><div className="stl4-support-reader-demo"><div><strong>目录</strong>{["导论", "第一章 技术与社会", "第二章 权力的形态", "第三章 主体与现代性"].map((label, index) => <button type="button" key={label} aria-pressed={readingStep === index} onClick={() => setReadingStep(index)}>{label}</button>)}</div><div><img src="/editorial/stl4-support-reading-final-r2.png" alt="阅读器排版示意，非当前馆藏" width={355} height={182}/><span className="sr-only" aria-live="polite">目录操作示意：{readingHints[readingStep]}</span></div></div></article>
    <article className="stl4-support-card"><header><Quote /><span>03</span><div><h3><Link href="/help/citation">引用与导出</Link></h3><p>查看来源位置、复制标准引注格式、或导出参考文献，规范使用学术资料。</p></div></header><SupportCitationExample compact /></article>
  </div></section><section className="stl4-support-links" aria-label="帮助主题"><Link href="/help?section=content"><BookOpen /><span><strong>用途与内容组织</strong><small>本书库收录社会理论领域的经典与当代著作，按照书、主题、学者与理论流派组织，帮助读者系统探索与比较。</small></span><ArrowRight size={16} /></Link><Link href="/help/source"><Layers /><span><strong>原文与内容身份</strong><small>区分原文扫描、印刷页与数字文本。明确人工整理与 AI 生成内容的身份与适用范围。</small></span><ArrowRight size={16} /></Link><Link href="/help?section=faq"><CircleHelp /><span><strong>常见问题</strong><small>搜索、阅读、引用、账户与权限等常见问题的解答。</small></span><ArrowRight size={16} /></Link><Link href="/feedback"><MessageCircle /><span><strong>来源纠错与使用反馈</strong><small>发现内容问题？提供修改建议或反馈你的使用体验。</small></span><ArrowRight size={16} /></Link></section></>;
}

export function SupportFaq() {
  const [query, setQuery] = useState(""), [category, setCategory] = useState("all");
  const normalized = query.trim().toLocaleLowerCase();
  const rows = supportFaqs.filter(row => (category === "all" || row.category === category) && `${row.question}${row.answer}`.toLocaleLowerCase().includes(normalized));
  return <section className="stl4-support-section stl4-support-faq"><h2>常见问题</h2><p className="stl4-support-lead">以下是使用过程中常见的问题，也可以搜索说明文字。</p><form role="search" aria-label="搜索常见问题" onSubmit={event => event.preventDefault()}><label><Search size={18} /><span className="sr-only">搜索问题或关键词</span><input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索问题或关键词…" /></label><button type="submit">搜索</button></form><div className="stl4-faq-filters" aria-label="常见问题分类">{[["all", "全部"], ["search", "搜索与阅读"], ["citation", "引用与导出"], ["account", "账户与隐私"]].map(([value, label]) => <button key={value} type="button" aria-pressed={category === value} onClick={() => setCategory(value)}>{label}</button>)}</div><p className="stl4-faq-count" role="status">{rows.length ? `找到 ${rows.length} 条说明` : "没有找到匹配的问题"}</p>{rows.map(row => <details key={row.id}><summary>{row.question}</summary><div><p>{row.answer}</p><Link href={`/help/${row.article}`}>阅读相关说明 <ArrowRight size={14} /></Link></div></details>)}{!rows.length ? <div className="stl4-support-no-answer"><CircleHelp size={30} /><h3>没有找到答案？</h3><p>可以换一个关键词，或直接向我们说明遇到的问题。</p><button type="button" onClick={() => { setQuery(""); setCategory("all"); }}>显示全部问题</button><Link className="stl4-support-primary" href="/feedback?category=usage">提交问题 <ArrowRight size={16} /></Link></div> : null}</section>;
}
