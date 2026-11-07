"use client";

import { Activity, CheckCircle2, CircleAlert, Play, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { LoadingState } from "@/components/ui/loading-state";
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
  broker: "任务消息服务",
  worker: "后台任务连接",
  rapidocr: "RapidOCR · PP-OCRv6 tiny",
  remote_ocr: "远程 OCR",
  meilisearch: "Meilisearch",
  embedding_model: "语义模型",
  metadata_providers: "元数据来源",
  public_catalog_freshness: "公开目录更新",
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
      setMessage("服务检查已完成，请查看各项结果。");
      await load();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "服务检查失败。");
    } finally {
      setPending(false);
    }
  }

  const selfTestSteps = selfTest && typeof selfTest.steps === "object" && selfTest.steps
    ? Object.entries(selfTest.steps as Record<string, unknown>)
    : [];

  return (
    <div className="admin-page system-health-page">
      <header className="admin-page-title">
        <div><h1>服务检查</h1></div>
        <div className="admin-title-actions">
          <button className="button secondary" type="button" onClick={() => void load()} disabled={pending}><RefreshCw size={15} />刷新</button>
          <button className="button" type="button" onClick={() => void runSelfTest()} disabled={pending}><Play size={15} />运行检查</button>
        </div>
      </header>
      {pending && !payload ? <LoadingState>正在读取检查记录…</LoadingState> : null}
      <section className="system-health-v2-layout">
        <div className="system-health-v2-results">
          <section className="admin-panel system-health-v2-scope"><header><h2>检查结果</h2><span>{payload ? `读取于 ${new Date(payload.checked_at).toLocaleString("zh-CN")}` : "尚未检查"}</span></header><p>点击“运行检查”后开始检查。刷新只读取已有结果。</p></section>
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
          {selfTest ? <section className="admin-panel system-health-v2-self-test"><header><Activity size={18} /><h2>最近一次运行检查</h2><strong>{selfTest.all_available ? "通过" : "需要处理"}</strong></header><dl>{selfTestSteps.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value && typeof value === "object" && "available" in value ? ((value as { available?: unknown }).available ? "可用" : "不可用") : "已返回结果"}</dd></div>)}</dl><details><summary>查看检查详情</summary><pre>{JSON.stringify(selfTest, null, 2)}</pre></details></section> : null}
        </div>

      </section>
      {message ? <p className="form-message" role="status">{message}</p> : null}
    </div>
  );
}
