import Link from "next/link";
import { ArrowRight, BookOpen, Database, FileText, LockKeyhole, Search } from "lucide-react";
import type { AboutPageBlock, SiteStats } from "@/lib/api/site.types";
import type { SiteConfig } from "@/lib/site-config";
import { SupportHero } from "./support-hero";

export function AboutPublicView({ config, about, unavailable = false }: { config: SiteConfig; stats?: SiteStats; about: { configured: boolean; blocks: AboutPageBlock[] } | null; unavailable?: boolean }) {
  const byKey = new Map(about?.blocks.map(block => [block.key, block]) ?? []);
  const enabled = (key: string) => Boolean(about && (!about.configured || byKey.has(key)));
  const text = (key: string, field: "title" | "body", fallback: string) => byKey.get(key)?.[field] ?? (about?.configured ? "" : fallback);
  const cards = [
    ["about-feature-source", "我们收录什么", "书库围绕社会理论与社会科学组织重要图书、研究成果和相关文献。作品、出版版本与数字文件分别记录，提供书目信息、可访问的原文与知识关联，便于阅读、下载、复制和引用。", BookOpen],
    ["about-feature-reading", "如何阅读与引用", "从书目或检索结果打开当前可访问的原文，核对作者、版本、页码和完整语境。来源文本与编者的介绍、评述和导读分开呈现，帮助读者在阅读原文的基础上形成自己的理解。", FileText],
    ["about-feature-knowledge", "内容与来源", "每个公开内容入口对应已发布的信息。扫描页面、OCR 文字与编者说明各有用途；识别文字可能有误，机器候选关系仍需核对。介绍与导读提供阅读参考，不替代原作者的文本。", Database],
  ] as const;
  return <div className="stl4-support-page stl4-about-page"><SupportHero config={config} title={text("about-intro", "title", "关于社会理论书库") || "关于社会理论书库"} intro={text("about-intro", "body", "连接思想、开放知识，服务研究与公众。")} />
    {unavailable ? <p className="stl4-support-status" role="alert">网站介绍暂时无法完整加载。未能读取的已发布内容没有用示例替代，可稍后重新打开本页。</p> : null}
    <section className="stl4-about-card-grid" aria-label="关于书库">{cards.filter(([key]) => enabled(key)).map(([key, title, body, Icon]) => <article key={key} data-edit-section={key}><Icon size={38} strokeWidth={1.5} /><div><h2>{text(key, "title", title) || title}</h2><p>{text(key, "body", body)}</p></div></article>)}<article className="stl4-about-further"><h2>进一步了解</h2><Link href="/help">使用帮助 <ArrowRight size={18} /></Link><Link href="/help/account">隐私说明 <ArrowRight size={18} /></Link><Link href="/feedback">提交反馈 <ArrowRight size={18} /></Link>{byKey.get("about-why")?.body ? <details><summary>{byKey.get("about-why")?.title || "为什么建设这座书库"}</summary><p>{byKey.get("about-why")?.body}</p></details> : null}</article></section>
    <section className="stl4-about-boundary" aria-label="访问边界"><p><Search size={29} />访客可以搜索、阅读、下载、复制和引用。</p><p><LockKeyhole size={29} />私人笔记与研究需登录后使用。</p></section>
  </div>;
}
