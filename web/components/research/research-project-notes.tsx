"use client";

import { useState } from "react";
import Link from "next/link";
import { Dialog } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { readResearchProjectForOwner, readResearchSelectionNoteSource, updateResearchProject, type ResolvedEvidence } from "@/lib/api/research.client";
import { ApiRequestError } from "@/lib/api";
import { researchReaderHref } from "@/lib/api/research-evidence";
import { parseResearchNoteDraft, type ResearchNoteDraft } from "@/lib/research-tab-draft";
import { useResearchTabDraft } from "./use-research-tab-draft";
import { ResearchTabRecovery } from "./research-tab-recovery";
import type { useResearchProject } from "./use-research-project";

export function ResearchProjectNotes({ workspace }: { workspace: ReturnType<typeof useResearchProject> }) {
  const { record, pending, actionError, refresh, run } = workspace;
  const [draft, setDraft] = useState<ResearchNoteDraft | null>(null);
  const [discard, setDiscard] = useState(false);
  const [noteLimit, setNoteLimit] = useState(50);
  const [sourcePreview, setSourcePreview] = useState<ResolvedEvidence | null>(null);
  const [sourceError, setSourceError] = useState("");
  const dirty = Boolean(draft && draft.text !== draft.initial);
  const owner = String(workspace.session.user?.id || "");
  const storage = useResearchTabDraft({ owner, project: record?.id || "", kind: "notes", value: dirty ? draft : null, parseInput: parseResearchNoteDraft });
  useUnsavedForm(dirty, false);
  if (!record) return null;
  const materialNotes = Object.entries(record.data.selection_notes || {}).filter(([, body]) => body.trim());
  function close() { if (!pending) { if (dirty) setDiscard(true); else setDraft(null); } }
  async function readNoteSource(id: string) {
    if (!record || pending) return;
    setSourceError(""); let source: ResolvedEvidence | null = null;
    const ok = await run(async () => {
      try {
        source = await readResearchSelectionNoteSource(record.id, id, owner);
        if (source.reference_id !== id) throw new Error("暂时无法核对备注的原文来源。备注文字仍保留。");
      } catch (reason) {
        setSourceError(reason instanceof Error ? reason.message : "原备注来源暂时无法读取。");
        if (reason instanceof ApiRequestError && reason.status === 404) throw new Error("原备注定位已不存在或未记录，备注文字仍保留。");
        throw reason;
      }
    }, "已读取该备注的原始来源状态。");
    if (ok && source) setSourcePreview(source);
  }
  async function save() {
    if (!draft || !record || pending) return;
    if (storage.enabled) storage.capture(draft);
    const currentDraft = draft;
    const ok = await run(async () => {
      const latest = await readResearchProjectForOwner(record.id, owner);
      if (latest.data.notes === currentDraft.text) return;
      if (latest.revision !== currentDraft.revision) throw new Error("服务器研究已有更新，本次没有覆盖。请读取最新状态并核对笔记后再保存。");
      await updateResearchProject(record.id, { expected_revision: currentDraft.revision, notes: currentDraft.text }, owner);
    }, "研究笔记已保存，与比较页同步。");
    if (ok) { storage.capture(null); setDraft(null); }
  }
  const recovery = <ResearchTabRecovery storage={storage} label="未保存笔记" description="仅暂存本次笔记文字、编辑前的笔记与版本标识，不自动上传。恢复后核对最新研究，点击保存才同步。" pending={pending} onRestore={setDraft} preview={value => <p className="stl4-research-notes-copy">{value.text || "本次修改将笔记清空"}</p>}/>;
  return <>
    <header><h2>我的研究笔记</h2><button type="button" className="stl4-research-secondary" disabled={pending || !storage.scanned || Boolean(storage.recovery) || Boolean(storage.error)} onClick={() => setDraft({ text: record.data.notes || "", initial: record.data.notes || "", revision: record.revision })}>编辑笔记</button></header>
    <p>笔记与比较页同步，仅本人可见。</p>
    <div className="stl4-research-notes-copy">{record.data.notes || "尚未填写研究笔记。可以记录判断、疑问和下一步需要核对的材料。"}</div>
    {materialNotes.length ? <details className="stl4-research-material-notes"><summary>选材备注（{materialNotes.length}）</summary><p>移除选材后，已写备注仍保留。旧来源变化时不会自动关联到新版本。</p><ul>{materialNotes.slice(0, noteLimit).map(([id, body]) => {
      const source = record.data.selection_note_sources?.[id], href = source ? researchReaderHref(source) : "";
      return <li key={id}><strong>{source?.source_status === "available" ? source.title || "原文材料" : "原来源待核对"}</strong><p className="stl4-research-notes-copy">{body}</p>{href ? <Link href={href} target="_blank" rel="noreferrer">核对原备注来源{source?.pdf_page ? ` · PDF 第 ${source.pdf_page} 页` : ""}</Link> : source ? <button type="button" disabled={pending} onClick={()=>void readNoteSource(id)}>核对原备注来源</button> : <small>旧来源定位未记录，备注文字仍保留。</small>}</li>;
    })}</ul>{noteLimit < materialNotes.length ? <button type="button" onClick={()=>setNoteLimit(value=>value+50)}>继续显示备注（已显示 {noteLimit}/{materialNotes.length}）</button> : null}{sourceError ? <p role="alert">{sourceError}</p> : null}</details> : null}
    {draft ? null : recovery}
    <Dialog open={draft !== null} onRequestClose={close} className="stl4-research-dialog" aria-labelledby="workspace-notes-title">
      {draft ? <form onSubmit={event => { event.preventDefault(); void save(); }}>
        <h2 id="workspace-notes-title">编辑研究笔记</h2><label htmlFor="workspace-notes-text">判断、疑问与后续计划</label>
        <textarea id="workspace-notes-text" rows={10} maxLength={20000} disabled={pending} value={draft.text} onChange={event => setDraft({ ...draft, text: event.target.value })}/>
        {recovery}
        {draft.revision !== record.revision ? <div role="status"><p>研究已有更新。请核对最新保存的笔记，再决定是否使用当前填写替换。</p><p className="stl4-research-notes-copy">{record.data.notes || "尚无已保存笔记"}</p><button type="button" disabled={pending} onClick={() => setDraft({ ...draft, revision: record.revision })}>已核对，保留当前填写</button></div> : null}
        {actionError ? <p role="alert">{actionError}<button type="button" disabled={pending} onClick={refresh}>读取最新状态</button></p> : null}
        <footer><button type="button" disabled={pending} onClick={close}>返回</button><button type="submit" disabled={pending || draft.revision !== record.revision}>{pending ? "正在保存……" : "保存笔记"}</button></footer>
      </form> : null}
    </Dialog>
    <ConfirmDialog open={discard} title="放弃尚未保存的笔记修改？" description="已保存的研究笔记和原文材料仍保留，本次修改及其本机暂存将清除。" confirmLabel="放弃本次修改" cancelLabel="继续编辑" pending={pending} onCancel={() => setDiscard(false)} onConfirm={() => { storage.clear(); setDraft(null); setDiscard(false); }}/>
    <Dialog open={sourcePreview !== null} onRequestClose={()=>setSourcePreview(null)} className="stl4-research-dialog" aria-labelledby="material-note-source-title"><h2 id="material-note-source-title">备注原始来源</h2>{sourcePreview?.source_status === "available" ? <><p>{sourcePreview.title || "原文材料"}</p><p>{sourcePreview.citation}</p>{researchReaderHref(sourcePreview) ? <Link href={researchReaderHref(sourcePreview)} target="_blank" rel="noreferrer">打开原始位置{sourcePreview.pdf_page ? ` · PDF 第 ${sourcePreview.pdf_page} 页` : ""}</Link> : null}</> : <p>原始版本已变化或当前不可访问，备注文字仍保留，不会替换为新版同页。</p>}<footer><button type="button" onClick={()=>setSourcePreview(null)}>返回笔记</button></footer></Dialog>
  </>;
}
