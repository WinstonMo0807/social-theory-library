"use client";

import type { Dispatch, SetStateAction } from "react";
import { useContextState } from "@/lib/use-context-state";

type Entry<T> = { id: string; before: Partial<T>; after: Partial<T> };

export function useEditorialPrefills<T extends object>(scope: string, draft: T, setDraft: Dispatch<SetStateAction<T>>, changed?: () => void) {
  const [entries, setEntries] = useContextState<Entry<T>[]>(scope, []);
  const [message, setMessage] = useContextState(scope, "");
  const [decisions, setDecisions] = useContextState<Record<string, "modified" | "removed">>(scope, {});
  function fill(id: string, update: (current: T) => T) {
    const next = update(draft);
    const keys = (Object.keys(next) as (keyof T)[]).filter((key) => JSON.stringify(next[key]) !== JSON.stringify(draft[key]));
    if (!keys.length) { setMessage("表单中已经有这项内容，没有重复添加。"); return false; }
    const before: Partial<T> = {}, after: Partial<T> = {};
    for (const key of keys) { before[key] = draft[key]; after[key] = next[key]; }
    setDraft(next);
    setEntries((current) => [...current, { id, before, after }]);
    changed?.();
    setMessage("建议已填入本页，尚未保存。可以继续修改，或撤销刚才的填写。");
    return true;
  }
  function undo() {
    const entry = entries.at(-1);
    if (!entry) return;
    const keys = Object.keys(entry.after) as (keyof T)[];
    if (keys.some((key) => JSON.stringify(draft[key]) !== JSON.stringify(entry.after[key]))) {
      setMessage("这项填写之后又有修改，为保护你的输入不能自动撤销。请在对应字段中手工调整。");
      return;
    }
    setDraft((current) => ({ ...current, ...entry.before }));
    setEntries((current) => current.slice(0, -1));
    changed?.();
    setMessage("已撤销刚才的填写，其他字段保持不变。尚未保存。");
  }
  return {
    ids: [...new Set(entries.map((entry) => entry.id).filter(Boolean))],
    decisions,
    reviews: entries.filter((entry) => entry.id && Object.keys(entry.after).some((key) => JSON.stringify(draft[key as keyof T]) !== JSON.stringify(entry.after[key as keyof T]))).map((entry) => ({ id: entry.id, value: Object.values(entry.after).map(String).join("、").slice(0, 120) })),
    review: (id: string, decision: "modified" | "removed") => setDecisions((current) => ({ ...current, [id]: decision })),
    fill, undo, count: entries.length, message,
    clear: () => { setEntries([]); setMessage(""); setDecisions({}); },
  };
}

export function EditorialPrefillNotice({ state }: { state: { count: number; message: string; undo: () => void; reviews?: Array<{ id: string; value: string }>; decisions?: Record<string, string>; review?: (id: string, decision: "modified" | "removed") => void } }) {
  if (!state.message) return null;
  return <aside className="curation-prefill-notice" aria-live="polite"><p>{state.message}</p>{state.count ? <button type="button" onClick={state.undo}>撤销上一次建议填写</button> : null}{state.reviews?.map((row) => <label key={row.id}><span>这项建议填入后有调整：{row.value}</span><select value={state.decisions?.[row.id] || ""} onChange={(event) => { if (event.target.value) state.review?.(row.id, event.target.value as "modified" | "removed"); }}><option value="">仅记录最终填写，不推断是否采用</option><option value="modified">修改后继续使用</option><option value="removed">不再使用这项建议</option></select></label>)}</aside>;
}
