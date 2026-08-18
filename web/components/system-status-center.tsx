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
  return ({ healthy: "健康", current: "当前", configured: "已配置", not_configured: "未配置", disabled: "未配置", not_tested: "尚未测试", available: "可用", insufficient_corpus: "证据不足", unavailable: "不可用", down: "服务不可用", not_available: "暂无", missing: "缺失", local_cache: "本地缓存", unknown: "尚未探测", true: "是", false: "否" } as Record<string, string>)[text] ?? text;
}

const keyLabels: Record<string, string> = {
  status: "状态", version: "版本", migration_heads: "迁移 head", vendor: "数据库引擎",
  configured: "已配置", reachable: "连接状态", broker: "Celery 消息代理",
  default_worker: "默认 Worker", ingestion_worker: "入库 Worker", beat: "Beat 调度器",
  control: "Worker 控制通道", heartbeat_at: "最近心跳", active_version: "活动版本",
  uid: "活动 UID", db_ready_chunks: "数据库 ready 分块", meilisearch_document_count: "Meilisearch 文档",
  expected_document_count: "预期文档", model: "模型", model_revision: "模型 revision",
  local_path: "本地路径", offline_mode: "离线模式", revision: "词典 revision",
  generation: "活动 generation", entries: "活动词条", public_active_entries: "公开词条",
  admin_resolvable_entries: "后台词条", pending_events: "待处理事件", failed_events: "失败事件",
  provider: "服务商", capability: "能力", profile: "配置档", health: "健康检查",
  last_success: "最近成功", last_successful_check: "最近成功检查", error_category: "错误类别",
  credential_configured: "凭据已配置", endpoint_configured: "服务地址已配置", restart_may_be_required: "可能需要重启",
  document_count: "文档数量", schema: "索引结构", model_health: "模型健康状态", reason: "原因",
  id: "编号", completed_at: "完成时间", checksum: "校验值", size: "大小", source: "来源",
};

function keyLabel(key: string) {
  return keyLabels[key] ?? key.replaceAll("_", " ");
}

function scalarLabel(value: unknown, key = "") {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (key.endsWith("_at") && typeof value === "string") {
    const date = new Date(value);
    if (!Number.isNaN(date.valueOf())) return date.toLocaleString("zh-CN");
  }
  return statusLabel(value);
}

function StatusDetails({ value }: { value: unknown }) {
  if (!value || typeof value !== "object") return <span>{scalarLabel(value)}</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span>无</span>;
    return <details className="system-status-details"><summary>{value.length} 项</summary><ul>{value.slice(0, 30).map((item, index) => <li key={index}>{item && typeof item === "object" ? <StatusDetails value={item} /> : scalarLabel(item)}</li>)}</ul></details>;
  }
  return <details className="system-status-details"><summary>查看详情</summary><dl>{Object.entries(value as Record<string, unknown>).slice(0, 30).map(([key, item]) => <div key={key}><dt>{keyLabel(key)}</dt><dd>{item && typeof item === "object" ? <StatusDetails value={item} /> : scalarLabel(item, key)}</dd></div>)}</dl></details>;
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
    ["数据库", payload.database],
    ["Redis", payload.redis],
    ["Celery 任务", payload.celery],
    ["NAS 存储", payload.storage],
    ["QueryLexicon 词典", payload.query_lexicon],
    ["语义索引", payload.semantic],
    ["Embedding 模型", payload.embedding],
    ["AI 服务", payload.ai],
    ["联网补全来源", payload.web_enrichment],
    ["备份", payload.backup],
  ] as Array<[string, Record<string, unknown>]> : [];

  return (
    <div className="admin-page">
      <header className="admin-page-title"><div><p>运营</p><h1>系统状态中心</h1><span>把“为什么不可用”显示出来，不展示密码、Token 或其他 secret。</span></div><div className="admin-title-actions"><button className="button secondary" type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={15} />刷新</button></div></header>
      {message ? <p className="form-message" role="alert"><CircleAlert size={15} />{message}</p> : null}
      {loading && !payload ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在读取系统状态……</p> : null}
      <section className="health-component-grid">{cards.map(([title, value]) => <article className="admin-panel health-component" key={title}><header><h2>{title}</h2><strong>{scalarLabel(value.status ?? value.configured)}</strong></header><dl>{Object.entries(value).filter(([key]) => !["profiles", "structured"].includes(key)).slice(0, 12).map(([key, item]) => <div key={key}><dt>{keyLabel(key)}</dt><dd>{item && typeof item === "object" ? <StatusDetails value={item} /> : scalarLabel(item, key)}</dd></div>)}</dl>{value.profiles ? <details><summary>模型配置档</summary><StatusDetails value={value.profiles} /></details> : null}{value.structured ? <details><summary>结构化来源</summary><StatusDetails value={value.structured} /></details> : null}</article>)}</section>
    </div>
  );
}
