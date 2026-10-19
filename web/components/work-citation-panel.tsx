"use client";

import { Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import { SectionHeading } from "./ui";
import { Button } from "./ui/controls";
import { Tabs } from "./ui/tabs";
import { Tooltip } from "./ui/tooltip";
import { SharedCitationButton } from "./shared-citation-overlay";

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
  const [result, setResult] = useState<{ editionId: string; payload?: CitationPayload; error?: string } | null>(null);
  const payload = result && result.editionId === editionId ? result.payload : undefined;
  const citationError = result && result.editionId === editionId ? result.error : undefined;
  const [attempt, setAttempt] = useState(0);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!editionId) return;
    const controller = new AbortController();
    apiRequest<CitationPayload>(`/catalog/editions/${editionId}/citations/`, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]), cache: "no-store" })
      .then((data) => {
        if (!controller.signal.aborted) setResult({ editionId, payload: data });
      })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setResult({ editionId, error: reason instanceof Error ? reason.message : "引用读取失败。" }); });
    return () => {
      controller.abort();
    };
  }, [editionId, attempt]);

  async function copy() {
    if (!editionId) return;
    try {
      const current = await apiRequest<CitationPayload>(`/catalog/editions/${editionId}/citations/`, { cache: "no-store", signal: AbortSignal.timeout(30000) });
      setResult({ editionId, payload: current });
      try { await navigator.clipboard.writeText(current[style]); setMessage("已复制"); }
      catch { setMessage("浏览器未允许复制，请选择上方引用文字手动复制。"); }
    } catch (reason) { setResult({ editionId, error: reason instanceof Error ? reason.message : "来源暂不可用，请重试。" }); setMessage("引用未复制，来源需重新核对。"); }
  }

  async function exportCsl() {
    if (!editionId) return;
    let current: CitationPayload;
    try { current = await apiRequest<CitationPayload>(`/catalog/editions/${editionId}/citations/`, { cache: "no-store", signal: AbortSignal.timeout(30000) }); setResult({ editionId, payload: current }); }
    catch (reason) { setResult({ editionId, error: reason instanceof Error ? reason.message : "来源暂不可用，请重试。" }); return; }
    const url = URL.createObjectURL(new Blob([JSON.stringify(current.csl, null, 2)], {
      type: "application/json;charset=utf-8",
    }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "citation.json";
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <section className="panel citation-panel" id="citation">
      <SectionHeading title="引用本书库版本" />
      <Tabs className="citation-tabs" aria-label="引用格式" value={style} onChange={setStyle}
        items={labels.map(([value, label]) => ({ value, label, id: `citation-tab-${value}`, panelId: "work-citation-text" }))} />
      <blockquote
        id="work-citation-text"
        role="tabpanel"
        aria-labelledby={`citation-tab-${style}`}
      >
        {payload?.[style] || citationError || (editionId ? "正在根据馆藏元数据生成引用……" : "当前尚无可引用的公开版本。")}
      </blockquote>
      <div className="citation-actions">
        {citationError ? <Button className="button secondary" onClick={() => setAttempt(value => value + 1)}>重试读取引用</Button> : null}
        <Button className="button secondary" onClick={copy} disabled={!payload}><Copy size={15} /> 复制引用</Button>
        <Tooltip content="导出当前馆藏版本的结构化引用资料"><Button className="button secondary" onClick={exportCsl} disabled={!payload}>导出 CSL JSON</Button></Tooltip>
        {editionId ? <SharedCitationButton editionId={editionId} className="button secondary">更多格式与选材</SharedCitationButton> : null}
      </div>
      <p aria-live="polite">{message || "进入阅读器后可生成带具体页码的引用。"}</p>
    </section>
  );
}
