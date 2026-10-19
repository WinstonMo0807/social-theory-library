import Link from "next/link";
import { ArrowLeft, CircleAlert } from "lucide-react";
import { notFound } from "next/navigation";
import { SiteFooter } from "@/components/site-footer";
import { SupportSourceStatus } from "@/components/public/support-source-status";
import { SupportHero } from "@/components/public/support-hero";
import { SupportCitationExample } from "@/components/public/support-citation-example";
import { helpArticles } from "@/lib/support-content";
import { loadSiteChromeConfig } from "@/lib/api/site.server";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) { const { slug } = await params; return { title: Object.hasOwn(helpArticles, slug) ? helpArticles[slug].title : "帮助文章" }; }
export default async function HelpArticlePage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ source?: string }> }) {
  const [{ slug }, chrome, query] = await Promise.all([params, loadSiteChromeConfig(), searchParams]); if (!Object.hasOwn(helpArticles, slug)) notFound(); const article = helpArticles[slug];
  return <><div className="stl4-support-page stl4-support-article"><SupportHero config={chrome.config} title={article.title} intro={article.intro} article />{chrome.unavailable ? <p className="stl4-support-status" role="status">网站配置暂时无法加载，帮助正文仍可阅读。</p> : null}<div className="stl4-support-article-layout"><article aria-label={article.title}>{slug === "source" ? <SupportSourceStatus source={query.source || ""} /> : null}{article.steps.map((step, index) => <section className="stl4-help-step" id={step.id} key={step.id}><span className="stl4-help-step-number" aria-hidden="true">{index + 1}</span><div><h2>{step.title}</h2><p>{step.body}</p>{slug === "citation" && step.id === "copy" ? <SupportCitationExample /> : null}</div></section>)}<div className="stl4-support-notice"><CircleAlert size={26} /><div><h3>{slug === "citation" ? "如遇页码不符" : "仍有问题？"}</h3><p>请提供可核对的位置与问题说明。</p></div><Link className="stl4-support-primary" href={`/feedback?category=${slug === "source" || slug === "citation" ? "content" : "usage"}&path=${encodeURIComponent(`/help/${slug}`)}`}>提交反馈</Link></div></article><aside className="stl4-help-toc" aria-label="本文目录"><h2>本文目录</h2><ol>{article.steps.map(step => <li key={step.id}><a href={`#${step.id}`}>{step.title}</a></li>)}</ol><Link href="/help"><ArrowLeft size={16} />返回帮助首页</Link></aside></div><Link className="stl4-support-back" href="/help"><ArrowLeft size={16} />返回帮助首页</Link></div><SiteFooter /></>;
}
