import Link from "next/link";
import { ArrowRight, BookOpen, FileText, Highlighter, Search } from "lucide-react";
import type { AboutPageBlock, SiteStats } from "@/lib/api/site.types";
import type { SiteConfig } from "@/lib/site-config";

export function AboutPublicView({ config, stats, about }: { config: SiteConfig; stats: SiteStats; about: { configured: boolean; blocks: AboutPageBlock[] } }) {
  const byKey = new Map(about.blocks.map((block) => [block.key, block]));
  const enabled = (key: string) => !about.configured || byKey.has(key);
  const value = (key: string, field: "title" | "body" | "action_label" | "action_href", fallback: string) => {
    const block = byKey.get(key);
    return block ? block[field] : about.configured ? "" : fallback;
  };
  const hero = config.home_hero_image || "/editorial/stl4-reading-room.png";
  const sourceSummary = stats.documents > 0 ? `当前公开馆藏 ${stats.documents.toLocaleString("zh-CN")} 种` : "当前公开馆藏正在持续整理";
  const cards = [
    ["about-feature-source", "我们收录什么", `${value("about-feature-source", "body", "以社会理论、社会科学研究和可核对的原文资料为入口，区分作品、出版版本与阅读文件。")}（${sourceSummary}）`, Search, "/explore"],
    ["about-feature-reading", "如何阅读与引用", value("about-feature-reading", "body", "从检索结果回到 Reader，核对完整语境、PDF 页码和当前可访问的版本。"), BookOpen, "/help/reading"],
    ["about-feature-knowledge", "内容与来源", value("about-feature-knowledge", "body", "学者、理论、主题和策划内容来自已发布的馆内关系，机器建议不会直接成为公开事实。"), FileText, "/help/source"],
    ["about-why", "为什么建设这座书库", value("about-why", "body", config.about_why_body), Highlighter, "/help"],
  ] as const;
  return <div className="stl4-about-page"><nav className="stl4-support-breadcrumb" aria-label="面包屑"><Link href="/">首页</Link><span>/</span><strong>关于书库</strong></nav><section className="stl4-about-hero" data-edit-section="about"><div><p className="stl4-support-kicker">社会理论书库</p><h1>{value("about-intro", "title", "关于社会理论书库")}</h1><p>{value("about-intro", "body", config.about_body)}</p></div><img src={hero} alt={config.home_hero_alt || "书桌与书架"} /></section><section className="stl4-about-card-grid">{cards.filter(([key]) => enabled(key)).map(([key, title, body, Icon, href]) => <article key={key} data-edit-section={key}><Icon size={20} /><h2>{title}</h2><p>{body}</p><Link href={href}>了解更多 <ArrowRight size={14} /></Link></article>)}</section><section className="stl4-about-further"><header><p className="stl4-support-kicker">进一步了解</p><h2>公开阅读，也保留边界</h2></header><div><Link href="/help/source"><span><strong>来源与版本</strong><small>阅读文件、OCR 与页码定位</small></span><ArrowRight size={15} /></Link><Link href="/help/account"><span><strong>私人资料</strong><small>笔记、研究会话与个人记忆</small></span><ArrowRight size={15} /></Link><Link href="/feedback"><span><strong>告诉我们</strong><small>提交内容、功能或无障碍反馈</small></span><ArrowRight size={15} /></Link></div></section><section className="stl4-about-boundary"><p>书库提供检索、阅读和引用入口；OCR、分类和检索结果仍需回到原始页面核对。</p><p>个人笔记、标注、研究会话和上传资料默认只对本人可见。</p></section></div>;
}
