"use client";

import { CircleAlert, LoaderCircle, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

type StatusValue = Record<string, unknown>;
type StatusPayload = {
  database: StatusValue;
  redis: StatusValue;
  celery: StatusValue;
  storage: StatusValue;
  query_lexicon: StatusValue;
  semantic: StatusValue;
  embedding: StatusValue;
  ai: StatusValue;
  web_enrichment: StatusValue;
  backup: StatusValue;
};

function statusLabel(value: unknown) {
  if (value === true) return "可用";
  if (value === false) return "不可用";
  const text = String(value ?? "unknown");
  return ({ healthy: "健康", current: "当前", configured: "已配置", not_configured: "未配置", disabled: "已停用", available: "可用", insufficient_corpus: "证据不足", unavailable: "不可用", not_available: "暂无", missing: "缺失", local_cache: "本地缓存", unknown: "尚未探测" } as Record<string, string>)[text] ?? text;
}

export function SystemStatusCenter() {
  const [payload, setPayload] = useState<StatusPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setPayload(await apiRequest<StatusPayload>("/catalog/admin/system-status/", {}, getServerSessionCredential()));
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "系统状态读取失败。");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const cards = payload ? [
    ["DATABASE", payload.database],
    ["REDIS", payload.redis],
    ["CELERY", payload.celery],
    ["STORAGE", payload.storage],
    ["QUERY LEXICON", payload.query_lexicon],
    ["SEMANTIC", payload.semantic],
    ["EMBEDDING", payload.embedding],
    ["AI", payload.ai],
    ["WEB ENRICHMENT", payload.web_enrichment],
    ["BACKUP", payload.backup],
  ] as Array<[string, Record<string, unknown>]> : [];

  return (
    <div className="admin-page">
      <header className="admin-page-title"><div><p>Operations</p><h1>System Status Center</h1><span>显示可解释的运行状态，不展示密码、Token 或其他 secret。</span></div><div className="admin-title-actions"><button className="button secondary" type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={15} />刷新</button></div></header>
      {message ? <p className="form-message" role="alert"><CircleAlert size={15} />{message}</p> : null}
      {loading && !payload ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在读取系统状态……</p> : null}
      <section className="health-component-grid">{cards.map(([title, value]) => <article className="admin-panel health-component" key={title}><header><h2>{title}</h2><strong>{statusLabel(value.status ?? value.configured)}</strong></header><dl>{Object.entries(value).filter(([key]) => !["profiles", "structured", "last_success"].includes(key)).slice(0, 12).map(([key, item]) => <div key={key}><dt>{key}</dt><dd>{typeof item === "object" ? JSON.stringify(item) : statusLabel(item)}</dd></div>)}</dl>{value.profiles ? <details><summary>Profiles</summary><pre>{JSON.stringify(value.profiles, null, 2)}</pre></details> : null}{value.structured ? <details><summary>Structured providers</summary><pre>{JSON.stringify(value.structured, null, 2)}</pre></details> : null}</article>)}</section>
    </div>
  );
}
