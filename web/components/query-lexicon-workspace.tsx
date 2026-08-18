"use client";

import { LoaderCircle, RefreshCw, Search, WandSparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

type LexiconPayload = {
  permissions?: { can_manage: boolean };
  initialized?: boolean;
  revision?: number | null;
  generation?: { id: string; status: string; entry_count?: number; content_hash?: string } | null;
  entries?: number;
  public_active_entries?: number;
  admin_resolvable_entries?: number;
  pending_events?: number;
  failed_events?: number;
  entities?: Array<{ entity_type: string; entries: number; public_active_entries: number; admin_resolvable_entries: number }>;
  terms?: Array<{ id: string; term: string; normalized_term: string; entity_type: string; entity_label: string; language: string; term_type: string; trust_level: string; source_kind: string; public_active: boolean; admin_resolvable: boolean; provenance?: unknown }>;
};

const trustLabels: Record<string, string> = {
  authoritative: "权威",
  verified: "已验证",
  high: "高信任",
  medium: "中信任",
  low: "低信任",
};
const sourceLabels: Record<string, string> = {
  authority: "权威对象",
  canonical: "规范名称",
  verified_alias: "已验证别名",
  generated: "系统派生",
  legacy: "历史映射",
};

function dryRunText(value: unknown, depth = 0): string {
  if (depth > 3) return "…";
  if (Array.isArray(value)) return value.slice(0, 20).map((item) => dryRunText(item, depth + 1)).join("、");
  if (value && typeof value === "object") {
    const labels: Record<string, string> = { source_entity_count: "来源实体数", expected_entry_count: "预计词条数", anomaly: "异常", revision: "版本", generation: "生成批次", content_hash: "内容校验" };
    return Object.entries(value as Record<string, unknown>).slice(0, 40).map(([key, item]) => `${labels[key] ?? key}：${dryRunText(item, depth + 1)}`).join("\n");
  }
  return String(value ?? "—");
}

export function QueryLexiconWorkspace() {
  const [query, setQuery] = useState("");
  const [payload, setPayload] = useState<LexiconPayload | null>(null);
  const [dryRun, setDryRun] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const search = new URLSearchParams();
      if (query.trim()) search.set("q", query.trim());
      const next = await apiRequest<LexiconPayload>(`/catalog/admin/query-lexicon/?${search.toString()}`, {}, getServerSessionCredential());
      setPayload(next);
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "QueryLexicon 状态读取失败。");
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function run(action: "dry_run" | "reconcile") {
    setBusy(action);
    try {
      const result = await apiRequest<Record<string, unknown>>(
        "/catalog/admin/query-lexicon/",
        { method: "POST", body: JSON.stringify({ action }) },
        getServerSessionCredential(),
      );
      if (action === "dry_run") setDryRun(result);
      setMessage(action === "dry_run" ? "预演已完成，词典没有被修改。" : "重建任务已进入处理任务。")
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "QueryLexicon 操作失败。");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="admin-page">
      <header className="admin-page-title">
        <div><p>搜索与智能</p><h1>QueryLexicon 派生词典</h1><span>这里查看由学者、理论节点、学科和主题等权威对象派生的检索词典。它不会自行创造权威对象，词条不能直接编辑；权威修改会通过变更事件同步。</span></div>
        <div className="admin-title-actions"><button className="button secondary" type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={15} />刷新</button>{payload?.permissions?.can_manage ? <><button className="button" type="button" onClick={() => void run("dry_run")} disabled={Boolean(busy)}><WandSparkles size={15} />预演</button><button className="button" type="button" onClick={() => void run("reconcile")} disabled={Boolean(busy)}><WandSparkles size={15} />正式同步</button></> : null}</div>
      </header>
      <div className="admin-toolbar"><label><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="检索 term、规范化 term……" aria-label="检索 QueryLexicon term" /></label></div>
      {message ? <p className="form-message" role="status">{message}</p> : null}
      {payload && !payload.permissions?.can_manage ? <p className="form-message" role="status">当前账户为只读权限。正式同步由超级管理员执行。</p> : null}
      {loading && !payload ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在读取词典状态……</p> : null}
      {payload ? <>
        <section className="admin-panel"><header><h2>当前派生状态</h2></header><dl className="admin-stats-grid"><div><dt>内容版本</dt><dd>{payload.revision ?? "未初始化"}</dd></div><div><dt>活动生成批次</dt><dd translate="no">{payload.generation?.id ?? "—"}</dd></div><div><dt>活动词条</dt><dd>{payload.entries ?? 0}</dd></div><div><dt>公开可用词条</dt><dd>{payload.public_active_entries ?? 0}</dd></div><div><dt>后台可解析词条</dt><dd>{payload.admin_resolvable_entries ?? 0}</dd></div><div><dt>待处理变更</dt><dd>{payload.pending_events ?? 0}</dd></div><div><dt>失败同步</dt><dd>{payload.failed_events ?? 0}</dd></div></dl><p className="admin-help">公开搜索只读公开可用词条；后台候选解析可以读取后台可解析词条。草稿权威对象不会因此暴露到公网。</p></section>
        <section className="admin-panel"><header><h2>实体覆盖</h2></header><div className="admin-table-wrap"><table><thead><tr><th>实体类型</th><th>词条</th><th>公开</th><th>后台</th></tr></thead><tbody>{(payload.entities ?? []).map((row) => <tr key={row.entity_type}><td>{({ person: "学者", knowledge_node: "理论节点", discipline: "学科", subdiscipline: "子学科", topic: "主题", theory_school: "理论流派", concept: "概念" } as Record<string, string>)[row.entity_type] ?? row.entity_type}</td><td>{row.entries}</td><td>{row.public_active_entries}</td><td>{row.admin_resolvable_entries}</td></tr>)}</tbody></table></div></section>
        <section className="admin-panel"><header><h2>词条检查器</h2><span>只读派生数据</span></header><div className="admin-table-wrap"><table><thead><tr><th>词条</th><th>实体</th><th>语言 / 类型</th><th>信任等级</th><th>可见范围</th><th>来源</th></tr></thead><tbody>{(payload.terms ?? []).map((row) => <tr key={row.id}><td><strong>{row.term}</strong><small translate="no">{row.normalized_term}</small></td><td>{row.entity_label}<small>{({ person: "学者", knowledge_node: "理论节点", discipline: "学科", subdiscipline: "子学科", topic: "主题", theory_school: "理论流派", concept: "概念" } as Record<string, string>)[row.entity_type] ?? row.entity_type}</small></td><td>{row.language} · {({ canonical: "规范名称", alias: "别名", translation: "译名", search_variant: "检索变体", historical: "历史名称", transliteration: "音译" } as Record<string, string>)[row.term_type] ?? row.term_type}</td><td>{trustLabels[row.trust_level] ?? row.trust_level}</td><td>{row.public_active ? "公开" : ""}{row.admin_resolvable ? " 后台" : ""}</td><td>{sourceLabels[row.source_kind] ?? row.source_kind}</td></tr>)}</tbody></table></div></section>
      </> : null}
      {dryRun ? <section className="admin-panel"><header><h2>最近一次预演</h2><span>只读结果</span></header><pre className="admin-readable-json">{dryRunText(dryRun)}</pre></section> : null}
    </div>
  );
}
