"use client";

import Link from "next/link";
import { ArrowRight, LoaderCircle, RefreshCw, RotateCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

type IntakePayload = {
  item: { id: string; filename: string; status: string; workflow_state: string; error_code: string; error_message: string };
  asset?: { id: string; status: string; validation: string; page_count: number; mime_type: string; sha256: string } | null;
  catalog?: Record<string, unknown> | null;
  metadata_candidates: Array<Record<string, unknown>>;
  entity_candidates: Array<Record<string, unknown>>;
  knowledge_discovery: { new_authority: Array<Record<string, unknown>>; unknown_observations: number };
};

const statusLabels: Record<string, string> = {
  waiting: "等待上传",
  uploaded: "已上传",
  processing: "处理中",
  ready: "待复核",
  published: "已发布",
  failed: "处理失败",
  paused: "已暂停",
  pending: "待处理",
  succeeded: "已完成",
};

const fieldLabels: Record<string, string> = {
  title: "题名",
  subtitle: "副题名",
  original_title: "原题名",
  document_type: "文献类型",
  language: "语言",
  publication_state: "出版状态",
  publication_year: "出版年份",
  publisher: "出版社",
  isbn: "ISBN",
  metadata_confidence: "元数据置信度",
};

function displayStatus(value: unknown) {
  const text = String(value ?? "");
  return statusLabels[text] ?? (text || "尚未建立");
}

export function IntakeWorkspace({ itemId }: { itemId: string }) {
  const [payload, setPayload] = useState<IntakePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const load = useCallback(async () => {
    setLoading(true);
    try { setPayload(await apiRequest<IntakePayload>(`/catalog/admin/intake/${itemId}/`, {}, getServerSessionCredential())); setMessage(""); }
    catch (error) { setMessage(error instanceof Error ? error.message : "上架工作区读取失败。"); }
    finally { setLoading(false); }
  }, [itemId]);

  async function action(path: string, label: string) {
    setBusy(path);
    try {
      await apiRequest(path, { method: "POST", body: JSON.stringify({}) }, getServerSessionCredential());
      setMessage(label);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `${label}失败。`);
    } finally {
      setBusy("");
    }
  }
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);
  const assetId = payload?.asset?.id ?? "";
  return (
    <div className="admin-page">
      <header className="admin-page-title"><div><p>入库 · 上架</p><h1>上架工作台</h1><span>文件处理、书目元数据和知识发现分开显示。联网、AI 或索引失败不会伪装成馆藏无法阅读。</span></div><div className="admin-title-actions"><button className="button secondary" type="button" onClick={() => void load()} disabled={loading || Boolean(busy)}><RefreshCw size={15} />刷新</button>{payload ? <Link className="button" href={`/admin/review/${payload.item.id}`}>打开元数据复核 <ArrowRight size={14} /></Link> : null}{payload?.item.status === "failed" ? <button className="button secondary" type="button" disabled={Boolean(busy)} onClick={() => void action(`/ingestion/items/${payload.item.id}/retry/`, "文件已重新进入处理队列。")}><RotateCw size={14} />重新处理</button> : null}{assetId ? <button className="button secondary" type="button" disabled={Boolean(busy)} onClick={() => void action(`/catalog/admin/projection-status/asset/${assetId}/refresh/`, "关联数据刷新任务已排队。")}><RotateCw size={14} />刷新关联数据</button> : null}</div></header>
      {message ? <p className="form-message" role="alert">{message}</p> : null}
      {loading && !payload ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在读取上架状态……</p> : null}
      {payload ? <div className="intake-workspace-grid"><section className="admin-panel"><header><h2>文件处理</h2></header><dl><div><dt>文件</dt><dd>{payload.item.filename}</dd></div><div><dt>状态</dt><dd>{displayStatus(payload.item.status)} · {displayStatus(payload.item.workflow_state)}</dd></div><div><dt>馆藏文件</dt><dd>{displayStatus(payload.asset?.status)}</dd></div><div><dt>文件校验</dt><dd>{displayStatus(payload.asset?.validation)}</dd></div><div><dt>页数</dt><dd>{payload.asset?.page_count ?? 0}</dd></div></dl>{payload.item.error_message ? <p className="health-error">{payload.item.error_code}: {payload.item.error_message}</p> : null}</section><section className="admin-panel"><header><h2>书目元数据</h2></header>{payload.catalog ? <dl>{Object.entries(payload.catalog).filter(([key]) => Object.hasOwn(fieldLabels, key)).map(([key, value]) => <div key={key}><dt>{fieldLabels[key] ?? key}</dt><dd>{String(value ?? "未填写")}</dd></div>)}</dl> : <p>元数据尚未建立。</p>}<p>待复核候选 {payload.metadata_candidates.length} 条</p></section><section className="admin-panel"><header><h2>知识发现</h2></header><p>未知实体观察 {payload.knowledge_discovery.unknown_observations} 条</p><div>{payload.knowledge_discovery.new_authority.map((row) => <article className="candidate-review-card" key={String(row.id)}><strong>{String(row.primary_term ?? "")}</strong><span>{String(row.entity_type ?? "")} · {displayStatus(row.status)}</span></article>)}</div><p>实体解析候选 {payload.entity_candidates.length} 条</p><Link href="/admin/knowledge">进入知识工作台</Link></section></div> : null}
    </div>
  );
}
