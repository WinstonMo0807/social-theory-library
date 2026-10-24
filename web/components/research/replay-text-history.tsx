"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { replayPath, replayRequest, type ReplayDetail } from "@/lib/api/research-replay.client";
import type { components } from "@/lib/api/generated/schema";
import styles from "./research-replay.module.css";

type History = components["schemas"]["ReplayHistoryOutput"];
const kinds = { baseline: "保存前记录", edit: "本人编辑", restore: "恢复后保存" };
const date = (value: string) => new Date(value).toLocaleString("zh-CN", { hour12: false });

export function ReplayTextHistory({ owner, id, turnId, active, onChanged }: { owner: string; id: string; turnId: string; active: boolean; onChanged: () => void }) {
  const [page, setPage] = useState(1), [selectedId, setSelectedId] = useState(""), [message, setMessage] = useState(""), [busy, setBusy] = useState(false);
  const request = useRef<AbortController | null>(null), sending = useRef(false);
  useEffect(() => { const controller = new AbortController(); request.current = controller; const off = subscribeToSessionChanges(() => controller.abort()); return () => { controller.abort(); off(); }; }, [owner, id, turnId]);
  const path = `/reading/research-projects/${id}/replay-history/?${new URLSearchParams({ turn_id: turnId, page: String(page), ...(selectedId ? { revision_id: selectedId } : {}) })}`;
  const load = useCallback((url: string, signal: AbortSignal) => replayRequest<History>(owner, url, { signal }), [owner]);
  const resource = usePersistentWorkspace<History>(path, owner, undefined, load);
  const data = resource.error ? null : resource.data, selected = data?.selected;
  async function apply(mode: "restore" | "download") {
    const controller = request.current;
    if (!controller || controller.signal.aborted || sending.current || !selected || !data) return;
    sending.current = true; setBusy(true); setMessage("");
    try {
      if (mode === "restore") {
        await withPrivateOwner(owner, () => replayRequest<ReplayDetail>(owner, replayPath(id), { method: "PATCH", signal: controller.signal,
          body: JSON.stringify({ turn_id: turnId, expected_revision: data.current_revision, restore_id: selected.id }) }), controller.signal);
        if (!controller.signal.aborted) { setMessage("已作为当前回放文字保存。原问题、起始选材和既有历史保留。"); resource.reload(); onChanged(); }
      } else {
        const fresh = await withPrivateOwner(owner, () => replayRequest<History>(owner, path, { signal: controller.signal }), controller.signal);
        if (controller.signal.aborted) return;
        if (fresh.selected?.id !== selected.id || fresh.turn_id !== turnId || typeof fresh.selected.notes !== "string") throw Error("历史版本已变化，请重新读取后保存。");
        const value = fresh.selected;
        const blob = new Blob([`${value.title || "未设置回放名称"}\n\n记录时间：${date(value.recorded_at)}\n主题标签：${value.tags.join("、") || "未设置"}\n\n${value.notes}`], { type: "text/plain;charset=utf-8" });
        const url = URL.createObjectURL(blob), anchor = document.createElement("a");
        anchor.href = url; anchor.download = `research-replay-${turnId}-r${value.revision}.txt`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    } catch (reason) { if (!controller.signal.aborted) { if (reason instanceof ApiRequestError && [401, 403, 404, 410].includes(reason.status)) { setSelectedId(""); resource.reload(); } setMessage(reason instanceof Error ? reason.message : "操作尚未确认，请重新读取后核对。"); } }
    finally { sending.current = false; if (!controller.signal.aborted) setBusy(false); }
  }
  return <section className={styles.textHistory} aria-label="本人回放文字历史"><h3>回放文字历史</h3>
    {resource.error ? <p role="alert">{resource.error}<button disabled={busy} onClick={() => { setSelectedId(""); setPage(1); resource.reload(); }}>重新读取历史</button></p> : !data ? <p role="status">正在读取本人保存记录…</p> : <>
      <p className={styles.branchHint}>{data.notice}</p>
      {!data.count ? <p>尚未保存回放文字修改，没有可回填的旧版本。</p> : <div className={styles.historyColumns}><div><ol>{data.results.map(row => <li key={row.id}><button disabled={busy} aria-pressed={selectedId === row.id} onClick={() => setSelectedId(row.id)}><strong>{row.title || "未设置回放名称"}</strong><small>{kinds[row.kind]} · {date(row.recorded_at)}</small><small>{row.note_length} 字笔记 · {row.tags.length} 个标签</small></button></li>)}</ol><nav className={styles.branchPager} aria-label="文字历史分页"><button disabled={busy || page <= 1} onClick={() => { setPage(value => value - 1); setSelectedId(""); }}>上一页</button><span>{page}/{data.total_pages}</span><button disabled={busy || page >= data.total_pages} onClick={() => { setPage(value => value + 1); setSelectedId(""); }}>下一页</button></nav></div>
        <div className={styles.historyText}>{selected ? <><h4>{selected.title || "未设置回放名称"}</h4><p className={styles.branchHint}>{kinds[selected.kind]} · 记录于 {date(selected.recorded_at)}</p>{selected.source_updated_at ? <p className={styles.branchHint}>对应轮次保存时间：{date(selected.source_updated_at)}</p> : null}<p>{selected.tags.join(" · ") || "没有主题标签"}</p><pre>{selected.notes || "这一版本没有回放笔记。"}</pre><div className={styles.historyActions}><button disabled={busy || active || selected.revision === data.current_revision} onClick={() => void apply("restore")}>将此版本作为当前回放文字</button><button disabled={busy} onClick={() => void apply("download")}>保存此版本为文字文件</button></div><p className={styles.branchHint}>{active ? "本轮仍在处理中，完成或取消后可恢复回放文字。" : "恢复会新增一条保存记录，旧版本继续保留。"}</p></> : <p>选择一个版本，核对完整文字后再恢复或保存。</p>}</div>
      </div>}
    </>}{message ? <p role="status">{message}</p> : null}
  </section>;
}
