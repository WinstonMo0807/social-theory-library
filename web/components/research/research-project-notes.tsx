"use client";

import { useState } from "react";
import { Dialog } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { readResearchProjectForOwner, updateResearchProject } from "@/lib/api/research.client";
import { parseResearchNoteDraft, type ResearchNoteDraft } from "@/lib/research-tab-draft";
import { useResearchTabDraft } from "./use-research-tab-draft";
import { ResearchTabRecovery } from "./research-tab-recovery";
import type { useResearchProject } from "./use-research-project";

export function ResearchProjectNotes({ workspace }: { workspace: ReturnType<typeof useResearchProject> }) {
  const { record, pending, actionError, refresh, run } = workspace;
  const [draft, setDraft] = useState<ResearchNoteDraft | null>(null);
  const [discard, setDiscard] = useState(false);
  const dirty = Boolean(draft && draft.text !== draft.initial);
  const owner = String(workspace.session.user?.id || "");
  const storage = useResearchTabDraft({ owner, project: record?.id || "", kind: "notes", value: dirty ? draft : null, parseInput: parseResearchNoteDraft });
  useUnsavedForm(dirty, false);
  if (!record) return null;
  function close() { if (!pending) { if (dirty) setDiscard(true); else setDraft(null); } }
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
    <p>这份笔记与证据比较共用，仅本人可见。原文依据仍保留各自的引用身份。</p>
    <div className="stl4-research-notes-copy">{record.data.notes || "尚未填写研究笔记。可以记录判断、疑问和下一步需要核对的材料。"}</div>
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
  </>;
}
