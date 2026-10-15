import Link from "next/link";
import { ArrowRight, Search } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";

const entries = [
  {
    href: "/explore/original",
    title: "原文检索",
    description: "按书名、作者、材料类型或年份查找具体文献，进入思想发生的现场。",
    imageClass: "book",
  },
  {
    href: "/explore/opinions",
    title: "观点检索",
    description: "围绕核心概念、理论观点或学术论争，了解不同立场的论证与回应。",
    imageClass: "shelves",
  },
  {
    href: "/explore/ask",
    title: "向书库提问",
    description: "以现实问题或研究兴趣为起点，获得与社会理论相关的文献、概念与讨论路径。",
    imageClass: "desk",
  },
] as const;

export function ExploreLanding() {
  return (
    <>
      <div className="stl4-explore-page">
        <section className="stl4-explore-hero" aria-labelledby="explore-title">
          <div className="stl4-explore-hero-media" aria-hidden="true" />
          <div className="stl4-explore-hero-copy">
            <h1 id="explore-title">在原典与论争之间</h1>
            <p>从经典文献到当代争论，在文本、观点与问题之间自由穿行，发现社会理论的思想脉络与现实回响。</p>
            <form className="stl4-explore-search" action="/explore/original" method="get">
              <Search size={17} strokeWidth={1.7} aria-hidden="true" />
              <label className="sr-only" htmlFor="explore-query">搜索书名、作者、概念或主题</label>
              <input id="explore-query" name="q" type="search" placeholder="搜索书名、作者、概念、主题……" />
              <button type="submit">搜索</button>
            </form>
          </div>
        </section>

        <section className="stl4-explore-entries" aria-labelledby="explore-entries-title">
          <div className="stl4-explore-section-heading">
            <h2 id="explore-entries-title">探索入口</h2>
          </div>
          <div className="stl4-explore-entry-grid">
            {entries.map((entry) => (
              <Link href={entry.href} className="stl4-explore-entry" key={entry.href}>
                <span className={`stl4-explore-entry-image ${entry.imageClass}`} aria-hidden="true" />
                <span className="stl4-explore-entry-body">
                  <strong>{entry.title}</strong>
                  <span>{entry.description}</span>
                  <ArrowRight size={18} strokeWidth={1.5} aria-hidden="true" />
                </span>
              </Link>
            ))}
          </div>
        </section>
      </div>
      <SiteFooter />
    </>
  );
}
