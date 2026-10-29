"use client";

import Link from "next/link";
import { Download, FolderInput, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { readLocalResearchSnapshot, prepareLocalResearchTransfer } from "@/lib/api/local-research-transfer";
import { importLocalResearch } from "@/lib/api/research.client";
import { Dialog } from "@/components/ui/dialog";
import styles from "./reader-overview.module.css";

type Snapshot = NonNullable<ReturnType<typeof readLocalResearchSnapshot>>;
type Receipt = { requestId: string; digest: string; projectId?: string; warnings?: number };

async function transferIdentity(owner: string, id: string) {
  // One source/recipient pair has one request identity even across tabs or lost receipts.
  const bytes = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`stl-local-research:v1:${owner}:${id}`))).slice(0, 16);
  bytes[6] = (bytes[6] & 15) | 128; bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function LocalResearchTransfer({ ownerId, onChanged }: { ownerId: string; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [receipts, setReceipts] = useState<Record<string, Receipt>>({});
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const request = useRef<AbortController | null>(null);
  const saving = useRef(false);
  const key = `stl-local-research-receipts:${ownerId}`;
  useEffect(() => { const controller = new AbortController(); request.current = controller; const stop = subscribeToSessionChanges(() => controller.abort()); return () => { controller.abort(); stop(); }; }, []);

  function inspect() {
    setOpen(true); setSnapshot(null); setSelected([]); setAcknowledged(false); setMessage("");
    try {
      const found = readLocalResearchSnapshot();
      const saved = JSON.parse(localStorage.getItem(key) || "{}");
      if (!saved || Array.isArray(saved) || typeof saved !== "object" || Object.values(saved).some(value => !value || typeof value !== "object" || !("requestId" in value) || typeof value.requestId !== "string" || !("digest" in value) || typeof value.digest !== "string")) throw new Error("本机转存结果无法识别，请保留并核对原研究记录，当前不会新建重复请求。");
      setReceipts(saved); setSnapshot(found);
      if (!found || !found.store.research.length) setMessage("未找到可转存的本机研究草稿。");
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "本机记录读取失败，原内容未改变。"); }
  }
  function exportLocal() {
    if (!snapshot) return;
    const url = URL.createObjectURL(new Blob([snapshot.raw], { type: "application/json;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "本机研究原始记录.json"; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function transfer() {
    const controller = request.current;
    if (!snapshot || !selected.length || !acknowledged || saving.current || !controller || controller.signal.aborted) return;
    if (!globalThis.crypto?.subtle) { setMessage("当前浏览器连接不支持转存所需的安全摘要。请通过本站 HTTPS 入口继续；也可以先保存下方原始记录。本机内容尚未上传或改变。"); return; }
    saving.current = true; setBusy(true); setMessage("");
    let completed = 0;
    let next = { ...receipts };
    try {
      for (const id of selected) {
        if (controller.signal.aborted) return;
        if (next[id]?.projectId) continue;
        const requestId = next[id]?.requestId || await transferIdentity(ownerId, id);
        const body = prepareLocalResearchTransfer(snapshot.store, id, requestId);
        const buffer = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(JSON.stringify(body)));
        const digest = Array.from(new Uint8Array(buffer), value => value.toString(16).padStart(2, "0")).join("");
        if (next[id] && next[id].digest !== digest) throw new Error("本机内容已修改。请先到研究列表核对上次转存结果。");
        next = { ...next, [id]: { requestId, digest } };
        // Store only request identity/fingerprint; never copy private bodies into the receipt.
        localStorage.setItem(key, JSON.stringify(next)); setReceipts(next);
        const result = await withPrivateOwner(ownerId, () => importLocalResearch(body, ownerId, controller.signal), controller.signal);
        if (controller.signal.aborted) return;
        next = { ...next, [id]: { requestId, digest, projectId: result.id, warnings: result.data.import_warnings?.length || 0 } };
        localStorage.setItem(key, JSON.stringify(next)); setReceipts(next); completed += 1;
      }
      setSelected([]); setAcknowledged(false); setMessage(`已取得 ${completed} 项转存结果。原本机记录完整保留，可打开研究核对来源。`); onChanged();
    } catch (reason) {
      if (!controller.signal.aborted) { setMessage(`已完成 ${completed} 项。${reason instanceof Error ? reason.message : "转存未完成。"} 未取得操作结果的项目重试时使用原请求，其他项目未继续提交。`); onChanged(); }
    } finally { saving.current = false; if (!controller.signal.aborted) setBusy(false); }
  }
  return <>
    <button onClick={inspect}><FolderInput size={15} />查看本机研究记录</button>
    {open ? <Dialog open onRequestClose={() => { if (!busy) setOpen(false); }} className={styles.transferDialog} aria-labelledby="local-transfer-title"><header><div><h2 id="local-transfer-title">转存本机研究记录</h2><p>选择记录和接收账户后转存，已有研究保持不变。</p></div><button disabled={busy} onClick={() => setOpen(false)} aria-label="关闭转存"><X size={18} /></button></header>
      <p>当前接收账户编号：{ownerId}。共享设备上请先确认这些记录属于你；切换账户会中止本页请求。</p>
      {message ? <p role="status" className={styles.bulkNotice}>{message}</p> : null}
      {snapshot?.store.research.length ? <><ul>{snapshot.store.research.map(row => <li key={row.id}><label><input type="checkbox" disabled={busy || Boolean(receipts[row.id]?.projectId)} checked={selected.includes(row.id)} onChange={event => { setAcknowledged(false); setSelected(previous => event.target.checked ? [...previous, row.id] : previous.filter(id => id !== row.id)); }} /><span>{row.title || "未命名本机研究"}</span></label>{receipts[row.id]?.projectId ? <Link href={`/account/research/${receipts[row.id].projectId}`}>已转存 · 打开{receipts[row.id].warnings ? `（${receipts[row.id].warnings}项来源提醒）` : ""}</Link> : <small>{receipts[row.id] ? "待取得原请求结果" : "仅保存在本机"}</small>}</li>)}</ul><label className={styles.transferAck}><input type="checkbox" disabled={busy || !selected.length} checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} />我确认所选记录属于我，转存到当前账户；原记录保留，来源由服务器重新核对。</label></> : null}
      <footer>{snapshot ? <button disabled={busy} onClick={exportLocal}><Download size={14} />保存原始记录</button> : null}<Link href="/account/research">核对研究列表</Link><button disabled={busy || !acknowledged || !selected.length} onClick={() => void transfer()}>{busy ? "正在逐项转存…" : `转存所选（${selected.length}）`}</button></footer>
    </Dialog> : null}
  </>;
}
