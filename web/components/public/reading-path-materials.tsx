"use client";

import { confirmAction } from "@/lib/ui-dialog";

import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { MediaPlacement } from "@/components/media-placement";
import { useState } from "react";
import { ArrowRight, BookOpen, FileText, MoreHorizontal, X } from "lucide-react";
import { readerContextHref } from "@/lib/api/research-navigation";
import { Dialog } from "@/components/ui/dialog";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import type { PathMaterial, PathProgress } from "@/lib/api/reading-paths.types";
import type { PathPersonal } from "./reading-path-personal";
import styles from "./reading-path.module.css";

const statusLabels: Record<PathProgress["status"], string> = { pending: "尚未开始", reading: "阅读中", completed: "已完成", skipped: "暂时跳过" };
const sourceLabels: Record<PathMaterial["source_status"], string> = { available: "原文可读", no_fulltext: "暂无全文", unavailable: "来源当前不可用", withdrawn: "材料已撤回", revision_changed: "原文版本已变化" };

export function ReadingPathMaterials({ items, personal, writable, preview, returnTo, onNavigateMaterial }: { items: PathMaterial[]; personal: PathPersonal; writable: boolean; preview: boolean; returnTo: string; onNavigateMaterial?:(id:string)=>void }) {
  const [details, setDetails] = useState<PathMaterial | null>(null), [noteItem, setNoteItem] = useState<PathMaterial | null>(null);
  const busy = personal.busy || !!personal.pending;
  return <>
    <div className={styles.materialTable} role="table" aria-label="阶段阅读材料"><div className={styles.materialHeader} role="row"><span role="columnheader">阅读类型</span><span role="columnheader">作品 / 章节 / 原文</span><span role="columnheader">作者</span><span role="columnheader">阅读理由</span><span role="columnheader">操作</span></div>
      {items.length ? items.map(item => { const progress = writable ? personal.record?.progress[item.id] : undefined; return <div className={styles.materialRow} role="row" key={item.id} id={`path-material-${item.id}`} tabIndex={-1} data-preview-stage-id={preview ? item.stage_id : undefined} data-preview-item-id={preview ? item.id : undefined}>
        <div className={styles.required} role="cell"><span data-required={item.is_required}>{item.is_required ? "必读" : "选读"}</span></div>
        <div className={styles.materialIdentity} role="cell">{item.cover_url ? <MediaPlacement uses={item.cover_media?.display_uses} fallback={<span className={styles.documentPlaceholder}><FileText size={27}/></span>}><img src={item.cover_url} alt="" /></MediaPlacement> : <span className={styles.documentPlaceholder}>{item.kind === "node" ? <BookOpen size={27} /> : <FileText size={27} />}</span>}<div><strong>{item.title}</strong>{item.chapter_title ? <small>{item.chapter_title}</small> : null}{item.version_label ? <small>{item.version_label}</small> : null}{item.page_start ? <small>PDF 第 {item.page_start}{item.page_end && item.page_end !== item.page_start ? `–${item.page_end}` : ""} 页{item.printed_page_label ? ` · 印刷页 ${item.printed_page_label}` : ""}</small> : null}{item.prerequisite ? <small>先修条件：{item.prerequisite}</small> : null}<span className={styles.mobileRequired}>{item.is_required ? "必读" : "选读"}</span><span className={styles.mobileAuthors}>{item.authors.join("、") || (item.source_status === "withdrawn" || item.source_status === "unavailable" ? "来源信息不可用" : "作者尚未收录")}</span></div></div>
        <div className={styles.authors} role="cell">{item.authors.join("、") || (item.source_status === "withdrawn" || item.source_status === "unavailable" ? "来源信息不可用" : "作者尚未收录")}</div>
        <div className={styles.materialReason} role="cell">{item.source_status !== "available" ? <><strong className={styles.sourceWarning}>{sourceLabels[item.source_status]}</strong><p>{item.source_notice}</p></> : <p>{item.reason || "尚未填写阅读理由。"}</p>}</div>
        <div className={styles.materialActions} role="cell">{item.kind === "node" && item.href && item.source_status === "available" ? <Link className={styles.outlineButton} href={item.href}>查看知识条目</Link> : item.reader_url && item.source_status === "available" ? <Link className={item.is_required ? styles.primaryButton : styles.outlineButton} href={readerContextHref(item.reader_url, { returnTo: `${returnTo}#path-material-${item.id}` })}>开始阅读</Link> : <button type="button" disabled className={styles.unavailableButton}>暂不可读</button>}
          {item.href ? <Link href={item.href}>查看详情<ArrowRight size={12} /></Link> : null}
          <button type="button" className={styles.textButton} aria-label={`查看${item.title}的来源与版本`} onClick={() => setDetails(item)}>{item.source_status === "available" ? <>来源与版本<MoreHorizontal size={13} /></> : <>了解来源状态<ArrowRight size={12} /></>}</button>
          {writable && personal.record && !preview ? <><label className={styles.progressSelect}><span className={styles.srOnly}>{item.title}的阅读状态</span><select data-stl-select value={progress?.status || "pending"} disabled={busy || progress?.status === "completed"} onChange={event => { if (personal.record) void personal.mutate({ action: "progress", request_id: createRequestKey(), id: personal.record.id, expected_revision: personal.record.revision, item_id: item.id, status: event.target.value as PathProgress["status"] }); }}>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>{progress?.status === "completed" ? <small>已完成记录保留，可补充笔记</small> : null}</label><button type="button" disabled={busy} onClick={() => setNoteItem(item)}>{progress?.note ? "查看本人笔记" : "记录本人笔记"}</button></> : null}
        </div>
      </div>; }) : <p className={styles.empty}>此阶段尚未编排阅读材料。</p>}
    </div>
    <Dialog open={!!details} className={styles.dialog} aria-labelledby="path-material-heading" onRequestClose={() => setDetails(null)}>{details ? <><header><h2 id="path-material-heading">{details.title}</h2><button type="button" aria-label="关闭材料来源" onClick={() => setDetails(null)}><X size={19} /></button></header><p className={styles.sourceWarning}>{sourceLabels[details.source_status]}</p><p>{details.source_notice}</p>{details.version_label ? <p>所选版本：{details.version_label}</p> : null}{details.learning_goal?<section><h3>阅读目标</h3><p>{details.learning_goal}</p></section>:null}{details.reason ? <section><h3>阅读理由</h3><p>{details.reason}</p></section> : null}{details.prerequisite ? <section><h3>先修要求</h3><p>{details.prerequisite}</p></section> : null}{details.dependencies?.length?<section><h3>路径内的先修关系</h3><ul>{details.dependencies.map(relation=><li key={`${relation.item_id}:${relation.kind}`}>{onNavigateMaterial?<button type="button" onClick={()=>{setDetails(null);onNavigateMaterial(relation.item_id);}}>{relation.title||"关联材料"}</button>:<span>{relation.title||"关联材料"}</span>} · {relation.kind==="learning_order"?"学习顺序":"理论相关"}{relation.reason?<p>{relation.reason}</p>:null}</li>)}</ul></section>:null}{details.substitutes.length ? <section><h3>可替代阅读的公开版本</h3><p>以下为已编排的替代材料。打开其他版本不会自动更改原材料的进度或笔记。</p><ul className={styles.substitutes}>{details.substitutes.map(row => <li key={row.edition_id}><strong>{row.title}</strong>{row.version_label ? <small>{row.version_label}</small> : null}{row.href ? <Link href={row.href}>查看版本<ArrowRight size={12} /></Link> : null}</li>)}</ul></section> : details.source_status !== "available" ? <p>暂无经过编排的公开替代材料。</p> : null}{details.href ? <Link className={styles.outlineButton} href={details.href}>打开书目与来源状态</Link> : null}</> : null}</Dialog>
    {noteItem && personal.record ? <PathNote key={`${personal.record.id}:${noteItem.id}`} item={noteItem} personal={personal} onClose={() => setNoteItem(null)} /> : null}
  </>;
}

function PathNote({ item, personal, onClose }: { item: PathMaterial; personal: PathPersonal; onClose: () => void }) {
  const saved = personal.record?.progress[item.id]?.note || "", [note, setNote] = useState(saved);
  const dirty = useUnsavedForm(note, saved), busy = personal.busy || !!personal.pending;
  const close = async () => { if (!personal.busy && (!dirty || (await confirmAction("本人笔记尚未保存，确定放弃本次输入吗？")))) onClose(); };
  return <Dialog open className={styles.dialog} aria-labelledby="path-note-heading" onRequestClose={close}><header><h2 id="path-note-heading">本人阅读笔记</h2><button type="button" aria-label="关闭路径笔记" disabled={personal.busy} onClick={close}><X size={19} /></button></header><p>{item.title}</p><p>仅保存到当前账户的跟读记录，不会写入公共路径。</p><form onSubmit={event => { event.preventDefault(); void (async () => { if (!personal.record) return; const result = await personal.mutate({ action: "note", request_id: createRequestKey(), id: personal.record.id, expected_revision: personal.record.revision, item_id: item.id, note }); if (result?.record) onClose(); })(); }}><label>笔记内容<textarea value={note} onChange={event => setNote(event.target.value)} maxLength={4000} rows={8} disabled={busy} /></label><button type="submit" className={styles.primaryButton} disabled={busy || !dirty}>保存本人笔记</button></form>{personal.error ? <p role="alert">{personal.error}</p> : null}{personal.pending && !personal.busy ? <button type="button" onClick={() => { if (personal.pending) void personal.mutate(personal.pending.command, true); }}>核对原操作</button> : null}</Dialog>;
}
