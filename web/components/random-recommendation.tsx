"use client";

import Link from "next/link";
import { ArrowRight, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Work } from "@/lib/data";
import { ArchitecturalImage, BookCover } from "./ui";

export function RandomRecommendation({ works, title = "为你推荐" }: { works: Work[]; title?: string }) {
  const [offset, setOffset] = useState(0);
  const [swapping, setSwapping] = useState(false);
  const timerRef = useRef<number | null>(null);
  const index = offset % Math.max(works.length, 1);
  const work = works[index];

  useEffect(() => () => {
    if (timerRef.current) window.clearTimeout(timerRef.current);
  }, []);

  function switchRecommendation() {
    if (works.length < 2 || swapping) return;
    setSwapping(true);
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      setOffset((value) => value + 1);
      setSwapping(false);
      timerRef.current = null;
    }, 110);
  }

  return (
    <section className="random-book panel">
      <header className="random-heading">
        <h2>{title}</h2>
        <button type="button" onClick={switchRecommendation} disabled={works.length < 2 || swapping}>
          <span>换一本</span><RefreshCw className={swapping ? "spin" : ""} size={14} />
        </button>
      </header>
      {work ? (
        <Link className="random-image" href={`/works/${work.slug}`} aria-label={`查看《${work.title}》详情`}>
          {work.coverImage ? <BookCover work={work} size="large" /> : <ArchitecturalImage compact />}
        </Link>
      ) : (
        <div className="random-image" aria-hidden="true"><ArchitecturalImage compact /></div>
      )}
      {work ? (
        <div className={`random-recommendation-content ${swapping ? "is-leaving" : "is-entering"}`} key={`${work.id}-${offset}`} aria-live="polite">
          <p className="eyebrow">{work.school}</p>
          <h3>{work.title}</h3>
          <p className="book-author">{work.author}</p>
          <p className="muted-row">{work.year} · {work.kind}</p>
          <Link className="button secondary" href={`/reader/${work.id}`}>
            立即阅读 <ArrowRight size={16} />
          </Link>
        </div>
      ) : <p className="empty-state">馆藏发布后会在这里生成推荐。</p>}
    </section>
  );
}
