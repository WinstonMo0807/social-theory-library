"use client";
import { useState } from "react";
import { Shuffle } from "lucide-react";
import { ScholarCard } from "@/components/ui";
import type { Scholar } from "@/lib/data";
export function ScholarDirectoryRecommendations({ recommended, pool }: {recommended: Scholar[]; pool: Scholar[]}) {
  const [selected, setSelected] = useState<Scholar | null>(null);
  if (!recommended.length && !pool.length) return null;
  const initial = recommended.length ? recommended : pool.slice(0,4);
  const shown = selected ? [selected, ...initial.filter(row => row.slug !== selected.slug)].slice(0, 4) : initial;
  return <section className="knowledge-section"><header className="section-heading"><h2>{recommended.length ? "学者推荐" : "馆藏学者"}</h2><button className="button secondary" type="button" disabled={pool.length < 2} onClick={() => {const candidates = pool.filter(row => row.slug !== (selected?.slug || shown[0]?.slug)); if (candidates.length) setSelected(candidates[Math.floor(Math.random() * candidates.length)]);}}><Shuffle size={16}/>随机认识一位学者</button></header><div className="knowledge-scholar-featured" aria-live="polite">{shown.map(row => <ScholarCard scholar={row} key={row.slug}/>)}</div></section>;
}
