"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import type { RecycleCollection, RecycleEntry } from "@/lib/api/recycle.types";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { AdminPublicPreviewFrame } from "./admin-public-preview-frame";
import { PageHeader } from "@/components/admin-ui";

const labels: Record<string, string> = { upload: "上传", work: "作品", edition: "出版版本", person: "人物", scholar: "学者", topic: "主题", "knowledge-node": "理论与概念", "theory-school": "理论流派", discipline: "学科", subdiscipline: "子学科", "reading-path": "阅读路径", "recommendation-issue": "推荐期", "about-block": "网站内容" };
const destinations: Record<string, string> = { upload: "/admin/review", work: "/admin/library", edition: "/admin/library", scholar: "/admin/scholars", person: "/admin/scholars/people", topic: "/admin/topics", "knowledge-node": "/admin/theories", "theory-school": "/admin/theories", "recommendation-issue": "/admin/recommendations", "about-block": "/admin/about" };
const tabs = [["", "全部"], ["work,edition,upload", "馆藏"], ["scholar,person", "学者"], ["knowledge-node,theory-school", "理论流派"], ["topic", "主题"], ["recommendation-issue", "荐读文章"]];

export function RecycleBin() {
  const [kind, setKind] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [previewed, setPreviewed] = useState("");
  const [perspective, setPerspective] = useState<"restore" | "current">("restore");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const active = useRef(false);
  const [confirmation, setConfirmation] = useState<RecycleEntry[]>([]);
  const [notice, setNotice] = useState<{ message: string; href?: string; error?: boolean } | null>(null);
  const resource = useApiResource<RecycleCollection>(`/catalog/admin/recycle/?offset=${offset}&search=${encodeURIComponent(query)}&kind=${encodeURIComponent(kind)}`, getServerSessionCredential());
  const entries = resource.data?.results ?? [];
  const selectedEntries = entries.filter(entry => selected.includes(entry.id));
  function clearSelection() { setSelected([]); setPreviewed(""); setPerspective("restore"); }
  function toggle(entry: RecycleEntry) {
    setSelected(current => current.includes(entry.id) ? current.filter(id => id !== entry.id) : [...current, entry.id]);
    setPreviewed(entry.id); setPerspective("restore");
  }
  function count(value: string) {
    if (!resource.data) return null;
    return value ? value.split(",").reduce((sum, key) => sum+(resource.data!.kind_counts[key] ?? 0), 0) : resource.data.total_count;
  }
  async function restore() {
    if (active.current || !confirmation.length) return;
    active.current = true; setBusy(true);
    const batch = confirmation;
    try {
      const result = await apiRequest<{ restored: boolean; count?: number; id?: string }>("/catalog/admin/recycle/", {
        method: "POST", body: JSON.stringify(batch.length === 1 ? { id: batch[0].id } : { ids: batch.map(entry => entry.id) }),
      }, getServerSessionCredential());
      if (!result.restored || (batch.length > 1 ? result.count !== batch.length : result.id !== batch[0].object_id)) throw new Error("恢复结果与本次选择不符，请刷新列表核对，避免重复提交。");
      setNotice({ message: batch.length === 1 ? `已恢复“${batch[0].name}”。可继续编辑，尚未重新发布或启动处理。` : `已恢复 ${batch.length} 项。请回到对应编辑区检查，尚未重新发布或启动处理。`, href: batch.length === 1 ? destinations[batch[0].kind] : undefined });
      setConfirmation([]); clearSelection(); resource.retry();
    } catch (error) { setNotice({ message: error instanceof Error ? error.message : "恢复结果尚未确认，请刷新列表核对。", error: true }); }
    finally { active.current = false; setBusy(false); }
  }
  return <div className="admin-page recycle-reference">
    <PageHeader title="回收站" description="删除的内容保留在这里。恢复后回到管理列表，不自动发布或重启后台任务。下架的内容仍在原管理列表。"/>
    <div className="recycle-reference-columns">
      <section className="admin-panel">
        <nav className="reference-tabs" aria-label="回收内容类型">{tabs.map(([value, label]) => <button type="button" key={value} disabled={busy} aria-current={kind === value ? "true" : undefined} onClick={() => { setKind(value); setOffset(0); clearSelection(); }}>{label}{count(value) !== null ? ` (${count(value)})` : ""}</button>)}</nav>
        <form className="admin-action-row" onSubmit={event => { event.preventDefault(); if (busy) return; setOffset(0); setQuery(String(new FormData(event.currentTarget).get("q") || "")); clearSelection(); }}>
          <input name="q" aria-label="搜索已删除内容" placeholder="按名称查找" disabled={busy}/><button type="submit" disabled={busy}>查找</button><button type="button" disabled={busy} onClick={resource.retry}>刷新</button>
        </form>
        {notice ? <p role={notice.error ? "alert" : "status"}>{notice.message} {notice.href ? <Link href={notice.href}>前往管理列表</Link> : null}</p> : null}
        {resource.error ? <p role="alert">{resource.error}</p> : resource.loading ? <p role="status">正在读取…</p> : resource.data ? <>
          <div className="recycle-selection-actions"><span>共 {resource.data.count} 项{selectedEntries.length ? ` · 本页已选 ${selectedEntries.length} 项` : ""}</span><button type="button" className="button secondary" disabled={busy || !selectedEntries.length} onClick={() => setConfirmation(selectedEntries)}>恢复所选{selectedEntries.length ? ` (${selectedEntries.length})` : ""}</button></div>
          <div className="admin-table-scroll"><table><thead><tr><th><input type="checkbox" aria-label="选择本页全部内容" disabled={busy || !entries.length} checked={Boolean(entries.length) && selectedEntries.length === entries.length} onChange={event => setSelected(event.target.checked ? entries.map(entry => entry.id) : [])}/></th><th>标题</th><th>类型</th><th>删除时间</th><th>删除原因</th><th>操作</th></tr></thead>
            <tbody>{entries.map(entry => <tr key={entry.id} data-selected={previewed === entry.id}>
              <td><input type="checkbox" aria-label={`选择${entry.name}`} disabled={busy} checked={selected.includes(entry.id)} onChange={() => toggle(entry)}/></td>
              <td><button className="reference-select-title" type="button" disabled={busy} onClick={() => { setPreviewed(entry.id); setPerspective("restore"); }}>{entry.name}</button></td>
              <td>{labels[entry.kind] || "管理内容"}</td><td>{new Date(entry.deleted_at).toLocaleString("zh-CN")}</td><td>{entry.reason || "未记录"}</td>
              <td><button type="button" className="button secondary" disabled={busy} onClick={() => { setPreviewed(entry.id); setPerspective("restore"); setConfirmation([entry]); }}>恢复</button></td>
            </tr>)}</tbody>
          </table></div>
          {!entries.length ? <p>没有符合条件的已删除内容。</p> : null}
          <div className="admin-action-row"><button type="button" disabled={busy || offset === 0} onClick={() => { setOffset(Math.max(0, offset-50)); clearSelection(); }}>上一页</button><button type="button" disabled={busy || offset+50 >= resource.data.count} onClick={() => { setOffset(offset+50); clearSelection(); }}>下一页</button></div>
        </> : null}
      </section>
      <AdminPublicPreviewFrame title="选中内容的读者预览" description="恢复后仍未公开，需要返回编辑区检查并发布。" src={previewed && perspective === "restore" ? `/admin/preview/recycle/${previewed}?embed=1` : null} emptyMessage={previewed && perspective === "current" ? "这条内容已移入回收站，当前没有公开页面。恢复后仍需检查并发布。" : "选择一条内容，查看恢复后的效果。"}>
        <nav className="reference-tabs" aria-label="恢复预览状态"><button type="button" aria-current={perspective === "restore" ? "true" : undefined} onClick={() => setPerspective("restore")}>恢复后效果（未公开）</button><button type="button" aria-current={perspective === "current" ? "true" : undefined} onClick={() => setPerspective("current")}>当前线上（已删除）</button></nav>
      </AdminPublicPreviewFrame>
    </div>
    <ConfirmDialog open={Boolean(confirmation.length)} title={confirmation.length > 1 ? `恢复所选 ${confirmation.length} 项` : `恢复“${confirmation[0]?.name || ""}”`} description="确认后回到对应管理列表，仍未公开，不会恢复旧的公开修订或重启任务。若有记录受阻，整批不会提交。" details={confirmation.map(entry => entry.name)} confirmLabel="确认恢复" pending={busy} onCancel={() => { if (!busy) setConfirmation([]); }} onConfirm={() => void restore()}/>
  </div>;
}
