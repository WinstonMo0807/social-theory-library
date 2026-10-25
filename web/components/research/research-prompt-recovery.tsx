"use client";

import { useEffect, useEffectEvent, useRef, useState } from "react";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { subscribeToSessionChanges } from "@/lib/api";
import { parseResearchPrompt, researchPromptKey, type ResearchPromptInput, type ResearchPromptRecovery as Recovery } from "@/lib/research-prompt-recovery";

export function ResearchPromptRecovery({ owner, project, input, disabled, onRestore, onReconnect }: {
  owner: string; project: string; input: ResearchPromptInput; disabled: boolean;
  onRestore: (value: ResearchPromptInput) => void; onReconnect: () => void;
}) {
  const key = researchPromptKey(owner, project);
  const [enabled, setEnabled] = useState(false);
  const [scanned, setScanned] = useState(false);
  const [recovery, setRecovery] = useState<Recovery | null>(null);
  const [error, setError] = useState("");
  const [savedAt, setSavedAt] = useState(0);
  const [offline, setOffline] = useState(false);
  const [confirm, setConfirm] = useState<"restore" | "clear" | null>(null);
  const sessionActive = useRef(true);
  const reconnect = useEffectEvent(onReconnect);
  useEffect(() => {
    let active = true;
    sessionActive.current = true;
    Promise.resolve().then(() => {
      if (!active) return;
      setOffline(!navigator.onLine);
      try { setRecovery(parseResearchPrompt(sessionStorage.getItem(key), owner, project)); }
      catch (reason) { setError(reason instanceof Error ? reason.message : "暂存读取失败，原输入仍保留。"); }
      setScanned(true);
    });
    const online = () => { setOffline(false); reconnect(); };
    const disconnected = () => setOffline(true);
    window.addEventListener("online", online); window.addEventListener("offline", disconnected);
    const unsubscribe = subscribeToSessionChanges(() => {
      active = false;
      sessionActive.current = false;
      try { sessionStorage.removeItem(key); } catch { /* Logout must still continue. */ }
      setEnabled(false); setRecovery(null); setSavedAt(0);
    });
    return () => { active = false; unsubscribe(); window.removeEventListener("online", online); window.removeEventListener("offline", disconnected); };
  }, [key, owner, project]);
  const question = input.question, scope = input.scope;
  useEffect(() => {
    if (!scanned || !enabled || recovery || error) return;
    const timer = window.setTimeout(() => {
      if (!sessionActive.current) return;
      try {
        const at = Date.now();
        sessionStorage.setItem(key, JSON.stringify({ version: 1, owner, project, at, input: { question, scope } } satisfies Recovery));
        setSavedAt(at);
      } catch { setError("浏览器未能暂存本次输入，当前文字仍在页面中。请先复制保留，再恢复连接。 "); setEnabled(false); }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [scanned, enabled, recovery, error, key, owner, project, question, scope]);
  function clear() {
    try { sessionStorage.removeItem(key); setRecovery(null); setEnabled(false); setSavedAt(0); setError(""); setConfirm(null); }
    catch { setError("浏览器未能清除本机暂存，请使用浏览器的网站数据设置清除；服务器研究没有改变。"); }
  }
  function restore() {
    if (!recovery || disabled) return;
    onRestore(recovery.input); setRecovery(null); setEnabled(true); setSavedAt(0); setConfirm(null);
  }
  return <section className="stl4-research-prompt-recovery" aria-label="追问输入恢复">
    {offline ? <p role="status">浏览器显示离线。已读取的资料仍可查看，追问尚未发送；网络恢复后只重新读取状态。</p> : null}
    {recovery ? <div><strong>本标签页有待恢复的追问</strong><p className="stl4-research-notes-copy">{recovery.input.question || "空白追问"}</p><p>暂存于 {new Date(recovery.at).toLocaleString()}，范围选择：{{ saved: "已保存的范围", selected: "仅当前选材", library: "全馆" }[recovery.input.scope]}。范围和来源会按当前研究重新核对。</p><div className="stl4-comparison-inline-actions"><button type="button" disabled={disabled} onClick={() => input.question && input.question !== recovery.input.question ? setConfirm("restore") : restore()}>恢复到输入框</button><button type="button" disabled={disabled} onClick={() => setConfirm("clear")}>清除此暂存</button></div></div> : <label><input type="checkbox" checked={enabled} disabled={!scanned || disabled || Boolean(error)} onChange={event => { if (event.target.checked) setEnabled(true); else setConfirm("clear"); }}/>允许在此标签页暂存追问输入</label>}
    <p>仅暂存追问文字和范围选择，不保存原文、选材正文或密码，不自动上传。暂存可被此浏览器读取；退出或重新登录账户时清除，关闭标签页后不保证恢复。</p>
    {savedAt ? <p role="status">已暂存本次追问 · {new Date(savedAt).toLocaleTimeString()}，尚不代表服务器已保存。</p> : null}
    {error ? <p role="alert">{error}<button type="button" disabled={disabled} onClick={() => setConfirm("clear")}>清除本机暂存</button></p> : null}
    <ConfirmDialog open={confirm !== null} title={confirm === "restore" ? "用暂存追问替换当前输入？" : "清除本标签页的追问暂存？"} description={confirm === "restore" ? "当前输入会被上方暂存文字替换。服务器已保存的研究不变。" : "仅清除此研究在当前标签页中的暂存，并关闭自动暂存。页面当前输入和服务器研究保留。"} confirmLabel={confirm === "restore" ? "恢复暂存追问" : "清除暂存"} cancelLabel="返回" pending={disabled} onCancel={() => setConfirm(null)} onConfirm={() => { if (confirm === "restore") restore(); else clear(); }}/>
  </section>;
}
