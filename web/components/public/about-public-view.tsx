import Link from "next/link";
import { ChevronRight, BookOpen, Database, FileText, LockKeyhole, Search } from "lucide-react";
import type { AboutPageBlock, SiteStats } from "@/lib/api/site.types";
import type { SiteConfig } from "@/lib/site-config";
import { publicSiteText } from "@/lib/site-content";
import { SiteCopyLink } from "./site-public-copy";
import { SupportHero } from "./support-hero";

export function AboutPublicView({ config, about, unavailable = false }: { config: SiteConfig; stats?: SiteStats; about: { configured: boolean; blocks: AboutPageBlock[] } | null; unavailable?: boolean }) {
  const intro=publicSiteText(config,about,"about");
  const why=about?.blocks.some(row=>row.key==="about-why")?publicSiteText(config,about,"about-why"):null;
  const cards = [["about-feature-source",BookOpen],["about-feature-reading",FileText],["about-feature-knowledge",Database]] as const;
  return <div className="stl4-support-page stl4-about-page"><SupportHero variant="about" title={intro?.title || "关于社会理论书库"} intro={intro?.body||""} />
    {unavailable ? <p className="stl4-support-status" role="alert">网站介绍暂时无法完整加载。未能读取的已发布内容没有用示例替代，可稍后重新打开本页。</p> : null}
    <section className="stl4-about-card-grid" aria-label="关于书库">{cards.map(([key,Icon])=>{const copy=publicSiteText(config,about,key);return copy?<article key={key} data-edit-section={key}><Icon size={38} strokeWidth={1.5}/><div><h2>{copy.title}</h2><p style={{whiteSpace:"pre-line"}}>{copy.body}</p><SiteCopyLink label={copy.action_label} href={copy.action_href}/></div></article>:null;})}<article className="stl4-about-further"><h2>进一步了解</h2><Link href="/help">使用帮助 <ChevronRight size={18} /></Link><Link href="/help/account#site-privacy">隐私说明 <ChevronRight size={18} /></Link><Link href="/feedback">提交反馈 <ChevronRight size={18} /></Link>{why?.body ? <details><summary>{why?.title || "为什么建设这座书库"}</summary><p>{why?.body}</p></details> : null}</article></section>
    <section className="stl4-about-boundary" aria-label="访问边界"><p><Search size={29} />访客可以搜索、阅读、下载、复制和引用。</p><p><LockKeyhole size={29} />私人笔记与研究需登录后使用。</p></section>
  </div>;
}
