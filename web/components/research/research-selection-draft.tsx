"use client";

import { useEffect, useEffectEvent, useState } from "react";
import { ApiRequestError } from "@/lib/api";
import { PrivateOwnerVerificationError } from "@/lib/api/private-owner";
import { applyResearchSelectionDraft, readResearchProjectForOwner, type ProjectData, type ResearchRecord, type ResolvedEvidence } from "@/lib/api/research.client";
import { researchEvidenceKey, researchEvidenceReference } from "@/lib/api/research-evidence";
import { createRequestKey } from "@/lib/request-key";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { parseResearchSelectionDraft, type ResearchSelectionDraft } from "@/lib/research-selection-draft";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { ResearchTabRecovery } from "./research-tab-recovery";
import { useResearchTabDraft } from "./use-research-tab-draft";
import type { useResearchProject } from "./use-research-project";

export function useResearchSelectionDraft(workspace: ReturnType<typeof useResearchProject>, locked: boolean) {
  const { record, pending, run, refresh } = workspace;
  const owner = String(workspace.session.user?.id || "");
  const [draft, setDraft] = useState<ResearchSelectionDraft | null>(null);
  const [localMode, setLocalMode] = useState(false);
  const [message, setMessage] = useState("");
  const [canReview, setCanReview] = useState(false);
  const [autoSync, setAutoSync] = useState(false);
  const [reviewRecord, setReviewRecord] = useState<ResearchRecord<ProjectData> | null>(null);
  const [confirm, setConfirm] = useState<"discard" | "rebase" | null>(null);
  const storage = useResearchTabDraft({ owner, project: record?.id || "", kind: "selections", value: draft, parseInput: parseResearchSelectionDraft });
  const blocked = locked || pending || !storage.scanned || Boolean(storage.recovery) || Boolean(storage.error) || Boolean(draft?.requestId);
  useUnsavedForm(Boolean(draft), false);
  function stage(ref: ResolvedEvidence, remove: boolean) {
    if (!record || blocked) return;
    try {
      const key = researchEvidenceKey(ref), title = `${ref.title || "原文材料"}${ref.pdf_page ? ` · PDF ${ref.pdf_page}` : ""}`.slice(0, 500);
      const baseline = draft || { revision: record.revision, additions: [], removals: [] };
      const additions = baseline.additions.filter(item => item.key !== key), removals = baseline.removals.filter(item => item.key !== key);
      if (remove) {
        if (!baseline.additions.some(item => item.key === key)) removals.push({ key, title });
      } else if (!baseline.removals.some(item => item.key === key)) additions.push({ key, title, reference: researchEvidenceReference(ref) });
      const next = additions.length + removals.length ? parseResearchSelectionDraft({ revision: baseline.revision, additions, removals }) : null;
      setDraft(next); setAutoSync(false); setLocalMode(true); setMessage(""); if (storage.enabled) storage.capture(next);
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "选材修改未能暂存。"); }
  }
  function undoItem(key: string) {
    if (!draft || blocked) return;
    const additions = draft.additions.filter(item => item.key !== key), removals = draft.removals.filter(item => item.key !== key);
    const next = additions.length + removals.length ? { ...draft, additions, removals } : null;
    setDraft(next); setAutoSync(false); if (storage.enabled) storage.capture(next);
  }
  async function sync(lookupOnly = false) {
    if (!record || !draft || locked || pending) return;
    setAutoSync(false);
    const original = draft;
    let rejected = false;
    const ok = await run(async () => {
      const latest = await readResearchProjectForOwner(record.id, owner);
      setReviewRecord(latest);
      if (original.requestId && latest.data.selection_receipts?.includes(original.requestId)) return;
      if (lookupOnly) throw new Error("保留的最近 100 条操作结果中未查到本批请求。请重试原请求；如状态已变化，再核对后处理。");
      if (!original.requestId && latest.revision !== original.revision) { setCanReview(true); throw new Error("研究已有更新，整批修改未写入。请读取最新状态，核对选材后继续。"); }
      const fixed = { ...original, requestId: original.requestId || createRequestKey() };
      setDraft(fixed); setCanReview(false); if (storage.enabled) storage.capture(fixed);
      try {
        const saved = await applyResearchSelectionDraft(record.id, { expected_revision: fixed.revision, request_id: fixed.requestId, additions: fixed.additions.map(item => item.reference), removals: fixed.removals.map(item => item.key) }, owner);
        if (saved.id !== record.id || !saved.data.selection_receipts?.includes(fixed.requestId)) throw new Error("整批选材操作结果未能核对，请保留原请求后查询。");
      } catch (reason) {
        rejected = reason instanceof ApiRequestError && !(reason instanceof PrivateOwnerVerificationError) && reason.status >= 400 && reason.status < 500 && ![408, 429].includes(reason.status);
        throw reason;
      }
    }, "本批选材请求已确认，当前选材以最新保存状态为准。");
    if (ok) { setDraft(null); storage.capture(null); setCanReview(false); setReviewRecord(null); setMessage(""); }
    else if (rejected) setCanReview(true);
  }
  const reconnect = useEffectEvent(() => {
    if (!autoSync || !draft) return;
    setAutoSync(false);
    if (locked || pending) { setMessage("连接已恢复，当前有另一项操作；本批保留，请稍后点击整批同步。"); return; }
    void sync();
  });
  useEffect(() => { const handler = () => reconnect(); window.addEventListener("online", handler); return () => window.removeEventListener("online", handler); }, []);
  const selectedKeys = new Set(record?.data.selections.map(researchEvidenceKey) || []);
  for (const item of draft?.removals || []) selectedKeys.delete(item.key);
  for (const item of draft?.additions || []) selectedKeys.add(item.key);
  const statusFor = (key: string) => draft?.additions.some(item => item.key === key) ? "待加入" : draft?.removals.some(item => item.key === key) ? "待移除" : "";
  const latest = reviewRecord && (!record || reviewRecord.revision >= record.revision) ? reviewRecord : record;
  const panel = <section className="stl4-research-selection-draft" aria-label="选材同步">
    <div className="stl4-comparison-inline-actions"><button type="button" disabled={locked || pending || Boolean(draft) || Boolean(storage.recovery)} aria-pressed={localMode} onClick={() => setLocalMode(value => !value)}>{localMode ? "结束暂存选材" : "暂存选材修改"}</button>{draft ? <strong>{draft.additions.length + draft.removals.length} 项选材修改待同步</strong> : null}</div>
    {draft ? <div className="stl4-research-source-notice"><p>本机待同步不会改变已保存选材。同步或放弃本批修改后可发送新的研究问题，当前仍可阅读和填写笔记。{draft.requestId ? "原请求已固定，先查询或原样重试；核对前不能修改这批内容。" : (autoSync ? "已允许本页恢复连接时同步这一批；修改本批内容会取消这次允许。" : "逐项核对后点击整批同步；只有另行允许，恢复连接时才会自动同步。")}</p><ul>{[...draft.additions.map(item => ({ ...item, action: "加入" })), ...draft.removals.map(item => ({ ...item, action: "移除" }))].map(item => <li key={item.key}><span>{item.action} · {item.title}</span><button type="button" disabled={blocked} onClick={() => undoItem(item.key)}>撤回本项修改</button></li>)}</ul>
      <div className="stl4-comparison-inline-actions">{!draft.requestId ? <button type="button" disabled={locked || pending} aria-pressed={autoSync} onClick={() => setAutoSync(value => !value)}>{autoSync ? "取消恢复连接时同步" : "允许恢复连接时同步本批"}</button> : null}{draft.requestId ? <button type="button" disabled={locked || pending} onClick={() => void sync(true)}>查询选材请求</button> : null}<button type="button" disabled={locked || pending} onClick={() => void sync()}>{draft.requestId ? "重试原批次" : "整批同步选材"}</button><button type="button" disabled={locked || pending} onClick={refresh}>读取最新状态</button><button type="button" disabled={locked || pending} onClick={() => setConfirm("discard")}>放弃本机修改</button></div>
      {draft.revision !== latest?.revision || canReview ? <div><p>保存版本与本批基线可能不同。请先核对当前保存的选材，再决定是否按新版本重新提交。本批原始引用不会替换成新版同页。</p><ul>{latest?.data.selections.map(ref => <li key={researchEvidenceKey(ref)}>{ref.title || "原文材料"} · PDF {ref.pdf_page || "—"} · {ref.source_status === "available" ? "可用" : "来源待核对"}</li>)}</ul><button type="button" disabled={locked || pending || Boolean(draft.requestId) && !canReview} onClick={() => setConfirm("rebase")}>已核对当前选材，保留这些修改</button></div> : null}
    </div> : null}
    {message ? <p role="alert">{message}</p> : null}
    <details data-disclosure="collection" open={Boolean(storage.recovery || storage.error)} className="stl4-research-prompt-recovery"><summary>待同步选材的本机恢复</summary><ResearchTabRecovery storage={storage} label="待同步选材" description="仅暂存文献标题、来源定位和加入/移除意图，不暂存原文正文；默认只在内存，勾选后才保留于此标签页。" pending={locked || pending} onRestore={value => { setDraft(value); setAutoSync(false); setLocalMode(true); setCanReview(false); setReviewRecord(null); }} preview={value => <p>加入 {value.additions.length} 项，移除 {value.removals.length} 项{value.requestId ? "；包含待查询原请求" : "；尚未提交"}。</p>} discardDescription="清除本机恢复记录不会取消服务器可能已经完成的同步；请先核对当前选材，避免重复操作。"/></details>
    <ConfirmDialog open={confirm !== null} title={confirm === "rebase" ? "以当前保存状态重新核对这批选材？" : "放弃本机待同步选材？"} description={confirm === "rebase" ? "保留原始引用和加入/移除意图，更新基线并使用新的请求标识。之后仍需点击整批同步。" : "本机修改及其恢复记录会清除，服务器选材保持现状。已提交的请求不会因此撤销。"} confirmLabel={confirm === "rebase" ? "保留修改，更新基线" : "放弃本机修改"} cancelLabel="返回" pending={locked || pending} onCancel={() => setConfirm(null)} onConfirm={() => {
      if (confirm === "rebase" && draft && latest) { const next = { revision: latest.revision, additions: draft.additions, removals: draft.removals }; setDraft(next); setCanReview(false); if (storage.enabled) storage.capture(next); }
      else { setDraft(null); storage.clear(); setCanReview(false); }
      setAutoSync(false); setConfirm(null);
    }}/>
  </section>;
  return { panel, blocked, hasDraft: Boolean(draft || storage.recovery), selectedKeys, statusFor, stage, shouldStage: () => localMode || Boolean(draft) || !navigator.onLine };
}
