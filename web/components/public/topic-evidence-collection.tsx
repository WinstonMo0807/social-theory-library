"use client";

import { useState } from "react";
import type { Work } from "@/lib/data";
import { topicEvidenceRows, type EvidenceCurationItem } from "@/lib/api/evidence-curation.types";
import { EvidenceCurationView } from "./evidence-curation-view";

export function TopicEvidenceCollection({ items, works, selectedKey }: { items: EvidenceCurationItem[]; works: Work[]; selectedKey?: string }) {
  const [ordering, setOrdering] = useState<"book" | "editorial">("book");
  const rows = topicEvidenceRows(items, ordering);
  return <div className="topic-evidence-collection"><header><h2>相关原文</h2><select aria-label="原文排序" data-preview-control value={ordering} onChange={event => setOrdering(event.target.value as "book" | "editorial")}><option value="book">按书籍排序</option><option value="editorial">按编辑顺序</option></select></header><EvidenceCurationView items={rows.map(row => row.item)} presentation="topic" works={works} rowIndices={rows.map(row => row.index)} selectedKey={selectedKey}/></div>;
}
