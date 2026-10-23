"use client";

import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Trash2 } from "lucide-react";
import { ApiRequestError, apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { useAdminSession } from "@/lib/admin-session";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { ConfirmDialog } from "@/components/confirm-dialog";

type Props = {
  kind: string; id: string; name: string; onDeleted?: () => void; disabled?: boolean;
};
export function RecycleControl(props: Props) {
  const user=useAdminSession(),[epoch,setEpoch]=useState(0);
  useEffect(()=>subscribeToSessionChanges(()=>setEpoch(value=>value+1)),[]);
  return <RecycleButton key={`${user?.id}:${epoch}:${props.kind}:${props.id}`} {...props} owner={String(user?.id||"")}/>;
}

function RecycleButton({kind,id,name,onDeleted,disabled=false,owner}:Props&{owner:string}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [deleted, setDeleted] = useState(false);
  const lifecycle=useRef<AbortController|null>(null),busyRef=useRef(false);
  const intent=useRef<{id:string;reason:string}|null>(null);
  useEffect(()=>{const controller=new AbortController();lifecycle.current=controller;return()=>controller.abort();},[]);
  async function remove(reason: string) {
    if (busyRef.current||!owner||!lifecycle.current||lifecycle.current.signal.aborted) return;
    const controller=lifecycle.current;
    const operation=intent.current||{id:createRequestKey(),reason};intent.current=operation;
    busyRef.current=true;
    setBusy(true);
    setMessage("");
    try {
      const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
      await withPrivateOwner(owner,()=>apiRequest(`/catalog/admin/lifecycle/${kind}/${id}/`, {
        method: "POST", signal,headers:{"X-Editor-Owner":owner,"Idempotency-Key":operation.id}, body: JSON.stringify({ action: "delete", confirmed: true, reason:operation.reason }),
      }, getServerSessionCredential()),signal);
      if(controller.signal.aborted)return;
      setDeleted(true); setOpen(false); onDeleted?.();
    } catch (error) { if(!controller.signal.aborted){
      if(error instanceof ApiRequestError&&error.status>=400&&error.status<500)intent.current=null;
      setMessage((error instanceof Error ? error.message : "删除暂未确认。")+(intent.current?" 再次确认将按原请求及原原因查回。":""));
    } }
    finally { if(!controller.signal.aborted){busyRef.current=false;setBusy(false);} }
  }
  return <span className="recycle-control">
    {deleted ? <span role="status">已移入回收站。<Link href="/admin/recycle">撤销删除</Link></span> : <button className="danger-link" type="button" disabled={disabled || busy} onClick={() => setOpen(true)}><Trash2 size={14} />删除</button>}
    <ConfirmDialog open={open} title={`删除“${name}”`} description={kind === "upload"
      ? "从上传、待办和处理列表移除，可在回收站恢复。保留原文件、已建立的馆藏与历史记录。未保存的输入不会提交。"
      : "移入回收站并停止公开展示，可恢复。原文件、历史与关联记录保留；恢复后需要重新检查并发布。未保存的输入不会提交。"}
      details={message ? [message] : []} reasonLabel="操作原因（可选，500字以内）" confirmLabel="移入回收站" tone="danger" pending={busy} onCancel={() => setOpen(false)} onConfirm={reason => void remove(reason)} />
  </span>;
}
