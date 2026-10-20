"use client";

import Link from "next/link";
import { BookOpen, CircleAlert, LockKeyhole, X } from "lucide-react";
import { useState } from "react";
import { normalizePublicResourceUrl } from "@/lib/api";
import type { DiscoveryDocument, DiscoveryDocuments } from "@/lib/api/discovery.types";
import { Dialog } from "./ui/dialog";
import styles from "@/app/explore/opinions/viewpoint-search.module.css";

const labels = { queued: "待处理", running: "正在检索", completed: "本轮查询完成", no_returned: "本轮未返回直接材料",
  partial: "部分完成", failed: "本轮查询未完成", waiting_index: "等待正文索引", unreadable: "当前文献暂不可读", changed: "来源已有更新", canceled: "已取消，已有材料保留" };
const tabs = ["全部", "已获材料", "已完成", "进行中", "待处理", "暂不可读"] as const;
type Tab = typeof tabs[number];
function matches(row: DiscoveryDocument, tab: Tab) {
  return tab === "全部" || tab === "已获材料" && row.material_count > 0
    || tab === "已完成" && ["completed", "no_returned"].includes(row.status)
    || tab === "进行中" && row.status === "running"
    || tab === "待处理" && ["queued", "waiting_index", "changed", "failed", "partial", "canceled"].includes(row.status)
    || tab === "暂不可读" && row.status === "unreadable";
}

export function DiscoveryDocumentProgress({ data, busy, onRemove, onView, onAdjust }: {
  data: DiscoveryDocuments; busy: boolean; onRemove: (id: string) => void; onView: (id: string) => void; onAdjust: () => void;
}) {
  const [tab, setTab] = useState<Tab>("全部");
  const [limit, setLimit] = useState(4);
  const [versionId, setVersionId] = useState("");
  const rows = data.items.filter(row => matches(row, tab));
  // Do not retain an old bibliography in an open dialog after revalidation.
  const version = data.items.find(row => row.edition_id === versionId);
  return <section className={styles.documentProgress} aria-label="本次文献处理状态">
    <header><h3>本次文献 <small>{data.tracked} 个出版版本</small></h3>{data.excluded_count ? <span>已移除 {data.excluded_count} 个版本</span> : null}</header>
    <p className={styles.help}>{data.notice}</p>
    {data.truncated ? <p role="status">当前仅列出前200个版本的状态。请缩小范围查看指定文献；检索结果仍来自完整允许范围。</p> : null}
    <div className={styles.documentTabs} role="group" aria-label="文献处理状态筛选">{tabs.map(value => <button type="button" key={value} aria-pressed={tab === value} onClick={() => { setTab(value); setLimit(4); }}>{value} <small>{data.items.filter(row => matches(row, value)).length}</small></button>)}</div>
    {!rows.length ? <p className={styles.help}>当前没有此状态的文献。</p> : rows.slice(0, limit).map(row => <article className={styles.documentRow} key={row.edition_id}>
      <div className={styles.documentCover}>{row.bibliography?.cover_url ? <img src={normalizePublicResourceUrl(row.bibliography.cover_url)} alt="" loading="lazy" /> : <BookOpen size={25} aria-hidden="true" />}</div>
      <div><h4>{row.title}</h4><p>{[row.authors.join("、"), row.bibliography?.publication_year, row.bibliography?.version_label].filter(Boolean).join(" · ")}</p>
        <div className={styles.documentState} data-state={row.status}>{row.status === "unreadable" ? <LockKeyhole size={16} /> : ["failed", "changed"].includes(row.status) ? <CircleAlert size={16} /> : null}<strong>{labels[row.status]}</strong>{row.material_count ? <span>已获得 {row.material_count} 段原文</span> : null}</div>
        {row.status === "no_returned" ? <p>本轮有限候选中没有返回该版本的材料，可调整问题或筛选。此状态不判定相关性高低。</p> : null}
        {row.status === "unreadable" ? <p>当前全文不可访问或尚未就绪，其他文献的已有结果继续保留。</p> : null}
        <div className={styles.documentActions}>{row.material_count ? <button type="button" disabled={busy} onClick={() => onView(row.edition_id)}>查看结果 →</button> : null}
          {row.available_versions.length ? <button type="button" onClick={() => setVersionId(row.edition_id)}>查看公开版本</button> : null}
          {row.status === "no_returned" ? <button type="button" onClick={onAdjust}>调整筛选条件</button> : null}
          <button type="button" disabled={busy} onClick={() => onRemove(row.edition_id)}>从本次检索移除</button></div>
      </div>
    </article>)}
    {rows.length > limit ? <button className="text-link" type="button" onClick={() => setLimit(value => value + 10)}>查看更多文献状态</button> : null}
    <Dialog open={Boolean(version)} onRequestClose={() => setVersionId("")} className={styles.filterDialog} aria-labelledby="document-versions-title"><header className={styles.dialogHeader}><h2 id="document-versions-title">已公开的出版版本</h2><button type="button" aria-label="关闭版本列表" onClick={() => setVersionId("")}><X size={18} /></button></header>
      <p>{version?.title}。进入版本详情核对当前阅读资格。</p><ul>{version?.available_versions.map(row => <li key={row.id}><Link href={row.url}>{row.label}</Link></li>)}</ul>
    </Dialog>
  </section>;
}
