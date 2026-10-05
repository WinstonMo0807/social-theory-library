"use client";

import { Activity, CheckCircle2, CircleAlert, LoaderCircle, Play, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { AdminPublicPreviewFrame } from "@/components/admin/admin-public-preview-frame";

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
  pdf_parse: "文件解析",
  page_retrieval: "页面读取",
  ocr: "文字识别",
  meilisearch_write_search: "搜索写入与返回",
  embedding: "语义检索",
};

export function AdminSystemHealth() {
  const [payload, setPayload] = useState<HealthPayload | null>(null);
  const [selfTest, setSelfTest] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(1);

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
    setCurrentStep(2);
    try {
      const result = await apiRequest<Record<string, unknown>>("/ingestion/system-health/", {
        method: "POST",
        body: JSON.stringify({ action: "self_test" }),
      }, token);
      setSelfTest(result);
      setCurrentStep(3);
      setMessage(result.all_available ? "端到端自检已完成，各项检查通过。" : "端到端自检已完成，部分检查需要处理。");
    } catch (reason) {
      setCurrentStep(3);
      setMessage(reason instanceof Error ? reason.message : "端到端自检失败。");
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
        <div><p>处理中心 / 运行检查</p><h1>系统检查</h1><span>检查网站核心功能是否正常，确保读者可以顺利访问和使用。</span></div>
        <div className="admin-title-actions">
          <button className="button secondary" type="button" onClick={() => void load()} disabled={pending}><RefreshCw size={15} />刷新</button>
          <button className="button" type="button" onClick={() => void runSelfTest()} disabled={pending}><Play size={15} />端到端自检</button>
        </div>
      </header>
      {pending && !payload ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在检查……</p> : null}
      <ol className="system-health-v2-steps" aria-label="系统检查步骤">
        {["选择检查范围", "运行检查", "查看结果"].map((label, index) => { const step = (index + 1) as 1 | 2 | 3; return <li className={currentStep === step ? "current" : currentStep > step ? "complete" : ""} key={label}><span>{currentStep > step ? "✓" : step}</span><strong>{label}</strong><small>{step === 1 ? "全站" : step === 2 ? "明确点击后执行" : currentStep === 3 ? "已生成结果" : "等待"}</small></li>; })}
      </ol>
      <section className="system-health-v2-layout">
        <div className="system-health-v2-results">
          <section className="admin-panel system-health-v2-scope"><header><h2>检查结果</h2><span>{payload ? `检查于 ${new Date(payload.checked_at).toLocaleString("zh-CN")}` : "尚未检查"}</span></header><p>打开页面或刷新会检查服务连接与现有文件。端到端自检会另外使用临时文件和临时索引测试文字识别与搜索，不修改馆藏。</p></section>
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
          {selfTest ? <section className="admin-panel system-health-v2-self-test"><header><Activity size={18} /><h2>最近一次端到端自检</h2><strong>{selfTest.all_available ? "通过" : "需要处理"}</strong></header><dl>{selfTestSteps.map(([key, value]) => <div key={key}><dt>{labels[key] ?? key}</dt><dd>{value && typeof value === "object" && "available" in value ? ((value as { available?: unknown }).available ? "可用" : "不可用") : "已返回结果"}</dd></div>)}</dl><details><summary>查看检查详情</summary><pre>{JSON.stringify(selfTest, null, 2)}</pre></details></section> : null}
        </div>
        <AdminPublicPreviewFrame title="公开首页" src="/" />
      </section>
      {message ? <p className="form-message" role="status">{message}</p> : null}
    </div>
  );
}
