"use client";

import Link from "next/link";
import { useState } from "react";
import { Trash2 } from "lucide-react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { ConfirmDialog } from "@/components/confirm-dialog";

export function RecycleControl({ kind, id, name, onDeleted, disabled = false }: {
  kind: string; id: string; name: string; onDeleted?: () => void; disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [deleted, setDeleted] = useState(false);
  async function remove() {
    if (busy) return;
    setBusy(true);
    setMessage("");
    try {
      await apiRequest(`/catalog/admin/lifecycle/${kind}/${id}/`, {
        method: "POST", body: JSON.stringify({ action: "delete", confirmed: true }),
      }, getServerSessionCredential());
      setDeleted(true); setOpen(false); onDeleted?.();
    } catch (error) { setMessage(error instanceof Error ? error.message : "删除失败，请重试。"); }
    finally { setBusy(false); }
  }
  return <span className="recycle-control">
    {deleted ? <span role="status">已移入回收站。<Link href="/admin/recycle">撤销删除</Link></span> : <button className="danger-link" type="button" disabled={disabled || busy} onClick={() => setOpen(true)}><Trash2 size={14} />删除</button>}
    <ConfirmDialog open={open} title={`删除“${name}”`} description={kind === "upload"
      ? "从上传、待办和处理列表移除，可在回收站恢复。保留原文件、已建立的馆藏与历史记录。未保存的输入不会提交。"
      : "移入回收站并停止公开展示，可恢复。原文件、历史与关联记录保留；恢复后需要重新检查并发布。未保存的输入不会提交。"}
      details={message ? [message] : []} confirmLabel="移入回收站" tone="danger" pending={busy} onCancel={() => setOpen(false)} onConfirm={() => void remove()} />
  </span>;
}
