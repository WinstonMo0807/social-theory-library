import Link from "next/link";
import { ArrowRight, BookOpen } from "lucide-react";
import { normalizePublicResourceUrl } from "@/lib/api";
import type { HomeCard } from "@/lib/api/home.types";
import { EditorialByline } from "./editorial-directory";
import styles from "./home-curated-section.module.css";

export function HomeCuratedSection({area, cards}: {area: "featured" | "scholars" | "topics"; cards: HomeCard[]}) {
  const content = {featured: ["特别策划", "Featured issues", "/recommendations"], scholars: ["学者聚焦", "Scholars", "/scholars"], topics: ["探索主题", "Topics", "/topics"]}[area];
  const shown = cards.filter(row => row.visible && row.available);
  return <section className={`stl4-home-section ${styles.section}`} data-edit-section={area} aria-label={content[0]}>
    <header className="stl4-home-heading"><h2>{content[0]} <small>{content[1]}</small></h2><Link href={content[2]}>查看全部 <ArrowRight size={15}/></Link></header>
    {shown.length ? <div className={area === "featured" ? "stl4-issue-grid" : area === "scholars" ? "stl4-scholar-grid" : "stl4-topic-grid"}>{shown.map((row,index) => <Link key={row.id} href={row.href} className={area === "featured" ? `stl4-issue-card${index === 0 ? " stl4-issue-lead" : ""}` : area === "scholars" ? `stl4-scholar-card ${styles.scholar}` : `stl4-topic-card ${styles.topic}`} data-preview-item-id={row.id}>
      {row.image_url ? <img src={normalizePublicResourceUrl(row.image_url)} alt="" loading="lazy"/> : <div className="stl4-image-missing" aria-label="尚未提供配图"><BookOpen size={28} strokeWidth={1}/></div>}
      <div className={area === "featured" ? "stl4-issue-copy" : styles.copy}>{area === "featured" ? <span className="stl4-issue-label">{row.label}</span> : null}<h3>{row.title}</h3><p>{row.description}</p>{area==="featured"&&index===0&&row.curator?.name?<div className="stl4-issue-byline"><EditorialByline curator={row.curator} date={null}/></div>:null}<ArrowRight size={16} aria-hidden="true"/></div>
    </Link>)}</div> : <div className="stl4-home-state"><BookOpen size={24} strokeWidth={1}/><p>此栏目暂未设置公开内容。</p></div>}
  </section>;
}
