"use client";

import { LoaderCircle, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

type KnowledgePayload = {
  new_authority: Array<{ id: string; entity_type: string; term: string; status: string; confidence: number; evidence_count: number; works: Array<{ work_id: string; work__title: string }> }>;
  aliases: Array<{ id: string; alias: string; language: string; alias_type: string; source_kind: string; is_verified: boolean; node__canonical_name_zh: string }>;
  relations: { pending: number };
  timelines: { pending: number };
  classification: { pending_enrichment: number };
  unknown_observations: number;
};

export function KnowledgeWorkspace() {
  const [payload, setPayload] = useState<KnowledgePayload | null>(null);
  const [status, setStatus] = useState("pending");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const query = new URLSearchParams({ status });
      setPayload(await apiRequest<KnowledgePayload>(`/catalog/admin/knowledge-workspace/?${query.toString()}`, {}, getServerSessionCredential()));
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "知识工作区读取失败。");
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  return (
    <div className="admin-page">
      <header className="admin-page-title"><div><p>Knowledge</p><h1>Knowledge Workspace</h1><span>把馆藏观察、已有 authority、草稿实体和证据放在同一审核入口。创建草稿不会发布。</span></div><div className="admin-title-actions"><button className="button secondary" type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={15} />刷新</button></div></header>
      <div className="admin-toolbar"><label><span>候选状态</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="pending">待审核</option><option value="all">全部</option><option value="matched">已关联</option><option value="draft_created">已创建草稿</option><option value="rejected">已拒绝</option></select></label></div>
      {message ? <p className="form-message" role="status">{message}</p> : null}
      {loading && !payload ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在读取知识工作区……</p> : null}
      {payload ? <>
        <section className="admin-panel"><header><h2>待处理概览</h2></header><dl className="admin-stats-grid"><div><dt>未知实体观察</dt><dd>{payload.unknown_observations}</dd></div><div><dt>待审核关系</dt><dd>{payload.relations.pending}</dd></div><div><dt>待审核时间线</dt><dd>{payload.timelines.pending}</dd></div><div><dt>待审核分类</dt><dd>{payload.classification.pending_enrichment}</dd></div></dl></section>
        <section className="admin-panel"><header><h2>New Authority Candidates</h2><span>显式选择 Match Existing 或 Create Draft</span></header><div className="admin-table-wrap"><table><thead><tr><th>Term</th><th>Entity</th><th>Confidence</th><th>Evidence</th><th>Works</th><th>Status</th></tr></thead><tbody>{payload.new_authority.map((row) => <tr key={row.id}><td><strong>{row.term}</strong><small>{row.works.map((work) => work.work__title).join("、") || "馆藏作品待补"}</small></td><td>{row.entity_type}</td><td>{Math.round(row.confidence * 100)}%</td><td>{row.evidence_count}</td><td>{row.works.length}</td><td>{row.status}</td></tr>)}{!payload.new_authority.length ? <tr><td colSpan={6}>当前没有未知实体候选。0 也是有效状态。</td></tr> : null}</tbody></table></div></section>
        <section className="admin-panel"><header><h2>Aliases</h2><span>authority source-of-truth</span></header><div className="admin-table-wrap"><table><thead><tr><th>Alias</th><th>Node</th><th>Language/type</th><th>Source</th><th>Verified</th></tr></thead><tbody>{payload.aliases.map((row) => <tr key={String(row.id)}><td>{row.alias}</td><td>{row.node__canonical_name_zh}</td><td>{row.language} · {row.alias_type}</td><td>{row.source_kind}</td><td>{row.is_verified ? "是" : "否"}</td></tr>)}</tbody></table></div></section>
      </> : null}
    </div>
  );
}
