"use client";

import Link from "next/link";
import { useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { AdminPublicPreviewFrame } from "./admin-public-preview-frame";
import { PageHeader } from "@/components/admin-ui";

type Entry = { id: string; kind: string; object_id: string; name: string; deleted_at: string };
const labels: Record<string, string> = { upload: "上传", work: "作品", edition: "出版版本", person: "人物", scholar: "学者", topic: "主题", "knowledge-node": "理论与概念", "theory-school": "理论流派", discipline: "学科", subdiscipline: "子学科", "reading-path": "阅读路径", "recommendation-issue": "推荐期", "about-block": "网站内容" };
const destinations: Record<string, string> = { upload: "/admin/review", work: "/admin/library", edition: "/admin/library", scholar: "/admin/scholars", person: "/admin/scholars/people", topic: "/admin/topics", "knowledge-node": "/admin/theories", "theory-school": "/admin/theories", "recommendation-issue": "/admin/recommendations", "about-block": "/admin/about" };
export function RecycleBin() {
  const [kind,setKind]=useState("");
  const [selected,setSelected]=useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState<{ message: string; href?: string; error?: boolean } | null>(null);
  const resource = useApiResource<{ count: number; results: Entry[] }>(`/catalog/admin/recycle/?offset=${offset}&search=${encodeURIComponent(query)}&kind=${encodeURIComponent(kind)}`, getServerSessionCredential());
  async function restore(entry: Entry) {
    if (busy) return;
    setBusy(entry.id);
    try {
      await apiRequest("/catalog/admin/recycle/", { method: "POST", body: JSON.stringify({ id: entry.id }) }, getServerSessionCredential());
      setNotice({ message: `已恢复“${entry.name}”。可继续编辑，尚未重新发布或启动处理。`, href: destinations[entry.kind] });
      resource.retry();
    } catch (error) { setNotice({ message: error instanceof Error ? error.message : "恢复失败", error: true }); }
    finally { setBusy(""); }
  }
  return <div className="admin-page recycle-reference"><PageHeader eyebrow="内容管理" title="回收站" description="删除的内容保留在这里。恢复后回到管理列表，不自动发布或重启后台任务。下架的内容仍在原管理列表。" />
    <div className="recycle-reference-columns"><section className="admin-panel"><nav className="reference-tabs" aria-label="回收内容类型">{[["","全部"],["work,edition,upload","馆藏"],["scholar,person","学者"],["knowledge-node,theory-school","理论流派"],["topic","主题"],["recommendation-issue","荐读文章"]].map(([value,label])=><button type="button" key={value} aria-current={kind===value ? "true" : undefined} onClick={()=>{setKind(value);setOffset(0);setSelected("");}}>{label}</button>)}</nav>
    <form className="admin-action-row" onSubmit={(event) => { event.preventDefault(); setOffset(0); setQuery(String(new FormData(event.currentTarget).get("q") || "")); }}><input name="q" aria-label="搜索已删除内容" placeholder="按名称查找" /><button type="submit">查找</button><button type="button" onClick={resource.retry}>刷新</button></form>
    {notice ? <p role={notice.error ? "alert" : "status"}>{notice.message} {notice.href ? <Link href={notice.href}>前往管理列表</Link> : null}</p> : null}
    {resource.error ? <p role="alert">{resource.error}</p> : resource.loading ? <p role="status">正在读取…</p> : resource.data ? <>
      <p>共 {resource.data.count} 项</p>
      <table><thead><tr><th aria-label="选择"/><th>标题</th><th>类型</th><th>删除时间</th><th>删除原因</th><th>操作</th></tr></thead><tbody>{resource.data.results.map(entry=><tr key={entry.id} data-selected={selected===entry.id}><td><input type="radio" name="recycle-selection" aria-label={`选择${entry.name}`} checked={selected===entry.id} onChange={()=>setSelected(entry.id)}/></td><td><button className="reference-select-title" type="button" onClick={()=>setSelected(entry.id)}>{entry.name}</button></td><td>{labels[entry.kind] || "管理内容"}</td><td>{new Date(entry.deleted_at).toLocaleString("zh-CN")}</td><td>—</td><td><button type="button" className="button secondary" disabled={Boolean(busy)} onClick={()=>void restore(entry)}>{busy===entry.id ? "正在恢复…" : "恢复"}</button></td></tr>)}</tbody></table>
      {!resource.data.results.length ? <p>没有符合条件的已删除内容。</p> : null}
      <div className="admin-action-row"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>上一页</button><button disabled={offset + 50 >= resource.data.count} onClick={() => setOffset(offset + 50)}>下一页</button></div>
    </> : null}
  </section><AdminPublicPreviewFrame title="选中内容的读者预览" description="恢复后仍未公开，需要返回编辑区检查并发布。" src={null} emptyMessage="—"/></div></div>;
}
