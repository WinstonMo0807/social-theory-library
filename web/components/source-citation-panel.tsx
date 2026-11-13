"use client";
import { useEffect, useState } from "react";
import { BookOpen, Copy } from "lucide-react";
import { normalizePublicResourceUrl } from "@/lib/api";
import { citationText, previewSharedCitation, type SharedCitationInput, type SharedCitationPreview } from "@/lib/api/shared-citation.client";
import { SharedCitationButton } from "./shared-citation-overlay";
import { LoadingState } from "./ui/loading-state";
import styles from "@/app/explore/opinions/viewpoint-search.module.css";
import panelStyles from "./source-citation-panel.module.css";

export function SourceCitationPanel({input}:{input:SharedCitationInput}) {
  const key=JSON.stringify(input),[preview,setPreview]=useState<SharedCitationPreview|null>(null),[error,setError]=useState(''),[attempt,setAttempt]=useState(0),[copied,setCopied]=useState('');
  useEffect(()=>{const controller=new AbortController();setPreview(null);setError('');setCopied('');void previewSharedCitation(JSON.parse(key),controller.signal).then(value=>{if(!controller.signal.aborted)setPreview(value);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:'引用信息暂不可用。');});return()=>controller.abort();},[key,attempt]);
  async function copy(){let latest:SharedCitationPreview;try{latest=await previewSharedCitation(input);setPreview(latest);}catch(reason){setPreview(null);setError(reason instanceof Error?reason.message:'来源暂不可用，请重新核对。');return;}try{await navigator.clipboard.writeText(citationText(latest,'gbt7714-2025'));setCopied('引用格式已复制。');}catch{setCopied('请选中下方引文复制。');}}

  return <div className={`${styles.evidenceSummary} ${panelStyles.panel}`}>{error?<div role="alert"><p>{error}</p><button type="button" onClick={()=>setAttempt(n=>n+1)}>重新核对来源</button></div>:!preview?<LoadingState variant="compact">正在核对引用信息…</LoadingState>:<>
    <div className={`${styles.evidenceBook} ${styles.compactBook}`}>{preview.source.cover_url&&<img src={normalizePublicResourceUrl(preview.source.cover_url)} alt="书籍封面"/>}<div><h3>{preview.source.title}</h3><p>{preview.source.authors.join('、')}</p><p>{[preview.source.publication_year,preview.source.publisher].filter(Boolean).join(' · ')}</p></div></div>
    {(preview.source.pdf_page||preview.source.printed_label)&&<section><strong>{preview.source.printed_label?`书页 ${preview.source.printed_label}`:''}{preview.source.pdf_page?` · PDF ${preview.source.pdf_page}`:''}</strong></section>}
    <section className={styles.citationPreview}><h3>GB/T 7714—2025</h3><p className={styles.citationText}>{citationText(preview,'gbt7714-2025')}</p>{preview.source.citation_notes?.map(note=><p className={styles.help} key={note}>{note}</p>)}</section>
    <div className={panelStyles.actions}>{preview.source.reader_url&&<a href={preview.source.reader_url}><BookOpen size={16}/>在线阅读</a>}<button type="button" onClick={()=>void copy()}><Copy size={15}/>复制引用</button><SharedCitationButton {...input}>其他格式与选材</SharedCitationButton></div>{copied&&<p role="status">{copied}</p>}
  </>}</div>;
}
