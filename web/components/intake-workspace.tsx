"use client";

import Link from "next/link";
import { LoaderCircle, RefreshCw } from "lucide-react";
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

export function IntakeWorkspace({ itemId }: { itemId: string }) {
  const [payload, setPayload] = useState<IntakePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const load = useCallback(async () => {
    setLoading(true);
    try { setPayload(await apiRequest<IntakePayload>(`/catalog/admin/intake/${itemId}/`, {}, getServerSessionCredential())); setMessage(""); }
    catch (error) { setMessage(error instanceof Error ? error.message : "上架工作区读取失败。"); }
    finally { setLoading(false); }
  }, [itemId]);
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);
  return (
    <div className="admin-page">
      <header className="admin-page-title"><div><p>Library · Intake</p><h1>Intake / Publication Workspace</h1><span>Collection、Knowledge、Projection 分开显示。联网、AI 和索引失败不会伪装成馆藏不能阅读。</span></div><div className="admin-title-actions"><button className="button secondary" type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={15} />刷新</button>{payload ? <Link className="button" href={`/admin/review/${payload.item.id}`}>打开元数据复核</Link> : null}</div></header>
      {message ? <p className="form-message" role="alert">{message}</p> : null}
      {loading && !payload ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在读取上架状态……</p> : null}
      {payload ? <div className="intake-workspace-grid"><section className="admin-panel"><header><h2>Collection Lane</h2></header><dl><div><dt>文件</dt><dd>{payload.item.filename}</dd></div><div><dt>状态</dt><dd>{payload.item.status} · {payload.item.workflow_state}</dd></div><div><dt>Asset</dt><dd>{payload.asset?.status ?? "尚未建立"}</dd></div><div><dt>Validation</dt><dd>{payload.asset?.validation ?? "待验证"}</dd></div><div><dt>页数</dt><dd>{payload.asset?.page_count ?? 0}</dd></div></dl>{payload.item.error_message ? <p className="health-error">{payload.item.error_code}: {payload.item.error_message}</p> : null}</section><section className="admin-panel"><header><h2>Catalog Metadata</h2></header>{payload.catalog ? <dl>{Object.entries(payload.catalog).filter(([key]) => ["title", "subtitle", "original_title", "document_type", "language", "publication_state", "publication_year", "publisher", "isbn", "metadata_confidence"].includes(key)).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value ?? "未填写")}</dd></div>)}</dl> : <p>元数据尚未建立。</p>}<p>候选 {payload.metadata_candidates.length} 条</p></section><section className="admin-panel"><header><h2>Knowledge Discovery</h2></header><p>未知观察 {payload.knowledge_discovery.unknown_observations} 条</p><div>{payload.knowledge_discovery.new_authority.map((row) => <article className="candidate-review-card" key={String(row.id)}><strong>{String(row.primary_term ?? "")}</strong><span>{String(row.entity_type ?? "")} · {String(row.status ?? "")}</span></article>)}</div><p>实体解析候选 {payload.entity_candidates.length} 条</p><Link href="/admin/knowledge">进入 Knowledge Workspace</Link></section></div> : null}
    </div>
  );
}
