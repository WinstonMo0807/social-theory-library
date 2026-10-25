"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { subscribeToSessionChanges } from "@/lib/api";
import { parseResearchTabDraft, researchTabDraftKey, type ResearchTabDraft } from "@/lib/research-tab-draft";

/** Explicit opt-in, bounded tab storage, and the same logout boundary as other reader drafts. */
export function useResearchTabDraft<T>({ owner, project, kind, value, parseInput }: {
  owner: string; project: string; kind: string; value: T | null; parseInput: (value: unknown) => T;
}) {
  const key = researchTabDraftKey(owner, project, kind);
  const [scanned, setScanned] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [recovery, setRecovery] = useState<ResearchTabDraft<T> | null>(null);
  const [error, setError] = useState("");
  const [savedAt, setSavedAt] = useState(0);
  const active = useRef(false), allowed = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    active.current = true;
    let current = true;
    Promise.resolve().then(() => {
      if (!current) return;
      try { setRecovery(parseResearchTabDraft(sessionStorage.getItem(key), owner, project, kind, parseInput)); }
      catch (reason) { setError(reason instanceof Error ? reason.message : "暂存无法读取，原记录仍保留。"); }
      setScanned(true);
    });
    const unsubscribe = subscribeToSessionChanges(() => {
      current = false; active.current = false; allowed.current = false;
      try { sessionStorage.removeItem(key); } catch { /* Session teardown must continue. */ }
      setEnabled(false); setRecovery(null); setSavedAt(0);
    });
    return () => { current = false; active.current = false; unsubscribe(); };
  }, [key, owner, project, kind, parseInput]);

  const capture = useCallback((input: T | null) => {
    if (timer.current !== null) { clearTimeout(timer.current); timer.current = null; }
    if (!active.current || !allowed.current) return false;
    try {
      if (input === null) { sessionStorage.removeItem(key); setSavedAt(0); return true; }
      const at = Date.now();
      const record: ResearchTabDraft<T> = { version: 1, owner, project, kind, at, input: parseInput(input) };
      const raw = JSON.stringify(record);
      if (raw.length > 300000) throw new Error("暂存内容超过本机保存范围。");
      sessionStorage.setItem(key, raw); setSavedAt(at); setError(""); return true;
    } catch (reason) { setError(reason instanceof Error ? reason.message : "本机暂存失败，页面输入仍保留。"); return false; }
  }, [key, owner, project, kind, parseInput]);
  const serialized = JSON.stringify(value);
  useEffect(() => {
    if (!scanned || !enabled || recovery || error) return;
    timer.current = setTimeout(() => capture(JSON.parse(serialized) as T | null), 250);
    return () => { if (timer.current !== null) clearTimeout(timer.current); timer.current = null; };
  }, [scanned, enabled, recovery, error, serialized, capture]);
  function enable() { if (scanned && !recovery && !error) { allowed.current = true; setEnabled(true); capture(value); } }
  function restore() {
    if (!active.current || !recovery) return null;
    const input = recovery.input;
    allowed.current = true; setEnabled(true); setRecovery(null); capture(input);
    return input;
  }
  function clear() {
    if (!active.current) return;
    if (timer.current !== null) { clearTimeout(timer.current); timer.current = null; }
    try { sessionStorage.removeItem(key); allowed.current = false; setEnabled(false); setRecovery(null); setSavedAt(0); setError(""); }
    catch { setError("浏览器未能清除暂存，请通过网站数据设置处理；页面输入和服务器资料仍保留。"); }
  }
  return { scanned, enabled, recovery, error, savedAt, enable, restore, clear, capture };
}
