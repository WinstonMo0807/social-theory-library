"use client";

import { CircleAlert, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { LoadingState } from "@/components/ui/loading-state";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

type StatusValue = Record<string, unknown>;
export type StatusPayload = {
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
  return ({ healthy: "正常", current: "当前", configured: "已配置", not_configured: "未配置", disabled: "未启用", not_tested: "尚未测试", available: "可用", partial: "部分就绪", prepared: "已准备", not_ready: "待建立", insufficient_corpus: "证据不足", unavailable: "不可用", down: "服务不可用", not_available: "暂无", missing: "缺失", local_cache: "本地缓存", unknown: "尚未确认", true: "是", false: "否" } as Record<string, string>)[text] ?? text;
}

const keyLabels: Record<string, string> = {
  status: "状态", version: "版本", migration_heads: "数据库结构版本", vendor: "数据库引擎",
  configured: "已配置", reachable: "连接状态", broker: "任务消息服务",
  default_worker: "常规任务进程", ingestion_worker: "入库任务进程", beat: "定时任务",
  control: "任务控制连接", heartbeat_at: "最近心跳", active_version: "活动版本",
  uid: "活动 UID", db_ready_chunks: "已就绪原文片段", meilisearch_document_count: "Meilisearch 文档",
  expected_document_count: "预期文档", model: "模型", model_revision: "模型版本",
  local_path: "本地路径", offline_mode: "离线模式", revision: "版本标识",
  generation: "当前索引批次", entries: "当前词条", public_active_entries: "公开词条",
  admin_resolvable_entries: "后台词条", pending_events: "待处理事件", failed_events: "失败事件",
  provider: "服务商", capability: "能力", profile: "服务配置", health: "正常检查",
  last_success: "最近成功", last_successful_check: "最近成功检查", error_category: "错误类别",
  credential_configured: "凭据已配置", endpoint_configured: "服务地址已配置", restart_may_be_required: "可能需要重启",
  document_count: "文档数量", schema: "索引结构", model_health: "模型正常状态", reason: "原因",
  id: "编号", completed_at: "完成时间", checksum: "校验值", size: "大小", source: "来源",
  checked_at: "检查时间", on_demand: "按需启动", available: "可用性", local_required: "需要本地模型",
  active_generation: "活动索引批次", index_uid: "活动索引", dimensions: "向量维度",
  coverage: "当前公开修订覆盖", eligible_editions: "可检索版本", published_editions: "已发布版本",
  indexed_editions: "关键词已完成版本", vector_editions: "语义已完成版本", projected_editions: "原文已完成版本",
  pending_editions: "待完成版本", index_pending_editions: "待建立索引版本", vector_pending_editions: "待建立向量版本",
  passage_count: "已完成原文片段", text_pending_editions: "正文待完成版本", bibliographic_editions: "仅书目版本",
  partial: "覆盖尚未完整", manifest_ready: "模型文件已准备", models: "模型状态", embedding: "编码模型",
  reranker: "重排模型", loaded: "当前已加载", inference_completed: "本次启动后已执行",
  artifact_id: "模型制品标识", embedding_artifact: "编码模型制品", reranker_artifact: "重排模型制品",
  backend: "推理引擎", threads: "计算线程", batch_size: "单次批量", pipeline: "处理版本", error_code: "错误代码",
};

function serviceState(value: StatusValue) {
  return value.status ?? (value.configured === true ? "configured" : value.configured === false ? "not_configured" : "unknown");
}

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
    return <details data-disclosure="collection" className="system-status-details"><summary>{value.length} 项</summary><ul>{value.slice(0, 30).map((item, index) => <li key={index}>{item && typeof item === "object" ? <StatusDetails value={item} /> : scalarLabel(item)}</li>)}</ul></details>;
  }
  return <details data-disclosure="collection" className="system-status-details"><summary>查看详情</summary><dl>{Object.entries(value as Record<string, unknown>).slice(0, 30).map(([key, item]) => <div key={key}><dt>{keyLabel(key)}</dt><dd>{item && typeof item === "object" ? <StatusDetails value={item} /> : scalarLabel(item, key)}</dd></div>)}</dl></details>;
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

  return <div className="admin-page system-status-page">
    <header className="admin-page-title"><div><h1>运行维护</h1></div><button className="button secondary" type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={16} className={loading ? "spin" : ""} />{loading ? "刷新中" : "刷新状态"}</button></header>
    {message ? <p className="form-message" role="alert"><CircleAlert size={16} />{message}</p> : null}
    {loading && !payload ? <LoadingState>正在读取服务状态…</LoadingState> : null}
    {payload ? <SystemStatusView payload={payload} /> : null}
  </div>;
}

/** Shared by the live maintenance page and the explicitly labelled LAN proposals. */
export function SystemStatusView({ payload }: { payload: StatusPayload }) {
  const [selectedKey, setSelectedKey] = useState("database");
  const cards = [
    ["database", "数据库", payload.database],
    ["redis", "Redis", payload.redis],
    ["celery", "后台任务", payload.celery],
    ["storage", "NAS 存储", payload.storage],
    ["query_lexicon", "检索词典", payload.query_lexicon],
    ["semantic", "语义索引", payload.semantic],
    ["embedding", "语义模型", payload.embedding],
    ["ai", "AI 服务", payload.ai],
    ["web_enrichment", "联网资料来源", payload.web_enrichment],
    ["backup", "备份", payload.backup],
  ] as Array<[string, string, Record<string, unknown>]>;

  const selected = cards.find(([key]) => key === selectedKey) ?? cards[0];

  return <section className="system-status-v2" aria-label="服务运行状况">
    <div className="system-status-v2-list">
      <header><h2>服务</h2><span>{cards.length} 项</span></header>
      <div className="system-status-options" aria-label="选择服务">
        {cards.map(([key, title, value]) => <button type="button" aria-pressed={selected?.[0] === key} aria-controls="service-detail" className={selected?.[0] === key ? "selected" : ""} key={key} onClick={() => setSelectedKey(key)}>
          <span className="system-status-v2-dot" data-status={String(serviceState(value))} aria-hidden="true" /><strong>{title}</strong><span>{scalarLabel(serviceState(value))}</span>
        </button>)}
      </div>
    </div>
    <section id="service-detail" key={selected?.[0]} className="system-status-v2-detail system-status-v2-detail-body" aria-live="polite">
      {selected ? <><header><h2>{selected[1]}</h2><span className="system-status-v2-state" data-status={String(serviceState(selected[2]))}>{scalarLabel(serviceState(selected[2]))}</span></header>
        {selected[2].reason ? <p className="system-status-reason">{String(selected[2].reason)}</p> : null}
        <dl>{Object.entries(selected[2]).filter(([key]) => !["profiles", "structured", "reason"].includes(key)).slice(0, 24).map(([key, item]) => <div key={key}><dt>{keyLabel(key)}</dt><dd>{item && typeof item === "object" ? <StatusDetails value={item} /> : scalarLabel(item, key)}</dd></div>)}</dl>
        {selected[2].profiles ? <details data-disclosure="collection"><summary>模型配置</summary><StatusDetails value={selected[2].profiles} /></details> : null}
        {selected[2].structured ? <section data-content-section><header data-section-heading>资料来源</header><StatusDetails value={selected[2].structured} /></section> : null}
      </> : null}
    </section>
  </section>;
}
