"use client";


import { LoadingState } from "@/components/ui/loading-state";
import { useState } from "react";
import { PrivateMediaImage } from "./media-crop";
import { useOwnedRead } from "./media-requests";
import styles from "./media-workspace.module.css";

type LegacyImage = { source: string; record_id: string; created_at: string; label: string; fingerprint: string; url: string };
type Collection = { count: number; page: number; pages: number; results: LegacyImage[] };
export type LegacyImageChoice = { legacy_source: string; legacy_record_id: string; legacy_fingerprint: string };

export function LegacyMediaHistory({ owner, objectType, objectId, slot, disabled, onSelect }: {
  owner: string; objectType: string; objectId: string; slot: string; disabled: boolean; onSelect: (choice: LegacyImageChoice) => void;
}) {
  const [page, setPage] = useState(1);
  const history = useOwnedRead<Collection>(owner, `/catalog/admin/media-legacy/${objectType}/${objectId}/?${new URLSearchParams({ slot, page: String(page) })}`);
  return <section className={styles.history} aria-label="旧文件图片记录">
    <h3>旧文件图片 {history.data ? <small>{history.data.count} 条记录</small> : null}</h3>
    <p className={styles.note}>来自当前对象、编辑和发布记录。选择后先准备为候选，裁切并保存才会形成新修订。同一原图可能被多条记录保留；没有记录的旧文件不会被推测补入。</p>
    {history.error ? <p role="alert">{history.error}<button onClick={history.retry}>重新读取</button></p> : !history.data ? <LoadingState role="status">正在读取旧图片记录…</LoadingState> : <>
      <div className={styles.historyStrip}>{history.data.results.map(row => <button key={`${row.source}:${row.record_id}`} disabled={disabled} onClick={() => onSelect({ legacy_source: row.source, legacy_record_id: row.record_id, legacy_fingerprint: row.fingerprint })}>
        <PrivateMediaImage owner={owner} path={row.url} alt={row.label} /><span>{row.label}</span><small>{new Date(row.created_at).toLocaleDateString("zh-CN")}</small><span>准备此图</span>
      </button>)}</div>
      {!history.data.count ? <p className={styles.note}>此对象没有记录在册的旧文件图片。</p> : null}
      {history.data.pages > 1 ? <div className={styles.controls}><button disabled={history.data.page <= 1} onClick={() => setPage(history.data!.page - 1)}>上一页</button><span>{history.data.page}/{history.data.pages}</span><button disabled={history.data.page >= history.data.pages} onClick={() => setPage(history.data!.page + 1)}>下一页</button></div> : null}
    </>}
  </section>;
}
