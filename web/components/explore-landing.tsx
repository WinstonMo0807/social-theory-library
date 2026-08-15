/* eslint-disable @next/next/no-img-element -- These decorative assets are pre-sized local WebP files and do not require a runtime image transformer. */
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";

const entries = [
  {
    href: "/explore/original",
    index: "01",
    title: "原文检索",
    description: "从题名、责任者和馆藏全文进入，定位可以核对、复制与引用的具体页面。",
    points: ["关键词与书目信息定位", "全文段落与纸本页码", "从结果直接回到阅读器"],
    action: "进入原文检索",
    visual: "/explore/explore-magnifier-v1.webp",
    visualClass: "magnifier",
    featured: false,
  },
  {
    href: "/explore/opinions",
    index: "02",
    title: "观点检索",
    description: "用自己的语言描述问题，从馆藏原文中发现相近表达、相关论证和可核查证据。",
    points: ["最相关原文优先", "更多证据与并排核对", "语义不可用时明确降级"],
    action: "开始观点检索",
    visual: "/explore/explore-door-v1.webp",
    visualClass: "door",
    featured: true,
  },
  {
    href: "/explore/ask",
    index: "03",
    title: "向书库提问",
    description: "基于已发布馆藏组织回答，并逐条保留来源，方便继续阅读与回到原文。",
    points: ["连续追问", "馆藏来源逐条展开", "模型未配置时停止生成"],
    action: "开始提问",
    visual: "/explore/explore-dialogue-v1.webp",
    visualClass: "dialogue",
    featured: false,
  },
] as const;

export function ExploreLanding() {
  return (
    <>
      <main className="page-shell explore-landing-page">
        <section className="explore-landing-hero">
          <img
            className="explore-landing-hero-image"
            src="/explore/explore-architecture-hero-v1.webp"
            alt=""
            width="1913"
            height="822"
            fetchPriority="high"
          />
          <div className="explore-landing-copy">
            <p className="explore-landing-kicker">Texts, concepts, and debate.</p>
            <h1>在原典与论争之间</h1>
            <span aria-hidden="true" />
            <p>从原文进入经典文本，从观点连接问题意识，也可以向已发布馆藏继续提问。</p>
          </div>
        </section>

        <nav className="explore-entry-grid" aria-label="选择探索方式">
          {entries.map((entry) => (
              <Link className={`explore-entry-card ${entry.visualClass}`} href={entry.href} key={entry.href}>
                <span className="explore-entry-index">{entry.index}</span>
                {entry.featured ? <span className="explore-entry-badge">主要功能</span> : null}
                <h2>{entry.title}</h2>
                <p>{entry.description}</p>
                <ul>
                  {entry.points.map((point) => <li key={point}>{point}</li>)}
                </ul>
                <strong>{entry.action}<ArrowRight size={18} aria-hidden="true" /></strong>
                <img
                  className="explore-entry-visual"
                  src={entry.visual}
                  alt=""
                  width="520"
                  height="520"
                  loading="lazy"
                />
              </Link>
          ))}
        </nav>
      </main>
      <SiteFooter />
    </>
  );
}
