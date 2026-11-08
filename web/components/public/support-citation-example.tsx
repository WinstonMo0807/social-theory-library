"use client";

import { useState } from "react";
import { Copy, Download } from "lucide-react";
import type { CitationStyle } from "@/components/reader/types";

const styles: [CitationStyle, string][] = [["apa", "APA"], ["mla", "MLA"], ["chicago", "Chicago"], ["gbt7714-2025", "GB/T 7714"]];
const examples: Record<string, string> = { apa: "作者. (年份). 书名. 出版社.", mla: "作者. 书名. 出版社, 年份.", chicago: "作者. 书名. 出版地: 出版社, 年份.", "gbt7714-2025": "作者. 书名[M]. 出版地: 出版社, 年份." };

export function SupportCitationExample({ compact = false }: { compact?: boolean }) {
  const [style, setStyle] = useState<CitationStyle>("apa"), [pdfPage, setPdfPage] = useState("88"), [printedPage, setPrintedPage] = useState("102"), [message, setMessage] = useState("");
  const text = `【引用格式示例，非真实文献】\n${examples[style]}\nPDF 页序：${pdfPage || "未填写"}；纸本页码：${printedPage || "未填写"}（均为演示输入）。`;
  async function copy() { try { await navigator.clipboard.writeText(text); setMessage("格式示例已复制；实际引用请在原文阅读页生成。"); } catch { setMessage("浏览器未允许复制，请选择下方示例文字手动复制。"); } }
  function download() { const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" })); const link = document.createElement("a"); link.href = url; link.download = "引用格式示例.txt"; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); setMessage("已导出格式示例，不能用作真实文献的引用。"); }
  return <div className={`stl4-citation-stage${compact ? " is-compact" : ""}`}><div className={`stl4-citation-example${compact ? " is-compact" : ""}`} aria-label="引用格式操作示例"><strong>引用格式示例</strong><div className="stl4-citation-formats" aria-label="示例引用格式">{styles.map(([value, label]) => <button type="button" key={value} aria-pressed={style === value} onClick={() => { setStyle(value); setMessage(""); }}>{label}</button>)}</div><p className="stl4-citation-example-text">{examples[style]}</p>{!compact ? <div className="stl4-citation-pages"><label>PDF 页码<input inputMode="numeric" value={pdfPage} maxLength={6} onChange={event => setPdfPage(event.target.value.replace(/\D/g, ""))} /></label><label>纸本页码<input value={printedPage} maxLength={24} onChange={event => setPrintedPage(event.target.value)} /></label></div> : null}<div className="stl4-example-actions"><button type="button" onClick={() => void copy()}><Copy size={15} />复制</button>{compact ? <button type="button" onClick={download}><Download size={15} />导出示例</button> : null}</div><small className="stl4-example-notice">此处展示格式。正式引用请在原文页面生成。</small>{message ? <p className="stl4-support-status" role="status">{message}</p> : null}</div></div>;
}
