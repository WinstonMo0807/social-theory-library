"use client";

import { Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import { SectionHeading } from "./ui";

type CitationStyle = "gbt7714-2025" | "apa" | "chicago" | "mla" | "harvard";
type CitationPayload = Record<CitationStyle, string> & { csl: Record<string, unknown> };

const labels: [CitationStyle, string][] = [
  ["gbt7714-2025", "GB/T 7714—2025"],
  ["apa", "APA"],
  ["chicago", "Chicago"],
  ["mla", "MLA"],
  ["harvard", "Harvard"],
];

export function WorkCitationPanel({ editionId }: { editionId?: string }) {
  const [style, setStyle] = useState<CitationStyle>("gbt7714-2025");
  const [payload, setPayload] = useState<CitationPayload | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!editionId) return;
    let cancelled = false;
    apiRequest<CitationPayload>(`/catalog/editions/${editionId}/citations/`)
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [editionId]);

  async function copy() {
    if (!payload) return;
    await navigator.clipboard.writeText(payload[style]);
    setMessage("已复制");
  }

  function exportCsl() {
    if (!payload) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload.csl, null, 2)], {
      type: "application/json;charset=utf-8",
    }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "citation.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="panel citation-panel" id="citation">
      <SectionHeading title="引用本书库版本" />
      <div className="citation-tabs" role="tablist" aria-label="引用格式">
        {labels.map(([value, label]) => (
          <button
            className={style === value ? "active" : ""}
            id={`citation-tab-${value}`}
            type="button"
            role="tab"
            aria-selected={style === value}
            aria-controls="work-citation-text"
            key={value}
            onClick={() => setStyle(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <blockquote
        id="work-citation-text"
        role="tabpanel"
        aria-labelledby={`citation-tab-${style}`}
      >
        {payload?.[style] || "正在根据馆藏元数据生成引用……"}
      </blockquote>
      <div className="citation-actions">
        <button className="button secondary" type="button" onClick={copy} disabled={!payload}><Copy size={15} /> 复制引用</button>
        <button className="button secondary" type="button" onClick={exportCsl} disabled={!payload}>导出 CSL JSON</button>
      </div>
      <p aria-live="polite">{message || "进入阅读器后可生成带具体页码的引用。"}</p>
    </section>
  );
}
