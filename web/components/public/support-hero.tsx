import Link from "next/link";
import type { SiteConfig } from "@/lib/site-config";
import { ChevronDown } from "lucide-react";
import { supportSections, type SupportSection } from "@/lib/support-content";

export function SupportHero({ config, title, intro, article = false }: { config: SiteConfig; title: string; intro: string; article?: boolean }) {
  return <section className="stl4-support-hero"><div><nav className="stl4-support-breadcrumb" aria-label="面包屑"><Link href="/">首页</Link><span aria-hidden="true">›</span>{article ? <><Link href="/help">使用帮助</Link><span aria-hidden="true">›</span></> : null}<span aria-current="page">{title}</span></nav><h1>{title}</h1><p>{intro}</p></div><img src={config.home_hero_image || "/editorial/stl4-reading-room.png"} alt={config.home_hero_alt || "阳光下的书桌与书架"} width={1774} height={887} /></section>;
}

export function SupportNavigation({ current }: { current: SupportSection }) {
  const href = (key: SupportSection) => key === "feedback" ? "/feedback" : `/help?section=${key}`;
  return <><nav className="stl4-support-tabs" aria-label="帮助栏目">{supportSections.map(([key, label]) => <Link key={key} href={href(key)} aria-current={key === current ? "page" : undefined}>{label}</Link>)}</nav><nav className="stl4-support-mobile-nav" aria-label="手机帮助栏目">{supportSections.map(([key, label]) => <details key={key}><summary className={key === current ? "is-active" : undefined}>{label}<ChevronDown size={16} /></summary><Link href={href(key)} aria-current={key === current ? "page" : undefined}>浏览{label}</Link></details>)}</nav></>;
}
