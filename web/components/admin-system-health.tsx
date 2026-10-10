"use client";

import { ArrowRight, BookOpen, CheckCircle2, ChevronRight, CircleAlert, FileText, LoaderCircle, Play, RefreshCw, Search } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { AdminPublicPreviewFrame } from "@/components/admin/admin-public-preview-frame";
import { AdminReaderPreview } from "@/components/admin/admin-reader-preview";

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

type SelfTestPayload = {
  started_at: string;
  duration_seconds: number;
  all_available: boolean;
  steps: Record<string, { available?: boolean; probe_cleaned?: boolean; error?: string; fallback_reason?: string }>;
};

export function systemCheckResults(payload: HealthPayload | null, selfTest: SelfTestPayload | null) {
  function tested(keys: string[]): boolean | null {
    const steps = keys.map(key => selfTest?.steps[key]);
    if (steps.some(step => step?.available === false)) return false;
    return steps.every(step => step?.available === true) ? true : null;
  }
  const storage = payload?.components.storage;
  const search = payload?.components.meilisearch;
  const catalog = payload?.components.public_catalog_freshness;
  const fileAvailable = selfTest ? tested(["pdf_parse", "page_retrieval", "ocr"]) : storage?.available ?? null;
  const searchProbe = selfTest?.steps.meilisearch_write_search;
  let searchAvailable: boolean | null = search?.available === false ? false : null;
  if (selfTest) {
    searchAvailable = tested(["meilisearch_write_search", "embedding"]);
    if (searchProbe?.probe_cleaned === false) searchAvailable = false;
    else if (searchAvailable === true && searchProbe?.probe_cleaned !== true) searchAvailable = null;
  }
  const fileDetail = selfTest
    ? ["pdf_parse", "page_retrieval", "ocr"].map(key => selfTest.steps[key]?.error).filter(Boolean).join("；")
    : storage?.last_error || (typeof storage?.detail === "string" ? storage.detail : "尚无可抽查的原始 PDF。");
  const searchDetail = selfTest
    ? ["meilisearch_write_search", "embedding"].map(key => selfTest.steps[key]?.error || selfTest.steps[key]?.fallback_reason).filter(Boolean).join("；") || (searchProbe?.probe_cleaned === false ? "临时索引清理未完成，请查看技术详情。" : "")
    : search?.last_error || "尚未运行实际查询测试。";
  const catalogFailed = !selfTest && catalog?.available === false;
  return [
    { key: "file", label: "文件能打开", available: fileAvailable, status: fileAvailable === null ? "待检查" : fileAvailable ? selfTest ? "通过" : "抽查可读取" : "需处理", description: selfTest ? "临时 PDF 的打开、页面生成与文字识别。" : "只读抽查最近原始 PDF 的文件头，完整阅读可在右侧核对。", detail: fileDetail },
    { key: "search", label: "搜索能返回", available: searchAvailable, status: searchAvailable === null ? "检索待测" : searchAvailable ? "通过" : "需处理", description: selfTest ? "临时索引写入与查询、索引清理以及当前语义检索。" : "当前读取服务连接；实际查询返回需运行端到端自检。", detail: searchDetail },
    { key: "content", label: "内容可见", available: catalogFailed ? false : null, status: catalogFailed ? "需处理" : "访问待核实", description: "目录记录不能替代读者页面访问，请对照右侧实际页面。", detail: catalogFailed ? catalog?.last_error || "公开目录记录需要处理。" : "当前没有自动访问页面的检查结果。" },
  ];
}

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
  const [selfTest, setSelfTest] = useState<SelfTestPayload | null>(null);
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(1);
  const [showSettings, setShowSettings] = useState(false);
  const [previewStep, setPreviewStep] = useState(0);
  const [previewDevice, setPreviewDevice] = useState<"desktop" | "mobile">("desktop");
  const pendingAction = useRef(false);

  const load = useCallback(async () => {
    const token = getServerSessionCredential();
    if (!token || pendingAction.current) return;
    pendingAction.current = true;
    setPending(true);
    setSelfTest(null);
    setCurrentStep(2);
    try {
      setPayload(await apiRequest<HealthPayload>("/ingestion/system-health/", {}, token));
      setMessage("");
      setCurrentStep(3);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "系统状态读取失败。");
    } finally {
      pendingAction.current = false;
      setPending(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function runSelfTest() {
    const token = getServerSessionCredential();
    if (!token || pendingAction.current) return;
    pendingAction.current = true;
    setPending(true);
    setMessage("");
    setSelfTest(null);
    setCurrentStep(2);
    try {
      const result = await apiRequest<SelfTestPayload>("/ingestion/system-health/", {
        method: "POST",
        body: JSON.stringify({ action: "self_test" }),
      }, token);
      setSelfTest(result);
      setCurrentStep(3);
      setMessage(result.all_available ? "临时文件与检索自检已完成。读者页面访问仍需核对右侧预览。" : "端到端自检已完成，部分检查需要处理。");
    } catch (reason) {
      setCurrentStep(3);
      setMessage(reason instanceof Error ? reason.message : "端到端自检失败。");
    } finally {
      pendingAction.current = false;
      setPending(false);
    }
  }

  const results = systemCheckResults(payload, selfTest);
  const checkedAt = selfTest?.started_at || payload?.checked_at;
  const failedCount = results.filter(row => row.available === false).length;
  const waitingCount = results.filter(row => row.available === null).length;
  const journey = <nav className="system-health-journey" aria-label="读者访问路径">{["访问首页", "浏览馆藏", "使用搜索", "阅读内容"].map((label, index) => <button type="button" key={label} aria-current={previewStep === index ? "step" : undefined} onClick={() => setPreviewStep(index)}>{index + 1}. {label}{index < 3 ? <ChevronRight size={14} aria-hidden="true" /> : null}</button>)}</nav>;

  return (
    <div className="admin-page system-health-page">
      <header className="admin-page-title">
        <div><h1>系统检查</h1><span>检查网站核心功能是否正常，确保读者可以顺利访问和使用。</span></div>
        <div className="admin-title-actions">
          <small>上次结果：{checkedAt ? new Date(checkedAt).toLocaleString("zh-CN") : "—"}　|　检查范围：整站</small>
          <button className="button secondary" type="button" aria-expanded={showSettings} aria-controls="system-health-settings" onClick={() => setShowSettings(value => !value)}>检查设置</button>
        </div>
      </header>
      {pending && !payload ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在检查……</p> : null}
      <section id="system-health-settings" className="admin-panel system-health-settings" hidden={!showSettings}><label>检查范围<select disabled value="all"><option value="all">整站</option></select></label><p>当前仅支持整站检查。连接与文件检查读取现有记录和原始 PDF；端到端自检另外使用临时文件和临时索引，不修改馆藏。</p><div><button className="button secondary" type="button" onClick={() => void load()} disabled={pending}><RefreshCw size={15} />刷新连接与文件检查</button><button className="button" type="button" onClick={() => void runSelfTest()} disabled={pending}><Play size={15} />{pending ? "正在检查…" : "运行端到端自检"}</button></div></section>
      <ol className="system-health-v2-steps" aria-label="系统检查步骤">
        {["选择检查范围", "运行检查", "查看结果"].map((label, index) => { const step = (index + 1) as 1 | 2 | 3; return <li className={currentStep === step ? "current" : currentStep > step ? "complete" : ""} aria-current={currentStep === step ? "step" : undefined} key={label}><span>{currentStep > step ? "✓" : step}</span><strong>{step}　{label}</strong><small>{step === 1 ? "整站" : step === 2 ? pending ? "正在检查" : currentStep === 3 ? "已返回结果" : "等待" : currentStep === 3 ? "当前：第 3 / 3 步" : "等待"}</small></li>; })}
      </ol>
      <section className="system-health-v2-layout">
        <section className="admin-panel system-health-v2-results">
          <header><h2>检查结果</h2><p>结果记录：{checkedAt ? new Date(checkedAt).toLocaleString("zh-CN") : "—"}　|　{selfTest ? "端到端临时测试" : "连接、文件与目录记录"}</p></header>
          <div className="system-health-result-list">{results.map((row, index) => { const Icon = [FileText, Search, BookOpen][index]; return <details className="system-health-result" data-status={row.available === null ? "unknown" : row.available ? "available" : "failed"} key={row.key}><summary><Icon size={23} aria-hidden="true"/><span><strong>{row.label}</strong><small>{row.description}</small></span><span className="system-health-result-state"><i/>{row.status}</span><ChevronRight size={16} aria-hidden="true"/></summary><p>{row.detail || "本次检查已返回结果，具体范围见上方说明。"}</p></details>; })}</div>
          <aside className="system-health-result-notice"><CircleAlert size={22}/><div><strong>{failedCount ? `发现 ${failedCount} 项需要进一步处理` : waitingCount ? `还有 ${waitingCount} 项待核实` : "本次临时测试通过"}</strong><p>连接可用不等于检索与页面已通过。可查看各项结果，并在右侧核对读者实际访问过程。</p></div><button className="button secondary" type="button" onClick={() => setShowSettings(true)}>检查设置<ArrowRight size={14}/></button></aside>
          <section className="system-health-result-info"><h3>其他信息</h3><dl><div><dt>检查范围</dt><dd>整站</dd></div><div><dt>检查时长</dt><dd>{selfTest ? `${selfTest.duration_seconds} 秒` : "—"}</dd></div><div><dt>下次建议</dt><dd>更新内容或搜索设置后，可重新检查并核对实际页面。</dd></div></dl></section>
          <details className="system-health-technical"><summary>技术检查与原始诊断</summary><p>连接与目录记录检查：{payload ? new Date(payload.checked_at).toLocaleString("zh-CN") : "—"}</p><section className="health-component-grid">
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
          </section>{selfTest ? <section className="system-health-v2-self-test"><h3>最近一次端到端自检</h3><dl>{Object.entries(selfTest.steps).map(([key, value]) => <div key={key}><dt>{labels[key] ?? key}</dt><dd>{value.available === true ? "可用" : value.available === false ? "不可用" : "待核实"}</dd></div>)}</dl><details><summary>查看完整自检详情</summary><pre>{JSON.stringify(selfTest, null, 2)}</pre></details></section> : null}</details>
        </section>
        {previewStep === 3 ? <AdminReaderPreview footer={journey} height={566} device={previewDevice} onDeviceChange={setPreviewDevice}/> : <AdminPublicPreviewFrame title="读者会看到什么" description="预览读者实际访问的页面；预览不会写成自动检查通过。" src={["/", "/explore/original", "/explore"][previewStep]} footer={journey} height={566} device={previewDevice} onDeviceChange={setPreviewDevice}/>}
      </section>
      {message ? <p className="form-message" role="status">{message}</p> : null}
    </div>
  );
}
