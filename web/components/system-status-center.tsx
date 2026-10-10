"use client";

import { CircleAlert, Database, FileText, Folder, Globe, ListChecks, LoaderCircle, RefreshCw, Search } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import type { FunctionalHealthPayload, RunProbeResponse } from "./functional-health-panel";

type StatusValue = Record<string, unknown>;
type StatusPayload = {
  generated_at?: string;
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
  return ({ healthy: "正常", degraded: "需要处理", failed: "故障", recovering: "恢复中", paused: "已暂停", current: "当前", configured: "已配置", not_configured: "未配置", disabled: "未配置", not_tested: "尚未测试", available: "可用", insufficient_corpus: "证据不足", unavailable: "不可用", down: "服务不可用", not_available: "暂无", missing: "缺失", local_cache: "本地缓存", unknown: "等待检查", true: "是", false: "否" } as Record<string, string>)[text] ?? text;
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

const services = [
  { key: "public_internet", title: "网站服务", scope: "公网入口", Icon: Globe },
  { key: "catalog_core", title: "数据保存", scope: "数据库、缓存与迁移", Icon: Database },
  { key: "background_processing", title: "后台任务", scope: "任务队列与处理记录", Icon: ListChecks },
  { key: "ingestion", title: "文字识别", scope: "入库与 OCR", Icon: FileText },
  { key: "search", title: "搜索功能", scope: "检索服务与检索用语", Icon: Search },
  { key: "public_reading", title: "文件存储", scope: "PDF 存储与在线阅读", Icon: Folder },
] as const;

function checkedTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

export function SystemStatusCenter() {
  const user = useAdminSession();
  const canCheck = hasAdminCapability(user, "can_retry_jobs") && hasAdminCapability(user, "can_view_system_status");
  const [payload, setPayload] = useState<FunctionalHealthPayload | null>(null);
  const [technical, setTechnical] = useState<StatusPayload | null>(null);
  const [technicalOpen, setTechnicalOpen] = useState(false);
  const [technicalError, setTechnicalError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [selectedKey, setSelectedKey] = useState<string>("search");
  const pending = useRef(false);
  const request = useRef<AbortController | null>(null);
  const technicalRequest = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    if (pending.current) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    try {
      const result = await apiRequest<FunctionalHealthPayload>("/catalog/admin/functional-health/", { signal: controller.signal }, getServerSessionCredential());
      if (!controller.signal.aborted) { setPayload(result); setMessage(""); }
    } catch (error) {
      if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : "检查记录读取失败。");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    const refresh = window.setInterval(() => void load(), 30000);
    return () => { window.clearTimeout(timer); window.clearInterval(refresh); request.current?.abort(); technicalRequest.current?.abort(); };
  }, [load]);

  async function check(probeKeys: string[]) {
    if (!canCheck || pending.current || !probeKeys.length) return;
    pending.current = true; request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setLoading(false); setMessage("");
    try {
      for (const probeKey of new Set(probeKeys)) {
        const result = await apiRequest<RunProbeResponse>("/catalog/admin/functional-health/", {
          method: "POST", body: JSON.stringify({ action: "run_probe", probe_key: probeKey }), signal: controller.signal,
        }, getServerSessionCredential());
        if (controller.signal.aborted) return;
        setPayload(result.snapshot);
      }
      setMessage("本次检查已完成，结果以各项服务的实际记录为准。");
    } catch (error) {
      if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : "服务检查失败。");
    } finally {
      pending.current = false;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  async function loadTechnical() {
    if (technicalRequest.current) return;
    const controller = new AbortController();
    technicalRequest.current = controller;
    setTechnicalError("");
    try {
      const result = await apiRequest<StatusPayload>("/catalog/admin/system-status/", { signal: controller.signal }, getServerSessionCredential());
      if (!controller.signal.aborted) setTechnical(result);
    } catch (error) {
      if (!controller.signal.aborted) setTechnicalError(error instanceof Error ? error.message : "技术状态读取失败。");
    } finally {
      if (technicalRequest.current === controller) technicalRequest.current = null;
    }
  }

  const cards = services.map(service => ({ ...service, value: payload?.capabilities.find(row => row.key === service.key) }));
  const selected = cards.find(row => row.key === selectedKey) ?? cards[4];
  const dependencies = selected.value?.dependencies ?? [];
  const incidents = payload?.incidents.filter(row => row.capability === selected.key && row.status !== "resolved") ?? [];
  const observations = [...new Map(cards.flatMap(row => row.value?.dependencies ?? []).filter(row => row.observation_id && row.last_checked_at).map(row => [row.probe_key, row])).values()].sort((a, b) => String(b.last_checked_at).localeCompare(String(a.last_checked_at)));
  const probeKeys = cards.flatMap(row => row.value?.dependencies.map(probe => probe.probe_key) ?? []);
  const recentRows = (rows: typeof observations) => <div className="admin-table-wrap"><table><thead><tr><th>检查时间</th><th>服务状态</th><th>主要说明</th></tr></thead><tbody>{rows.map(row => <tr key={row.probe_key}><td><time>{checkedTime(row.last_checked_at)}</time></td><td>{statusLabel(row.status)}</td><td><strong>{row.label}</strong><p>{row.summary}</p></td></tr>)}</tbody></table></div>;

  return <div className="admin-page system-status-reference">
    <header className="admin-page-title"><div><h1>运行检查</h1><span>检查网站各项服务的运行状态，及时发现并处理可能的问题。</span></div><div className="admin-title-actions"><span>最近检查：{checkedTime(observations[0]?.last_checked_at)}</span><button className="button" type="button" onClick={() => void check(probeKeys)} disabled={loading || busy || !canCheck || !probeKeys.length}><RefreshCw size={16} />{busy ? "正在检查…" : "立即检查"}</button></div></header>
    {message ? <p className="form-message" role="status">{message}</p> : null}
    {!canCheck ? <p className="admin-help">当前账户可读取检查记录；手工检查需要处理任务权限。</p> : null}
    {loading && !payload ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在读取检查记录……</p> : null}
    {!payload && message ? <button type="button" className="button secondary" disabled={loading} onClick={() => void load()}>重新读取</button> : null}
    {payload ? <section className="system-status-v2" aria-label="服务运行状况">
      <div>
        <section className="system-status-v2-list admin-panel"><header><h2>服务运行状况</h2><span>{cards.length} 项</span></header>
          <div className="system-status-reference-columns" aria-hidden="true"><span>服务项目</span><span>当前状态</span><span>最近检查时间</span><span>操作</span></div>
          <div role="listbox" aria-label="服务项目" onKeyDown={event => {
            const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("[role=option]"));
            const index = buttons.indexOf(event.target as HTMLButtonElement);
            if (index < 0 || !["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
            event.preventDefault();
            const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
            setSelectedKey(cards[next].key); buttons[next].focus();
          }}>{cards.map(({ key, title, scope, Icon, value }) => <button key={key} type="button" role="option" tabIndex={selected.key === key ? 0 : -1} aria-selected={selected.key === key} className={selected.key === key ? "selected" : ""} onClick={() => setSelectedKey(key)} title={scope}>
            <Icon size={21} aria-hidden="true" /><strong>{title}</strong><span data-status={value?.status ?? "unknown"}><i className="system-status-v2-dot" data-status={value?.status ?? "unknown"} />{statusLabel(value?.status)}</span><time>{checkedTime(value?.last_checked_at)}</time><em>查看详情</em>
          </button>)}</div>
        </section>
        <section className="admin-panel system-status-recent"><header><h2>最近检查记录</h2><span>{observations.length} 项</span></header><p className="admin-help">各服务最近一次观察，过期记录按当前接口标为等待检查。完整历史尚未提供。</p>{observations.length ? <>{recentRows(observations.slice(0, 5))}{observations.length > 5 ? <details><summary>查看其余 {observations.length - 5} 项</summary>{recentRows(observations.slice(5))}</details> : null}</> : <p>尚未返回检查记录。</p>}</section>
      </div>
      <section className="system-status-v2-detail admin-panel" data-status={selected.value?.status ?? "unknown"} aria-live="polite"><header><div><p className="system-status-v2-state"><i className="system-status-v2-dot" data-status={selected.value?.status ?? "unknown"} />{statusLabel(selected.value?.status)}</p><h2>{selected.title}</h2><p>最近检查时间：{checkedTime(selected.value?.last_checked_at)}</p></div><button className="button secondary" disabled={busy || !canCheck || !dependencies.length} onClick={() => void check(dependencies.map(row => row.probe_key))}>重试检查</button></header>
        <aside className="system-status-impact"><h3><CircleAlert size={21} />可能的影响</h3>{incidents.length ? incidents.map(incident => <div key={incident.id}><p>{incident.error_message || "尚未返回错误说明。"}</p><p>受影响功能：{incident.affected_features.join("、") || "尚未提供"}</p><h3>建议操作</h3>{incident.probable_causes.length ? <ul>{incident.probable_causes.map(cause => <li key={cause}>{cause}</li>)}</ul> : null}<p>{incident.manual_guidance || "尚未提供处理指引。"}</p></div>) : <p>当前接口没有返回这项服务的影响说明。</p>}</aside>
        <details className="system-status-check-details" open><summary>检查详情</summary><p className="admin-help">范围：{selected.scope}。打开本页只读取记录，手工检查后才更新观察。</p>{dependencies.length ? dependencies.map(probe => <section key={probe.probe_key}><h3>{probe.label}</h3><dl><div><dt>服务状态</dt><dd>{statusLabel(probe.status)}</dd></div><div><dt>检查时间</dt><dd>{checkedTime(probe.last_checked_at)}</dd></div><div><dt>响应时间</dt><dd>{probe.latency_ms === null ? "—" : `${probe.latency_ms} 毫秒`}</dd></div><div><dt>检查结果</dt><dd>{probe.summary}</dd></div></dl></section>) : <p>尚未返回检查详情。</p>}</details>
        <details><summary>相关日志（技术详情）</summary>{dependencies.map(probe => <section key={probe.probe_key}><h3>{probe.label}</h3><p>观察编号：{probe.observation_id || "—"} · 错误代码：{probe.error_code || "—"}</p><StatusDetails value={probe.details} /></section>)}</details>
      </section>
    </section> : null}
    <details className="system-status-technical" onToggle={event => { const open = event.currentTarget.open; setTechnicalOpen(open); if (open) void loadTechnical(); }}><summary>全部技术状态与配置</summary>{technicalOpen ? <>{technicalError ? <p role="alert">{technicalError}<button type="button" onClick={() => void loadTechnical()}>重试读取</button></p> : null}{technical ? <><p>快照读取时间：{checkedTime(technical.generated_at)}。此时间不作为服务的最近探测时间。</p>{Object.entries(technical).filter(([key]) => key !== "generated_at").map(([key, value]) => <details key={key}><summary>{({ database: "数据库", redis: "Redis", celery: "Celery 任务", storage: "NAS 存储", query_lexicon: "检索用语", semantic: "语义索引", embedding: "Embedding 模型", ai: "AI 服务", web_enrichment: "联网补全来源", backup: "备份" } as Record<string, string>)[key] ?? keyLabel(key)}</summary><StatusDetails value={value} /></details>)}</> : !technicalError ? <p>正在读取技术状态……</p> : null}</> : null}</details>
  </div>;
}
