import Link from "next/link";
import { ChevronDown } from "lucide-react";
import { supportSections, type SupportSection } from "@/lib/support-content";

export function SupportHero({ title, intro, article = false, variant = "support" }: { title: string; intro: string; article?: boolean; variant?: "support" | "about" | "feedback" }) {
  const image = article ? "article" : variant;
  return <section className="stl4-support-hero" data-hero-variant={image}><div><nav className="stl4-support-breadcrumb" aria-label="面包屑"><Link href="/">首页</Link><span aria-hidden="true">›</span>{article ? <><Link href="/help">使用帮助</Link><span aria-hidden="true">›</span></> : variant === "feedback" ? <><Link href="/about">关于</Link><span aria-hidden="true">›</span></> : null}<span aria-current="page">{article ? title : variant === "about" ? "关于书库" : variant === "feedback" ? title : "关于"}</span></nav><h1>{title}</h1><p>{intro}</p></div><picture><source media="(max-width: 720px)" srcSet={`/editorial/stl4-${image === "feedback" ? "support" : image}-mobile-final-r2.png`} /><img src={`/editorial/stl4-${image}-desktop-final-r2.png`} alt="阳光下的书桌、打开的书、笔筒与书架" width={image === "about" ? 688 : image === "article" ? 668 : image === "feedback" ? 666 : 703} height={image === "about" ? 213 : image === "article" ? 207 : image === "feedback" ? 200 : 217} /></picture></section>;
}

export function SupportNavigation({ current }: { current: SupportSection }) {
  const href = (key: SupportSection) => key === "feedback" ? "/feedback" : `/help?section=${key}`;
  return <><nav className="stl4-support-tabs" aria-label="帮助栏目">{supportSections.map(([key, label]) => <Link key={key} href={href(key)} aria-current={key === current ? "page" : undefined}>{label}</Link>)}</nav><nav className="stl4-support-mobile-nav" aria-label="手机帮助栏目">{supportSections.map(([key, label]) => <details key={key}><summary className={key === current ? "is-active" : undefined}>{label}<ChevronDown size={16} /></summary><Link href={href(key)} aria-current={key === current ? "page" : undefined}>浏览{label}</Link></details>)}</nav></>;
}
