"use client";
import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { FileImage, Minus, Plus, X } from 'lucide-react';
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from '@/lib/api';
import { previewSharedCitation } from '@/lib/api/shared-citation.client';
import { passageReference } from '@/lib/api/research.client';
import type { DiscoveryPassage } from '@/lib/api/discovery.types';
import type { ReaderAssetAccess } from '@/lib/api/public-catalog';
import { sourceLayoutHint } from '@/lib/source-layout';
import { SourceExcerpt } from './source-excerpt';
import { LoadingState } from './ui/loading-state';
import styles from './discovery-source-page.module.css';

const PdfCanvas=lazy(()=>import('./pdf-canvas').then(module=>({default:module.PdfCanvas})));

/** Render one requested source page in the browser. Never enqueue OCR/retrieval. */
export function DiscoverySourcePage({item}:{item:DiscoveryPassage}) {
  const hint=sourceLayoutHint(item.excerpt),[open,setOpen]=useState(false);
  const excerpt=<SourceExcerpt text={item.excerpt} preserveLayout={Boolean(hint)} label={`原文节选${/ocr/i.test(item.source_kind)?' · OCR':''}`} location={`${item.printed_page?`书页 ${item.printed_page} · `:''}PDF ${item.pdf_page}`} marginalia={[item.work.title,item.printed_page||'']} validateSource={async()=>{await previewSharedCitation({reference:passageReference(item),selectedText:item.excerpt});}}/>;
  return <div className={styles.source}>
    <div className={styles.tools}>{hint&&<span>{hint==='table'?'含表格或量表':'含公式'} · 按原页核对</span>}<button type="button" aria-expanded={open} onClick={()=>setOpen(value=>!value)}><FileImage size={16}/>{open?'收起原页':'查看原页'} · PDF {item.pdf_page}</button></div>
    {open&&<SourcePageCanvas item={item} onClose={()=>setOpen(false)}/>}
    {hint?<details className={styles.ocr}><summary>查看 OCR 文字对照</summary><p>列关系、公式和数字以原页为准。</p>{excerpt}</details>:excerpt}
  </div>;
}

function SourcePageCanvas({item,onClose}:{item:DiscoveryPassage;onClose:()=>void}) {
  const [access,setAccess]=useState<ReaderAssetAccess|null>(null),[error,setError]=useState(''),[attempt,setAttempt]=useState(0),[zoom,setZoom]=useState(100);
  const loaded=useCallback((pages:number)=>{if(item.pdf_page<1||item.pdf_page>pages)setError('当前页码超出阅读文件范围，请返回阅读器核对。');},[item.pdf_page]);
  useEffect(()=>{const controller=new AbortController();setError('');setAccess(null);void(async()=>{
    await previewSharedCitation({reference:passageReference(item),selectedText:item.excerpt},controller.signal);
    const payload=await apiRequest<ReaderAssetAccess>(`/distribution/assets/${encodeURIComponent(item.asset_id)}/access/`,{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]),cache:'no-store'},getServerSessionCredential());
    if(payload.requested_asset_id!==item.asset_id)throw Error('阅读文件已变化，请重新检索并核对来源。');
    if(!controller.signal.aborted)setAccess({...payload,url:normalizePublicResourceUrl(payload.url)});
  })().catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:'原页未能载入。');});return()=>controller.abort();},[item.asset_id,item.document_revision_id,item.id,item.pdf_page,attempt]);
  return <section className={styles.preview} aria-label={`原版 PDF 第 ${item.pdf_page} 页`}><header><strong>原版页面 · PDF {item.pdf_page}</strong><div><button type="button" aria-label="缩小原页" disabled={zoom<=80} onClick={()=>setZoom(value=>value-20)}><Minus size={16}/></button><button type="button" onClick={()=>setZoom(100)} aria-label="原页缩放复位">{zoom}%</button><button type="button" aria-label="放大原页" disabled={zoom>=240} onClick={()=>setZoom(value=>value+20)}><Plus size={16}/></button><button type="button" aria-label="关闭原页" onClick={onClose}><X size={17}/></button></div></header>
    {error?<div role="alert"><p>{error}</p><button type="button" onClick={()=>setAttempt(value=>value+1)}>重新读取原页</button></div>:access?<div className={styles.canvas}><Suspense fallback={<LoadingState>正在准备原页…</LoadingState>}><PdfCanvas url={access.url} page={item.pdf_page} zoom={zoom} sourceWidth={0} sourceHeight={0} canonicalBlocks={[]} highlights={[]} onDocumentLoad={loaded} withCredentials={new URL(access.url,location.origin).origin===location.origin}/></Suspense></div>:<LoadingState>正在核对原页…</LoadingState>}
  </section>;
}
