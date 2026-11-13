"use client";

import { LoadingState } from "@/components/ui/loading-state";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { ExternalLink, X } from "lucide-react";
import type { IssueResolvedSource } from "@/lib/api/recommendation-issues.types";
import { previewSharedCitation, type SharedCitationInput, type SharedCitationPreview } from "@/lib/api/shared-citation.client";
import { CitationSourcePreview } from "@/components/research/citation-source-preview";
import { SharedCitationButton } from "@/components/shared-citation-overlay";
import { Drawer } from "@/components/ui/dialog";
import styles from "./editorial.module.css";

export function editorialCitation(source: IssueResolvedSource): SharedCitationInput | null {
  if (source.type === "span") return { reference: { evidence_span_id: source.id, document_revision_id: source.document_revision_id } };
  if (source.asset_id && source.document_revision_id) return { reference: { asset_id: source.asset_id, document_revision_id: source.document_revision_id, pdf_page: source.page_start || 1 } };
  return source.edition_id ? { editionId: source.edition_id } : null;
}
export function EditorialSource({ source, children }: { source: IssueResolvedSource; children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  return <><button type="button" className={styles.sourceLink} onClick={() => setOpen(true)}>{children || source.title}</button>{open ? <Drawer open onRequestClose={() => setOpen(false)} className={styles.sourceDrawer} aria-label="原文与编辑注释"><header><strong>{editorialCitation(source) ? "原文阅读" : "编辑注释"}</strong><button aria-label="关闭原文返回文章" onClick={() => setOpen(false)}><X size={18} /></button></header><EditorialSourceContent source={source} /><button className={styles.returnButton} onClick={() => setOpen(false)}>返回文章</button></Drawer> : null}</>;
}
export function EditorialSourceContent({ source }: { source: IssueResolvedSource }) {
  const input = editorialCitation(source), fingerprint = JSON.stringify(input);
  const [result, setResult] = useState<SharedCitationPreview | null>(null), [error, setError] = useState(""), [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); let sequence = 0;
    const reload = () => {
      if (document.visibilityState !== "visible" || fingerprint === "null") return;
      const current = ++sequence; setResult(null); setError("");
      void previewSharedCitation(JSON.parse(fingerprint), controller.signal).then(value => { if (!controller.signal.aborted && current === sequence) setResult(value); })
        .catch(reason => { if (!controller.signal.aborted && current === sequence) setError(reason instanceof Error ? reason.message : "原文暂不可用。"); });
    };
    reload(); window.addEventListener("focus", reload); document.addEventListener("visibilitychange", reload);
    return () => { controller.abort(); window.removeEventListener("focus", reload); document.removeEventListener("visibilitychange", reload); };
  }, [fingerprint, attempt]);
  if (!input) return <section className={styles.sourceDescription}><h2>{source.title}</h2>{source.summary ? <p>{source.summary}</p> : <p>这条注释关联到已公开的知识资料。</p>}{source.href ? <Link href={source.href}>查看相关条目 <ExternalLink size={14} /></Link> : null}</section>;
  return <section className={styles.sourceContent}><h2>{result?.source.title || source.title}</h2>{source.edition_label ? <p>{source.edition_label}</p> : null}
    {error ? <div role="alert"><h3>该版本原文暂不可用</h3><p>{error}</p><button onClick={() => setAttempt(value => value + 1)}>重新核对原文</button></div> : !result ? <LoadingState role="status">正在核对当前版本与原文权限…</LoadingState> : result.reference ? <CitationSourcePreview reference={result.reference} /> : <p>这条材料当前只有书目信息，尚未提供可核验的原文页。</p>}
    <footer>{result ? <SharedCitationButton {...input}>引用 · 加入研究</SharedCitationButton> : null}{source.work_url ? <Link href={source.work_url}>查看书目信息</Link> : null}{result?.source.reader_url ? <a href={result.reference?.reader_url || result.source.reader_url} target="_blank" rel="noopener noreferrer">完整阅读、笔记与下载 <ExternalLink size={14} /></a> : null}</footer>
  </section>;
}
