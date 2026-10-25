"use client";

import { useState, type ReactNode } from "react";
import { ConfirmDialog } from "@/components/confirm-dialog";
import type { useResearchTabDraft } from "./use-research-tab-draft";

export function ResearchTabRecovery<T>({ storage, label, description, pending, onRestore, preview, discardDescription }: {
  storage: ReturnType<typeof useResearchTabDraft<T>>; label: string; description: string; pending: boolean;
  onRestore: (value: T) => void; preview: (value: T) => ReactNode; discardDescription?: string;
}) {
  const [confirm, setConfirm] = useState<"restore" | "clear" | null>(null);
  return <section className="stl4-research-prompt-recovery" aria-label={`${label}恢复`}>
    {storage.recovery ? <div><strong>本标签页有待恢复的{label}</strong>{preview(storage.recovery.input)}<p>暂存于 {new Date(storage.recovery.at).toLocaleString()}。恢复只填回页面，之后再核对服务器状态。</p><div className="stl4-comparison-inline-actions"><button type="button" disabled={pending} onClick={() => setConfirm("restore")}>查看并恢复</button><button type="button" disabled={pending} onClick={() => setConfirm("clear")}>清除此暂存</button></div></div>
      : <label><input type="checkbox" checked={storage.enabled} disabled={pending || !storage.scanned || Boolean(storage.error)} onChange={event => { if (event.target.checked) storage.enable(); else setConfirm("clear"); }}/>允许在本标签页暂存{label}</label>}
    <p>{description} 暂存可被此浏览器读取，退出或重新登录时清除，关闭标签页后不保证恢复。</p>
    {storage.savedAt ? <p role="status">本机暂存于 {new Date(storage.savedAt).toLocaleTimeString()}，尚不代表服务器已保存。</p> : null}
    {storage.error ? <p role="alert">{storage.error}<button type="button" disabled={pending} onClick={() => setConfirm("clear")}>清除本机暂存</button></p> : null}
    <ConfirmDialog open={confirm !== null} title={confirm === "restore" ? `恢复暂存的${label}？` : `清除此${label}的本机暂存？`} description={confirm === "restore" ? "恢复内容会替换页面中对应的当前输入。服务器资料暂不改变。" : (discardDescription || "仅清除本标签页的暂存并关闭自动暂存。当前输入和服务器资料仍保留。")} confirmLabel={confirm === "restore" ? "恢复到页面" : "清除暂存"} cancelLabel="返回" pending={pending} onCancel={() => setConfirm(null)} onConfirm={() => { if (confirm === "restore") { const input = storage.restore(); if (input !== null) onRestore(input); } else storage.clear(); setConfirm(null); }}/>
  </section>;
}
