"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { createRequestKey } from "@/lib/request-key";
import { useAssistantCommands } from "./assistant-commands";
import { useAdminSession } from "@/lib/admin-session";
import { withPrivateOwner } from "@/lib/api/private-owner";

type Person = { id: string; name?: string; label?: string };

/** Creation has its own receipt; the book association remains an explicit save. */
export function ContributorCreate({ editionId, name, role, disabled, onSelect }: {
  editionId: string; name: string; role: string; disabled: boolean;
  onSelect: (person: { id: string; name: string }) => void;
}) {
  const decisions=useAssistantCommands(),user=useAdminSession(),owner=user?String(user.id):"";
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [matches, setMatches] = useState<Person[]>([]);
  const [checkedName, setCheckedName] = useState("");
  const active = useRef(false);
  const mounted = useRef(true);
  const selectLatest = useRef(onSelect);
  const contextKey = JSON.stringify([owner, editionId, role, name.trim()]);
  const latestContext = useRef(contextKey);
  useLayoutEffect(() => { selectLatest.current = onSelect; latestContext.current = contextKey; }, [onSelect, contextKey]);
  const receipt = useRef<{ name: string; id: string; sent?: boolean; distinct?: boolean } | null>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const label = role === "translator" ? "译者" : "人物";

  async function create(distinct = false) {
    const clean = name.trim();
    if (!clean || active.current || disabled) return;
    active.current = true; setBusy(true); setMessage("");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20_000);
    try {
      const token = getServerSessionCredential();
      if (!token) throw new Error("登录已失效，请重新登录。当前填写保留。");
      if (!receipt.current || receipt.current.name !== clean) receipt.current = { name: clean, id: createRequestKey() };
      if (!receipt.current.sent && (!distinct || checkedName !== clean)) {
        const found = await withPrivateOwner(owner,()=>apiRequest<{ matches: Person[] }>("/catalog/admin/field-assistant/duplicates/", {
          method: "POST", cache:"no-store", headers:{"X-Editor-Owner":owner}, signal: controller.signal, body: JSON.stringify({ field_name: role === "translator" ? "translator" : "author", label: clean }),
        }, token,false),controller.signal);
        if (!mounted.current) return;
        if (latestContext.current !== contextKey) { setMessage("本行填写已变化，尚未新建人物。请核对当前姓名后再操作。"); return; }
        setMatches(found.matches); setCheckedName(clean);
        if (found.matches.length) { setMessage("已有相近人物，请选择；确为不同的人时再新建。"); return; }
      }
      if (!receipt.current.sent) receipt.current.distinct = distinct && checkedName === clean;
      receipt.current.sent = true;
      const input={ edition_id: editionId, field_name: role === "translator" ? "translator" : "author", label: clean, defer_link: true, request_id: receipt.current.id, allow_possible_duplicate: Boolean(receipt.current.distinct) };
      const response=decisions?await decisions.send("create",input.field_name,input) as {entity:{id:string;name:string}}:await withPrivateOwner(owner,()=>apiRequest<{entity:{id:string;name:string}}>("/catalog/admin/field-assistant/create/",{method:"POST",cache:"no-store",headers:{"X-Editor-Owner":owner},signal:controller.signal,body:JSON.stringify(input)},token,false),controller.signal);
      if (mounted.current) {
        if (latestContext.current === contextKey) { selectLatest.current(response.entity); setMessage("人物已建立并选入本行，请保存作者与译者。"); }
        else setMessage(`已建立${response.entity.name}，本行填写已变化，请重新查找并选择该人物。`);
        setMatches([]);
        window.dispatchEvent(new Event("stl-people-updated"));
      }
    } catch (error) { if (mounted.current) setMessage(decisions ? (error instanceof Error ? error.message : "尚未确认成功，请查回材料助手的原决定。") : controller.signal.aborted ? "响应超时，人物可能已建立。再次点击会查询同一次创建，不重复建人。" : error instanceof Error ? error.message : "尚未确认成功，请重试。"); }
    finally { clearTimeout(timeout); active.current = false; if (mounted.current) setBusy(false); }
  }
  return <div className="contributor-create">
    <button type="button" className="button secondary" disabled={disabled || busy || !name.trim()} onClick={() => void create()}>{busy ? "正在核对并创建…" : `新建${label}“${name.trim() || "请先填写姓名"}”`}</button>
    {message ? <p role="status">{message}</p> : null}
    {checkedName === name.trim() && matches.length ? <div className="contributor-matches">{matches.map(person => <button type="button" key={person.id} disabled={busy || disabled} onClick={() => { onSelect({ id: person.id, name: person.name || person.label || name }); setMatches([]); setMessage("已选入本行，请保存作者与译者。"); }}>选择 {person.name || person.label}</button>)}<button type="button" disabled={busy || disabled} onClick={() => void create(true)}>已核对，创建同名的不同人物</button></div> : null}
  </div>;
}
