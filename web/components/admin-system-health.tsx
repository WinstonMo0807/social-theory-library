"use client";

import { Activity, CheckCircle2, CircleAlert, LoaderCircle, Play, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

type ComponentHealth = {
  configured: boolean;
  available: boolean | null;
  last_successful_check: string | null;
  last_error: string;
  detail: unknown;
};

type HealthPayload = {
  checked_at: string;
  components: Record<string, ComponentHealth>;
};

const labels: Record<string, string> = {
  database: "数据库",
  storage: "NAS 存储",
  cache: "Redis 缓存",
  broker: "Celery 消息代理",
  worker: "Worker 心跳",
  paddleocr: "PaddleOCR",
  remote_ocr: "远程 OCR",
  meilisearch: "Meilisearch",
  embedding_model: "语义模型",
  metadata_providers: "元数据来源",
  public_catalog_freshness: "公开目录新鲜度",
};

export function AdminSystemHealth() {
  const [payload, setPayload] = useState<HealthPayload | null>(null);
  const [selfTest, setSelfTest] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);

  const load = useCallback(async () => {
    const token = getServerSessionCredential();
    if (!token) return;
    setPending(true);
    try {
      setPayload(await apiRequest<HealthPayload>("/ingestion/system-health/", {}, token));
      setMessage("");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "系统状态读取失败。");
    } finally {
      setPending(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function runSelfTest() {
    const token = getServerSessionCredential();
    if (!token) return;
    setPending(true);
    try {
      const result = await apiRequest<Record<string, unknown>>("/ingestion/system-health/", {
        method: "POST",
        body: JSON.stringify({ action: "self_test" }),
      }, token);
      setSelfTest(result);
      setMessage("端到端自检已经完成。失败步骤不会影响已经发布的原始 PDF。");
      await load();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "端到端自检失败。");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="admin-page system-health-page">
      <header className="admin-page-title">
        <div><p>概览</p><h1>系统健康检查</h1><span>区分已配置、当前可用、最后成功和最近错误。检查不会改变馆藏。</span></div>
        <div className="admin-title-actions">
          <button className="button secondary" type="button" onClick={() => void load()} disabled={pending}><RefreshCw size={15} />刷新</button>
          <button className="button" type="button" onClick={() => void runSelfTest()} disabled={pending}><Play size={15} />端到端自检</button>
        </div>
      </header>
      {pending && !payload ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在检查……</p> : null}
      <section className="health-component-grid">
        {Object.entries(payload?.components ?? {}).map(([key, component]) => (
          <article className={`admin-panel health-component ${component.available === true ? "available" : component.available === false ? "failed" : "unknown"}`} key={key}>
            <header>{component.available === true ? <CheckCircle2 size={18} /> : <CircleAlert size={18} />}<h2>{labels[key] ?? key}</h2></header>
            <dl>
              <div><dt>已配置</dt><dd>{component.configured ? "是" : "否"}</dd></div>
              <div><dt>当前可用</dt><dd>{component.available === null ? "待测试" : component.available ? "可用" : "不可用"}</dd></div>
              <div><dt>最近成功检查</dt><dd>{component.last_successful_check ? new Date(component.last_successful_check).toLocaleString("zh-CN") : "尚无"}</dd></div>
            </dl>
            {component.last_error ? <p className="health-error">{component.last_error}</p> : null}
            <details><summary>诊断详情</summary><pre>{JSON.stringify(component.detail, null, 2)}</pre></details>
          </article>
        ))}
      </section>
      {selfTest ? <section className="admin-panel"><header><Activity size={18} /><h2>最近一次端到端自检</h2></header><pre>{JSON.stringify(selfTest, null, 2)}</pre></section> : null}
      {message ? <p className="form-message" role="status">{message}</p> : null}
    </div>
  );
}
