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
      setMessage(action === "dry_run" ? "Dry run 已完成，未修改词典。" : "重建任务已进入 Processing Jobs。")
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
        <div><p>Search &amp; Intelligence</p><h1>QueryLexicon</h1><span>派生词典只读检查。权威修改必须从 Authority 或候选审核入口完成。</span></div>
        <div className="admin-title-actions"><button className="button secondary" type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={15} />刷新</button>{payload?.permissions?.can_manage ? <><button className="button" type="button" onClick={() => void run("dry_run")} disabled={Boolean(busy)}><WandSparkles size={15} />Dry Run</button><button className="button" type="button" onClick={() => void run("reconcile")} disabled={Boolean(busy)}><WandSparkles size={15} />Reconcile</button></> : null}</div>
      </header>
      <div className="admin-toolbar"><label><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="检索 term、规范化 term……" aria-label="检索 QueryLexicon term" /></label></div>
      {message ? <p className="form-message" role="status">{message}</p> : null}
      {payload && !payload.permissions?.can_manage ? <p className="form-message" role="status">当前账户为只读权限。Reconcile 由超级管理员执行。</p> : null}
      {loading && !payload ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在读取词典状态……</p> : null}
      {payload ? <>
        <section className="admin-panel"><header><h2>当前投影</h2></header><dl className="admin-stats-grid"><div><dt>Revision</dt><dd>{payload.revision ?? "未初始化"}</dd></div><div><dt>Generation</dt><dd>{payload.generation?.id ?? "—"}</dd></div><div><dt>Entries</dt><dd>{payload.entries ?? 0}</dd></div><div><dt>Public active</dt><dd>{payload.public_active_entries ?? 0}</dd></div><div><dt>Admin resolvable</dt><dd>{payload.admin_resolvable_entries ?? 0}</dd></div><div><dt>Pending events</dt><dd>{payload.pending_events ?? 0}</dd></div><div><dt>Failed sync</dt><dd>{payload.failed_events ?? 0}</dd></div></dl></section>
        <section className="admin-panel"><header><h2>Entity coverage</h2></header><div className="admin-table-wrap"><table><thead><tr><th>Entity</th><th>Entries</th><th>Public</th><th>Admin</th></tr></thead><tbody>{(payload.entities ?? []).map((row) => <tr key={row.entity_type}><td>{row.entity_type}</td><td>{row.entries}</td><td>{row.public_active_entries}</td><td>{row.admin_resolvable_entries}</td></tr>)}</tbody></table></div></section>
        <section className="admin-panel"><header><h2>Term inspector</h2><span>只读</span></header><div className="admin-table-wrap"><table><thead><tr><th>Term</th><th>Entity</th><th>Language/type</th><th>Trust</th><th>Scope</th><th>Source</th></tr></thead><tbody>{(payload.terms ?? []).map((row) => <tr key={row.id}><td><strong>{row.term}</strong><small>{row.normalized_term}</small></td><td>{row.entity_label}<small>{row.entity_type}</small></td><td>{row.language} · {row.term_type}</td><td>{row.trust_level}</td><td>{row.public_active ? "public" : ""}{row.admin_resolvable ? " admin" : ""}</td><td>{row.source_kind}</td></tr>)}</tbody></table></div></section>
      </> : null}
      {dryRun ? <section className="admin-panel"><header><h2>最近 Dry Run</h2></header><pre>{JSON.stringify(dryRun, null, 2)}</pre></section> : null}
    </div>
  );
}
