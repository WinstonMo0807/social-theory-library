"use client";
import { SourceText } from "@/components/source-text";


import { confirmAction } from "@/lib/ui-dialog";


import { LoadingState } from "@/components/ui/loading-state";
import { useCallback, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import type { PlacementCommand, PlacementState, PlacementPage } from "@/lib/api/curation-workspace.client";
import styles from "./concept-editor.module.css";

type HistoryPage = { count: number; next: string | null; previous: string | null; results: { id: string; revision: number; status: string; created_at: string; published_at: string | null; item_count: number; withdrawn: boolean }[] };
export function PlacementHistory({ nodeId, owner, current, locked, act, pageType = "node", initialRevisionId = "" }: { initialRevisionId?: string; pageType?: PlacementPage; nodeId: string; owner: string; current: PlacementState; locked: boolean; act: (body: Omit<PlacementCommand, "request_id">) => Promise<void> }) {
  const [page, setPage] = useState(1), [selected, setSelected] = useState(initialRevisionId);
  const path = `/catalog/admin/content-placements/${pageType}/${nodeId}/`;
  const load = useCallback((url: string, signal: AbortSignal) => apiRequest<HistoryPage>(url, {signal,cache:"no-store",headers:{"X-Editor-Owner":owner}}, getServerSessionCredential()), [owner]);
  const loadVersion = useCallback((url: string, signal: AbortSignal) => apiRequest<PlacementState>(url, {signal,cache:"no-store",headers:{"X-Editor-Owner":owner}}, getServerSessionCredential()), [owner]);
  const history = usePersistentWorkspace<HistoryPage>(`${path}history/?page=${page}`, owner, undefined, load);
  const version = usePersistentWorkspace<PlacementState>(selected ? `${path}?revision=${selected}` : "", owner, undefined, loadVersion);
  return <section className={styles.panel}><h2>内容编排历史</h2><p>恢复会将所选历史内容保存为新的草稿，保留此前版本；不会自动发布或改绑原文。</p>
    <button type="button" disabled={locked || !current.revision_id} onClick={async () => { if ((await confirmAction("撤销最近一次编排，将其之前的内容保存为新草稿？公开页不会因此改变。"))) void act({action:"undo",expected_revision:current.expected_revision!}).then(history.reload); }}>撤销最近编排</button>
    {history.error ? <p role="alert">{history.error}<button type="button" onClick={history.reload}>重新读取历史</button></p> : !history.data ? <LoadingState role="status">正在读取原修订…</LoadingState> : <><ul>{history.data.results.map(row => <li key={row.id}><strong>修订 {row.revision}</strong> · {row.withdrawn ? "撤回记录" : row.status === "draft" ? "草稿" : row.status === "published" ? "当前发布" : "历史版本"} · {row.item_count} 项 · {new Date(row.created_at).toLocaleString("zh-CN")} <button type="button" aria-pressed={selected === row.id} onClick={() => setSelected(row.id)}>查看此版</button></li>)}</ul>{!history.data.results.length ? <p>还没有保存过编排。</p> : null}<nav className={styles.pagination} aria-label="编排历史分页"><button type="button" disabled={!history.data.previous} onClick={() => setPage(value => value - 1)}>上一页</button><span>第 {page} 页</span><button type="button" disabled={!history.data.next} onClick={() => setPage(value => value + 1)}>下一页</button></nav></>}
    {selected ? version.error ? <p role="alert">{version.error}<button type="button" onClick={version.reload}>重新读取此版</button></p> : !version.data ? <LoadingState role="status">正在核对历史来源…</LoadingState> : <section><h3>所选版本中的准确来源</h3><ol>{version.data.items.map(row => <li key={row.id}><strong>{row.source?.title || "原来源当前不可用"}</strong>{row.concept_usage ? <p>{String(row.concept_usage.term || "")} · {String(row.concept_usage.interpretation || "")}</p> : <p>{row.reason}</p>}{row.source?.text ? <blockquote className={styles.quote}><SourceText text={(row.source.text) || ""} /></blockquote> : null}</li>)}</ol>{version.data.source_problems?.length ? <p>此版包含待核对的来源。恢复后仍须重新确认公开条件。</p> : null}<button type="button" disabled={locked || selected === current.revision_id} onClick={async () => { if ((await confirmAction("将所选历史编排恢复为新的草稿？现有版本保留，公开内容需另行确认。"))) void act({action:"restore",revision_id:selected,expected_revision:current.expected_revision!}).then(history.reload); }}>恢复为新草稿</button></section> : null}
  </section>;
}
