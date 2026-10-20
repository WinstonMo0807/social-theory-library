"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ListPlus, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { readAllPages } from "@/lib/api/read-all-pages";
import { usePublicSession } from "./public-session-provider";
import { Dialog } from "./ui/dialog";

type ReadingListChoice = { id: string; title: string; items: { work: string }[] };

export function AddWorkToListButton({ workId, title }: { workId: string; title: string }) {
  const router = useRouter();
  const { state: session } = usePublicSession();
  const owner = session.status === "authenticated" && session.user ? String(session.user.id) : "";
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<{ owner: string; lists: ReadingListChoice[] } | null>(null);
  const [selected, setSelected] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const generation = useRef(0);
  const closeRef = useRef<HTMLButtonElement>(null);
  const lists = result?.owner === owner ? result.lists : null;
  useEffect(() => subscribeToSessionChanges(() => { generation.current += 1; setOpen(false); setResult(null); setSelected(""); setMessage(""); setBusy(false); }), []);
  useEffect(() => {
    const controller = new AbortController();
    const epoch = ++generation.current;
    if (open && owner) withPrivateOwner(owner, () => readAllPages<ReadingListChoice>("/reading/lists/", getServerSessionCredential()!, controller.signal, owner), controller.signal).then(lists => {
      if (!controller.signal.aborted && epoch === generation.current) { setResult({ owner, lists }); setSelected(""); }
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted && epoch === generation.current) setMessage(reason instanceof Error ? reason.message : "书单暂时无法读取。");
    });
    return () => { controller.abort(); generation.current += 1; };
  }, [open, owner, attempt]);
  function show() {
    if (!owner) { router.push(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`); return; }
    setResult(null); setMessage(""); setSelected(""); setOpen(true);
  }
  async function add() {
    if (!owner || !selected || busy) return;
    const epoch = generation.current;
    setBusy(true); setMessage("");
    try {
      await withPrivateOwner(owner, () => apiRequest(`/reading/lists/${selected}/add_item/`, { method: "POST", headers: { "X-Reader-Owner": owner }, body: JSON.stringify({ work: workId }), signal: AbortSignal.timeout(30000) }, getServerSessionCredential(), false));
      if (epoch === generation.current) {
        setMessage("已加入书单。");
        setResult(current => current?.owner === owner ? { ...current, lists: current.lists.map(list => list.id === selected ? { ...list, items: [...list.items.filter(item => item.work !== workId), { work: workId }] } : list) } : current);
      }
    } catch (reason) {
      if (epoch === generation.current) setMessage(`${reason instanceof Error ? reason.message : "暂时无法确认加入结果。"} 可以重试同一书单，已加入的文献不会重复添加。`);
    } finally { if (epoch === generation.current) setBusy(false); }
  }
  const alreadyAdded = lists?.find(list => list.id === selected)?.items.some(item => item.work === workId);
  return <><button type="button" onClick={show} disabled={session.status === "loading"}><ListPlus size={14} />加入书单</button>
    <Dialog open={open && Boolean(owner)} className="stl4-catalog-list-dialog" aria-label="加入书单" initialFocusRef={closeRef} onRequestClose={() => { if (!busy) setOpen(false); }}>
      <header><h2>加入书单</h2><button type="button" ref={closeRef} aria-label="关闭书单选择" disabled={busy} onClick={() => setOpen(false)}><X size={18} /></button></header><p>{title}</p>
      {lists ? lists.length ? <label>选择你的书单<select value={selected} onChange={event => { setSelected(event.target.value); setMessage(""); }} disabled={busy}><option value="">请选择</option>{lists.map(list => <option key={list.id} value={list.id}>{list.title}{list.items.some(item => item.work === workId) ? "（已加入）" : ""}</option>)}</select></label> : <p>还没有书单。<Link href="/account?section=lists">前往我的书单创建</Link></p> : !message ? <p role="status">正在读取你的书单…</p> : <button type="button" onClick={() => { setMessage(""); setAttempt(value => value + 1); }}>重新读取书单</button>}
      {message ? <p role="status">{message}</p> : null}<footer><button type="button" disabled={busy} onClick={() => setOpen(false)}>关闭</button><button type="button" disabled={!selected || busy || alreadyAdded} onClick={() => void add()}>{busy ? "正在加入…" : alreadyAdded ? "已在书单中" : "加入书单"}</button></footer>
    </Dialog>
  </>;
}
