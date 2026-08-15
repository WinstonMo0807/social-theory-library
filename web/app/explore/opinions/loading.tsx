"use client";

import { useEffect, useState } from "react";

export default function OpinionSearchLoading() {
  const [stage, setStage] = useState<"retrieval" | "comparison">("retrieval");

  useEffect(() => {
    const timer = window.setTimeout(() => setStage("comparison"), 900);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <main className="page-shell semantic-loading-page">
      <section className="semantic-loading-status" role="status" aria-live="polite" aria-atomic="true">
        <span className="semantic-loading-indicator" aria-hidden="true" />
        <div>
          <p>{stage === "retrieval" ? "正在匹配馆藏原文……" : "正在比较候选原文……"}</p>
          <small>{stage === "retrieval" ? "先从可检索馆藏中召回候选" : "整理排序和前后文后再显示结果"}</small>
        </div>
      </section>
    </main>
  );
}
