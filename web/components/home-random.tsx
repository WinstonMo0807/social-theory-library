"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Shuffle } from "lucide-react";
import type { Scholar, Work } from "@/lib/data";
import { ScholarCard } from "@/components/ui";
import { CollectionLink } from "@/components/collection-link";

export function HomeScholars({ scholars }: { scholars: Scholar[] }) {
  const [offset, setOffset] = useState(0);
  const shown = scholars.slice(offset).concat(scholars.slice(0, offset)).slice(0, 6);
  return <section className="v307-home-panel home-scholars" data-edit-section="scholars"><header className="v307-section-heading"><h2>学者聚焦 <small>Scholars</small></h2><div><Link href="/scholars">查看全部</Link><button className="button secondary" disabled={scholars.length < 2} onClick={() => setOffset(current => (current + 1 + Math.floor(Math.random() * (scholars.length - 1))) % scholars.length)}><Shuffle size={16} />随机认识一位学者</button></div></header>{shown.length ? <div className="v307-scholar-grid" aria-live="polite">{shown.map(scholar => <ScholarCard key={scholar.slug} scholar={scholar} />)}</div> : <p className="empty-state">学者档案发布后会在这里显示。</p>}</section>;
}

export function HomeRandom({ works }: { works: Work[] }) {
  const [index, setIndex] = useState<number | null>(null);
  if (!works.length) return null;
  const work = index === null ? null : works[index];
  return <section className="v307-home-random"><div><span className="eyebrow">A serendipitous encounter</span><h2>{work ? work.title : "遇见一本好书"}</h2><p aria-live="polite">{work ? `${work.author} · ${work.year || "出版年未详"}` : "随机打开一本书，遇见未曾预期的思想。"}</p></div><button className="button secondary" onClick={() => setIndex(current => current === null ? Math.floor(Math.random() * works.length) : works.length === 1 ? 0 : (current + 1 + Math.floor(Math.random() * (works.length - 1))) % works.length)}><Shuffle size={16} />{work ? "再换一本" : "随机推荐"}</button>{work ? <CollectionLink className="button secondary" href={`/works/${work.slug}`}>查看馆藏 <ArrowRight size={15} /></CollectionLink> : null}</section>;
}
