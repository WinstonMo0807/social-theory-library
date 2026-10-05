"use client";

import { BarChart3, Pause, Play, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import styles from "./semantic-index-reference.module.css";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { AdminPublicPreviewFrame } from "@/components/admin/admin-public-preview-frame";

type IndexPayload = {
  permissions: { can_manage: boolean };
  runtime: {
    enabled: boolean;
    engine: string;
    provider: string;
    model: string;
    reranker: string;
    query_rewrite_enabled: boolean;
    semantic_ratio: number;
    embedder_name: string;
    model_repo_id: string;
    model_revision: string;
    offline_mode: boolean;
  };
  model_health: { configured: boolean; available: boolean | null; reason: string; cache_root?: string };
  index_versions: { id: string; uid: string; status: string; model_repo_id: string; model_revision: string; dimensions: number | null; document_count: number; expected_document_count: number; validation_details: Record<string, unknown>; created_at: string; activated_at: string | null; error: string }[];
  paused: boolean;
  documents: { eligible: number; indexed: number; pending: number; failed: number };
  chunks: Record<string, number>;
  feedback: { total: number; relevant: number; not_relevant: number };
  recent_jobs: {
    id: string;
    operation: string;
    status: string;
    progress: number;
    asset_id: string | null;
    title: string;
    attempts: number;
    error: string;
    created_at: string;
  }[];
};

type TestPayload = {
  count: number;
  engine?: string;
  timing_ms?: number | null;
  fallback_used: boolean;
  notice: string;
  effective_configuration?: { semantic_ratio: number; embedder: string; provider: string; model: string; revision: string; offline_mode: boolean; model_health: { available: boolean | null; reason: string } };
  comparison?: {
    keyword_results: unknown[];
    semantic_results: unknown[];
    final_results: unknown[];
    latency_ms: { keyword: number | null; semantic: number | null; final: number | null };
  };
  results: { id: string; title: string; page_index: number; printed_label?: string; relevance: string; snippet: string; debug?: Record<string, unknown> }[];
};

type EvaluationSetSummary = {
  id: string;
  name: string;
  description: string;
  language: string;
  is_active: boolean;
  query_count: number;
  judgment_count: number;
  updated_at: string;
};

type EvaluationRunSummary = {
  id: string;
  evaluation_set: string;
  evaluation_set_name: string;
  index_version: string | null;
  index_uid: string;
  status: "pending" | "running" | "completed" | "failed";
  semantic_ratio: number;
  metrics: Record<string, number>;
  query_count: number;
  completed_query_count: number;
  task_id: string;
  error_message: string;
  created_at: string;
};

type EvaluationPlan = {
  can_execute: boolean;
  query_count: number;
  blockers: { code: string; detail: string }[];
  warnings: { code: string; detail: string }[];
};

const indexStatusLabels: Record<string, string> = {
  building: "构建中",
  ready: "待验证",
  active: "当前生产",
  failed: "失败",
  retired: "已停用，可回退",
};

const jobStatusLabels: Record<string, string> = {
  pending: "等待中",
  queued: "已排队",
  running: "处理中",
  paused: "已暂停",
  succeeded: "已完成",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const evaluationStatusLabels: Record<string, string> = {
  pending: "等待中",
  running: "评估中",
  completed: "已完成",
  failed: "失败",
};

const operationLabels: Record<string, string> = {
  build: "建立索引",
  rebuild_asset: "重建单本",
  rebuild_all: "批量重建",
  stage_snapshot_version: "建立快照候选",
  clean_orphans: "清理孤立索引",
  retry_failed: "重试失败项目",
  delete: "删除索引文档",
};

export function SemanticIndexAdmin() {
  const [surface, setSurface] = useState<"index" | "evaluation">("index");
  const [step, setStep] = useState(1);
  const [selectedVersion, setSelectedVersion] = useState("");
  const [savedQuestions, setSavedQuestions] = useState<{id:string;query_text:string;judgments:unknown[]}[]>([]);
  const actionPending = useRef(false);
  const [data, setData] = useState<IndexPayload | null>(null);
  const [dataLoaded, setDataLoaded] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [query, setQuery] = useState("");
  const [previewQuery, setPreviewQuery] = useState("");
  const [testResult, setTestResult] = useState<(TestPayload & { testedQuery: string }) | null>(null);
  const [activateTarget, setActivateTarget] = useState<IndexPayload["index_versions"][number] | null>(null);
  const [evaluationSets, setEvaluationSets] = useState<EvaluationSetSummary[]>([]);
  const [evaluationRuns, setEvaluationRuns] = useState<EvaluationRunSummary[]>([]);
  const [evaluationsLoaded, setEvaluationsLoaded] = useState(false);
  const [evaluationError, setEvaluationError] = useState("");
  const [evaluationName, setEvaluationName] = useState("");
  const [evaluationDescription, setEvaluationDescription] = useState("");
  const [evaluationLanguage, setEvaluationLanguage] = useState("zh-CN");
  const [evaluationTargetSetId, setEvaluationTargetSetId] = useState("");
  const [evaluationIndexId, setEvaluationIndexId] = useState("");
  const [evaluationJudgments, setEvaluationJudgments] = useState<Record<string, number>>({});
  const [evaluationMessage, setEvaluationMessage] = useState("");
  const judgmentsDirty = useUnsavedForm(evaluationJudgments, {});
  const allowQueryChange = () => !judgmentsDirty || window.confirm("当前评价尚未保存，确定放弃后重新选择问题吗？");
  const effectiveEvaluationIndexId = evaluationIndexId
    || data?.index_versions.find((version) => version.status === "ready")?.id
    || data?.index_versions.find((version) => version.status === "active")?.id
    || data?.index_versions[0]?.id
    || "";

  const refreshEvaluations = useCallback(async () => {
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      const [sets, runs] = await Promise.all([
        apiRequest<EvaluationSetSummary[]>("/catalog/admin/search-evaluations/sets/", {}, token),
        apiRequest<EvaluationRunSummary[]>("/catalog/admin/search-evaluations/runs/", {}, token),
      ]);
      setEvaluationSets(sets);
      setEvaluationRuns(runs);
      setEvaluationsLoaded(true);
      setEvaluationError("");
    } catch (reason) {
      setEvaluationsLoaded(true);
      setEvaluationError(reason instanceof Error ? reason.message : "检索评估状态加载失败。");
    }
  }, []);

  const refresh = useCallback(async () => {
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      setData(await apiRequest<IndexPayload>("/catalog/admin/semantic-index/", {}, token));
      setDataLoaded(true);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "语义索引状态加载失败。");
    }
  }, []);

  useEffect(() => {
    let active = true;
    const token = getServerSessionCredential();
    if (!token) return;
    apiRequest<IndexPayload>("/catalog/admin/semantic-index/", {}, token)
      .then((payload) => {
        if (active) {
          setData(payload);
          setDataLoaded(true);
          setError("");
        }
      })
      .catch((reason) => {
        if (active) {
          setDataLoaded(true);
          setError(reason instanceof Error ? reason.message : "语义索引状态加载失败。");
        }
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    const token = getServerSessionCredential();
    if (!token) return;
    Promise.all([
      apiRequest<EvaluationSetSummary[]>("/catalog/admin/search-evaluations/sets/", {}, token),
      apiRequest<EvaluationRunSummary[]>("/catalog/admin/search-evaluations/runs/", {}, token),
    ])
      .then(([sets, runs]) => {
        if (!active) return;
        setEvaluationSets(sets);
        setEvaluationRuns(runs);
        setEvaluationsLoaded(true);
        setEvaluationError("");
      })
      .catch((reason) => {
        if (active) {
          setEvaluationsLoaded(true);
          setEvaluationError(reason instanceof Error ? reason.message : "检索评估状态加载失败。");
        }
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!evaluationRuns.some((run) => run.status === "pending" || run.status === "running")) return;
    const timer = window.setInterval(() => void refreshEvaluations(), 3000);
    return () => window.clearInterval(timer);
  }, [evaluationRuns, refreshEvaluations]);

  useEffect(() => {
    const controller = new AbortController();
    const reset = window.setTimeout(() => setSavedQuestions([]), 0);
    if (evaluationTargetSetId) void apiRequest<{queries: typeof savedQuestions}>(`/catalog/admin/search-evaluations/sets/${evaluationTargetSetId}/`, {signal:controller.signal}, getServerSessionCredential())
      .then(result => { if (!controller.signal.aborted) setSavedQuestions(result.queries); })
      .catch(reason => { if (!controller.signal.aborted) setEvaluationError(reason instanceof Error ? reason.message : "问题列表读取失败"); });
    return () => { controller.abort();window.clearTimeout(reset); };
  }, [evaluationTargetSetId]);

  async function runAction(action: string, assetId?: string | null) {
    const token = getServerSessionCredential();
    if (!token || actionPending.current) return;
    actionPending.current = true;
    setBusy(action);
    try {
      await apiRequest("/catalog/admin/semantic-index/", {
        method: "POST",
        body: JSON.stringify({ action, asset_id: assetId || undefined }),
      }, token);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "索引操作失败。");
    } finally {
      actionPending.current = false;
      setBusy("");
    }
  }

  async function testQuery(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    const testedQuery = query.trim();
    if (!token || testedQuery.length < 2 || actionPending.current) return;
    if (!allowQueryChange()) return;
    actionPending.current = true;
    setPreviewQuery(testedQuery);
    setBusy("test");
    setError("");
    setTestResult(null);
    setEvaluationJudgments({});
    try {
      const result = await apiRequest<TestPayload>("/catalog/admin/semantic-index/test-query/", {
        method: "POST",
        body: JSON.stringify({ query: testedQuery }),
      }, token);
      setTestResult({ ...result, testedQuery });
      setStep(2);
    } catch (reason) {
      setTestResult(null);
      setError(reason instanceof Error ? reason.message : "测试查询失败。");
    } finally {
      actionPending.current = false;
      setBusy("");
    }
  }

  async function saveEvaluationQuery(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    const judgments = Object.entries(evaluationJudgments).map(([chunkId, relevance]) => ({
      chunk_id: chunkId,
      relevance,
    }));
    if (!token || !testResult || testResult.testedQuery !== query.trim() || actionPending.current) return;
    if (!evaluationTargetSetId && !evaluationName.trim()) {
      setEvaluationMessage("新建评估集时需要填写名称。");
      return;
    }
    actionPending.current = true;
    setBusy("save_evaluation_query");
    setEvaluationMessage("");
    try {
      if (evaluationTargetSetId) {
        await apiRequest(
          `/catalog/admin/search-evaluations/sets/${evaluationTargetSetId}/queries/`,
          {
            method: "POST",
            body: JSON.stringify({
              query_text: testResult.testedQuery,
              judgments,
            }),
          },
          token,
        );
        setEvaluationMessage("查询和人工相关性已经加入现有评估集。");
      } else {
        await apiRequest("/catalog/admin/search-evaluations/sets/", {
          method: "POST",
          body: JSON.stringify({
            name: evaluationName.trim(),
            description: evaluationDescription.trim(),
            language: evaluationLanguage,
            is_active: true,
            queries: [{ query_text: testResult.testedQuery, judgments }],
          }),
        }, token);
        setEvaluationMessage("评估集已建立。可以继续加入查询，或先运行一次基线评估。");
        setEvaluationName("");
        setEvaluationDescription("");
      }
      setEvaluationJudgments({});
      setTestResult(null);
      await refreshEvaluations();
    } catch (reason) {
      setEvaluationMessage(reason instanceof Error ? reason.message : "评估查询保存失败。");
    } finally {
      actionPending.current = false;
      setBusy("");
    }
  }

  async function runEvaluation(evaluationSetId: string) {
    const token = getServerSessionCredential();
    if (actionPending.current) return;
    if (!token || !effectiveEvaluationIndexId || !data) {
      setEvaluationMessage("请先选择一个候选或活动索引版本。");
      return;
    }
    actionPending.current = true;
    setBusy(`evaluate:${evaluationSetId}`);
    setEvaluationMessage("正在核对评估集、模型配置和候选索引文档数……");
    const payload = {
      evaluation_set: evaluationSetId,
      index_version: effectiveEvaluationIndexId,
      semantic_ratio: data.runtime.semantic_ratio,
    };
    try {
      const plan = await apiRequest<EvaluationPlan>("/catalog/admin/search-evaluations/runs/", {
        method: "POST",
        body: JSON.stringify({ ...payload, mode: "dry_run" }),
      }, token);
      if (!plan.can_execute) {
        setEvaluationMessage(plan.blockers.map((blocker) => blocker.detail).join("；") || "评估预检未通过。");
        return;
      }
      const run = await apiRequest<EvaluationRunSummary>("/catalog/admin/search-evaluations/runs/", {
        method: "POST",
        body: JSON.stringify({ ...payload, mode: "enqueue" }),
      }, token);
      setEvaluationMessage(`评估任务已提交，共 ${run.query_count} 条查询。页面会自动刷新进度。`);
      await refreshEvaluations();
    } catch (reason) {
      setEvaluationMessage(reason instanceof Error ? reason.message : "检索评估提交失败。");
    } finally {
      actionPending.current = false;
      setBusy("");
    }
  }

  async function toggleEvaluationSet(evaluationSet: EvaluationSetSummary) {
    const token = getServerSessionCredential();
    if (!token || actionPending.current) return;
    actionPending.current = true;
    setBusy(`evaluation_set:${evaluationSet.id}`);
    try {
      await apiRequest(`/catalog/admin/search-evaluations/sets/${evaluationSet.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !evaluationSet.is_active }),
      }, token);
      setEvaluationMessage(evaluationSet.is_active ? "评估集已停用，历史运行仍然保留。" : "评估集已重新启用。");
      await refreshEvaluations();
    } catch (reason) {
      setEvaluationMessage(reason instanceof Error ? reason.message : "评估集状态修改失败。");
    } finally {
      actionPending.current = false;
      setBusy("");
    }
  }

  async function activateVersion() {
    const token = getServerSessionCredential();
    if (!token || !activateTarget || actionPending.current) return;
    actionPending.current = true;
    setBusy("activate_version");
    setError("");
    try {
      await apiRequest("/catalog/admin/semantic-index/", {
        method: "POST",
        body: JSON.stringify({
          action: "activate_version",
          version_id: activateTarget.id,
          confirmed: true,
        }),
      }, token);
      setActivateTarget(null);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "候选索引切换失败。");
    } finally {
      actionPending.current = false;
      setBusy("");
    }
  }

  const current = data?.index_versions.find(version=>version.status==="active");
  const candidate = data?.index_versions.find(version=>version.id===selectedVersion) ?? data?.index_versions.find(version=>["building","ready","failed"].includes(version.status));
  const failedJobs = data?.recent_jobs.filter(job=>job.status==="failed") ?? [];
  const resultList = (<>          <div className="semantic-index-test-results">
            {testResult?.results.map((item, index) => (
              <article key={item.id}>
                <strong>{item.relevance} · {item.title}</strong>
                <span>{item.printed_label ? `引用第 ${item.printed_label} 页 · ` : ""}PDF 第 {item.page_index} 页</span>
                <p>{item.snippet}</p>
                <fieldset className={styles.judgments} disabled={Boolean(busy)}><legend>与问题的相关性</legend>{[{value:2,label:"相关"},{value:0,label:"不相关"},{value:null,label:"待判断"}].map(choice=><label key={choice.label}><input type="radio" name={`evaluation_relevance_${index}`} checked={(evaluationJudgments[item.id] ?? null)===choice.value} onChange={()=>setEvaluationJudgments(current=>{ const next={...current};if(choice.value===null) delete next[item.id];else next[item.id]=choice.value;return next; })}/>{choice.label}</label>)}</fieldset>
              </article>
            ))}
          </div>
</>);
  return <div className={styles.page}>
    <header className="admin-page-title"><div><h1>{surface==="index" ? "搜索内容更新" : "检查搜索结果"}</h1><p>{surface==="index" ? "检查搜索内容的更新进度，确认失败项目。" : "选择问题、检查实际返回的段落，再保存判断。"}</p></div><button type="button" className="button secondary" disabled={Boolean(busy)} onClick={()=>void refresh()}><RefreshCw size={16}/>重新检查</button></header>
    <nav className={styles.switcher} aria-label="搜索维护"><button type="button" disabled={Boolean(busy)} aria-pressed={surface==="index"} onClick={()=>setSurface("index")}>搜索内容更新</button><button type="button" disabled={Boolean(busy)} aria-pressed={surface==="evaluation"} onClick={()=>setSurface("evaluation")}>检查搜索结果</button></nav>
    {error ? <p role="alert">{error}</p> : null}
    {surface==="evaluation" ? <ol className="reference-step-strip">{["输入问题","检查结果","保存评价"].map((label,index)=><li key={label} aria-current={step===index+1 ? "step" : undefined}><button type="button" disabled={Boolean(busy) || (index>0 && !testResult)} onClick={()=>setStep(index+1)}><b>{index+1}</b>{label}</button></li>)}</ol> : null}
    <div className={styles.layout}><div>
    {surface==="index" ? <section className={styles.versions}><h2>搜索版本</h2><p>切换版本仅对所有者开放。请先检查完整性与评估结果。</p><label>当前使用版本<strong>{current ? `${new Date(current.created_at).toLocaleDateString("zh-CN")}（正式版）` : "—"}</strong></label><label>准备中的版本<select disabled={Boolean(busy)} value={candidate?.id || ""} onChange={event=>setSelectedVersion(event.target.value)}><option value="">—</option>{data?.index_versions.filter(version=>version.status!=="active").map(version=><option key={version.id} value={version.id}>{new Date(version.created_at).toLocaleDateString("zh-CN")} · {indexStatusLabels[version.status] || version.status}</option>)}</select></label>
      <h2>建立进度</h2>{candidate ? <><progress max={candidate.expected_document_count || 1} value={candidate.document_count}/><p>已保存索引文档 {candidate.document_count} / {candidate.expected_document_count || "—"}</p>{candidate.error ? <p role="alert">{candidate.error}</p> : null}{candidate.status==="ready" && data?.permissions.can_manage ? <button className="button" type="button" disabled={Boolean(busy)} onClick={()=>setActivateTarget(candidate)}>验证并启用</button> : null}</> : <p>—</p>}
      <dl>{[["全库已建立索引",data?.documents.indexed],["全库等待处理",data?.documents.pending],["全库失败",data?.documents.failed]].map(([label,value])=><div key={String(label)}><dt>{label}</dt><dd>{value ?? "—"}</dd></div>)}</dl>
      <h2>处理失败的内容</h2><p>最近返回的 {data?.recent_jobs.length ?? "—"} 条任务中，失败 {data ? failedJobs.length : "—"} 条。</p>{failedJobs.map(job=><article key={job.id}><strong>{job.title || "全库任务"}</strong><p>{job.error}</p>{job.asset_id && data?.permissions.can_manage ? <button type="button" disabled={Boolean(busy)} onClick={()=>void runAction("rebuild_asset",job.asset_id)}>重试该文档</button> : null}</article>)}{data?.permissions.can_manage ? <button className="button secondary" type="button" disabled={Boolean(busy)} onClick={()=>void runAction("retry_failed")}>重试失败项</button> : null}
      <details><summary>版本、任务与配置记录</summary>      <section className="admin-panel semantic-job-list">
        <header><h2>索引版本</h2><span>新版本完整验证后才切换生产指针</span></header>
        <div className="admin-table-scroll"><table><thead><tr><th>索引</th><th>模型</th><th>模型版本</th><th>维度</th><th>文档</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead><tbody>
          {data?.index_versions.map((version) => <tr key={version.id}><td><strong>{version.uid}</strong>{version.error ? <small className="attempt-error">{version.error}</small> : null}</td><td>{version.model_repo_id}</td><td>{version.model_revision}</td><td>{version.dimensions ?? "模型默认"}</td><td>{version.document_count}{version.expected_document_count ? ` / ${version.expected_document_count}` : ""}</td><td>{indexStatusLabels[version.status] ?? version.status}</td><td>{new Date(version.created_at).toLocaleString("zh-CN")}</td><td>{version.status === "ready" && data.permissions.can_manage ? <button type="button" disabled={Boolean(busy)} onClick={() => setActivateTarget(version)}>验证并切换</button> : version.status === "active" ? "当前生产" : "—"}</td></tr>)}
          {!dataLoaded ? <tr><td colSpan={8}>正在读取索引版本……</td></tr> : !data ? <tr><td colSpan={8}>索引版本暂时无法读取。</td></tr> : !data.index_versions.length ? <tr><td colSpan={8}>尚未建立版本化索引。</td></tr> : null}
        </tbody></table></div>
      </section>
        <article className="admin-panel semantic-index-runtime">
          <header><h2>当前配置</h2><span className={data?.paused ? "status warning" : "status"}>{!data ? "加载中" : data.paused ? "已暂停" : "运行中"}</span></header>
          <dl>
            <div><dt>功能状态</dt><dd>{!data ? "加载中" : data.runtime.enabled ? "已启用" : "已关闭"}</dd></div>
            <div><dt>检索引擎</dt><dd>{data?.runtime.engine || "加载中"}</dd></div>
            <div><dt>语义模型</dt><dd>{data?.runtime.model || "加载中"}</dd></div>
            <div><dt>模型状态</dt><dd>{!data ? "加载中" : data.model_health.available === true ? "本地文件已就绪" : data.model_health.available === false ? "语义模型不可用" : "尚未完成运行验证"}</dd></div>
            <div><dt>混合检索权重</dt><dd>{data ? `${Math.round(data.runtime.semantic_ratio * 100)}%` : "加载中"}</dd></div>
            <div><dt>离线模式</dt><dd>{!data ? "加载中" : data.runtime.offline_mode ? "禁止运行时联网下载" : "允许联网"}</dd></div>
            <div><dt>重排器</dt><dd>{data?.runtime.reranker || "规则回退"}</dd></div>
            <div><dt>反馈</dt><dd>{data ? `${data.feedback.relevant} 条相关，${data.feedback.not_relevant} 条不相关` : "加载中"}</dd></div>
          </dl>
          <p className="admin-help">混合检索权重只控制关键词与语义结果的融合，不是检索质量分数。模型状态不能单独证明关键词降级已经执行，请以下方测试查询结果为准。</p>
          {data?.model_health.reason ? <p className={data.model_health.available ? "admin-help" : "attempt-error"}>{data.model_health.reason}</p> : null}
          <div className="admin-action-row">
            {data?.permissions.can_manage ? <><button className="button secondary" type="button" disabled={Boolean(busy)} onClick={() => runAction(data.paused ? "resume" : "pause")}>{data.paused ? <Play size={15} /> : <Pause size={15} />}{data.paused ? "恢复任务" : "暂停任务"}</button>
            <button className="button secondary" type="button" disabled={Boolean(busy)} onClick={() => runAction("retry_failed")}><RefreshCw size={15} />只重试失败项目</button>
            <button className="button" type="button" disabled={Boolean(busy)} onClick={() => runAction("rebuild_all")}><RefreshCw size={15} />批量重建</button>
            <button className="button" type="button" disabled={Boolean(busy) || Boolean(data.index_versions.some((version) => version.status === "building" || version.status === "ready"))} onClick={() => runAction("stage_snapshot_version")}><RefreshCw size={15} />建立快照候选</button>
            <button className="button secondary" type="button" disabled={Boolean(busy)} onClick={() => runAction("clean_orphans")}><Trash2 size={15} />清理孤立索引</button></> : <span className="status">只读。索引构建与切换由超级管理员执行。</span>}
          </div>
        </article>
      <section className="admin-panel semantic-job-list">
        <header><h2>最近索引任务</h2><span>{data ? `${data.recent_jobs.length} 条` : "加载中"}</span></header>
        <div className="admin-table-scroll"><table><thead><tr><th>文献</th><th>任务类型</th><th>状态</th><th>进度</th><th>尝试次数</th><th>时间</th><th>操作</th></tr></thead><tbody>
          {data?.recent_jobs.map((job) => <tr key={job.id}><td><strong>{job.title || "全库任务"}</strong>{job.error ? <small className="attempt-error">{job.error}</small> : null}</td><td>{operationLabels[job.operation] ?? job.operation}</td><td>{jobStatusLabels[job.status] ?? job.status}</td><td>{job.progress}%</td><td>{job.attempts}</td><td>{new Date(job.created_at).toLocaleString("zh-CN")}</td><td>{job.asset_id && data.permissions.can_manage ? <button type="button" onClick={() => runAction("rebuild_asset", job.asset_id)}>单本重建</button> : null}</td></tr>)}
          {!dataLoaded ? <tr><td colSpan={7}>正在读取索引任务……</td></tr> : !data ? <tr><td colSpan={7}>索引任务暂时无法读取。</td></tr> : !data.recent_jobs.length ? <tr><td colSpan={7}>还没有语义索引任务。</td></tr> : null}
        </tbody></table></div>
      </section>
</details></section> : <>
      <section className={styles.questions}><h2>测试问题</h2><label>问题集<select disabled={Boolean(busy)} value={evaluationTargetSetId} onChange={event=>setEvaluationTargetSetId(event.target.value)}><option value="">新增问题集</option>{evaluationSets.map(item=><option value={item.id} key={item.id}>{item.name}</option>)}</select></label>{evaluationError ? <p role="alert">{evaluationError}</p> : null}{savedQuestions.map((item,index)=><button type="button" key={item.id} disabled={Boolean(busy)} aria-pressed={query===item.query_text} onClick={()=>{if(!allowQueryChange()) return;setQuery(item.query_text);setTestResult(null);setEvaluationJudgments({});setPreviewQuery("");setStep(1);}}><b>{index+1}</b>{item.query_text}</button>)}</section>
      {step<3 ? <>{        <form className="admin-panel semantic-index-test" onSubmit={testQuery}>
          <header><h2>测试一条查询</h2></header>
          <label><span>观点或问题</span><textarea rows={4} value={query} disabled={Boolean(busy)} onChange={(event) => { if (!allowQueryChange()) return; setQuery(event.target.value); setTestResult(null); setPreviewQuery(""); setEvaluationJudgments({}); setEvaluationMessage(""); }} placeholder="例如：为什么农业现代化以后，农民反而更依赖组织？" /></label>
          <button className="button" type="submit" disabled={Boolean(busy) || query.trim().length < 2} aria-busy={busy === "test"}><Search size={15} />{busy === "test" ? "正在测试" : "运行测试"}</button>
          {testResult ? <p className="semantic-index-test-summary">返回 {testResult.count} 条 · {testResult.timing_ms ?? "未记录"} ms · {testResult.fallback_used || testResult.engine === "keyword_fallback" ? "服务端确认使用关键词检索" : testResult.engine === "hybrid" ? "服务端确认完成混合检索" : "服务端已完成查询"}{testResult.effective_configuration?.semantic_ratio === undefined ? " · 混合检索权重未返回" : ` · 实际混合检索权重 ${Math.round(testResult.effective_configuration.semantic_ratio * 100)}%`}</p> : null}
          {testResult?.comparison ? <dl className="ocr-runtime-status"><div><dt>关键词结果</dt><dd>{testResult.comparison.keyword_results.length} 条 · {testResult.comparison.latency_ms.keyword ?? "—"} ms</dd></div><div><dt>语义结果</dt><dd>{testResult.comparison.semantic_results.length} 条 · {testResult.comparison.latency_ms.semantic ?? "—"} ms</dd></div><div><dt>最终结果</dt><dd>{testResult.comparison.final_results.length} 条 · {testResult.comparison.latency_ms.final ?? "—"} ms</dd></div></dl> : null}
        </form>}</> :       <section className="admin-panel search-evaluation-panel" aria-labelledby="search-evaluation-title">
        <header>
          <div>
            <h2 id="search-evaluation-title"><BarChart3 size={17} />馆内检索评估</h2>
            <span>用人工相关性检验候选索引，不会切换或删除任何索引版本</span>
          </div>
        </header>
        {evaluationError ? <p className="form-message error" role="alert">{evaluationError}</p> : null}
        <div className="search-evaluation-workspace">
          <form className="search-evaluation-editor" onSubmit={saveEvaluationQuery}>
            <h3>保存当前测试查询</h3>
            <p>先在上方运行真实查询，再给结果标注相关性。不相关结果可以全部保存；待判断的结果不提交标注。</p>
            <label>
              <span>保存位置</span>
              <select
                name="evaluation_target_set"
                value={evaluationTargetSetId}
                onChange={(event) => setEvaluationTargetSetId(event.target.value)}
              >
                <option value="">新建评估集</option>
                {evaluationSets.map((evaluationSet) => (
                  <option value={evaluationSet.id} key={evaluationSet.id}>{evaluationSet.name}</option>
                ))}
              </select>
            </label>
            {!evaluationTargetSetId ? (
              <>
                <label>
                  <span>评估集名称</span>
                  <input
                    name="evaluation_name"
                    value={evaluationName}
                    maxLength={240}
                    placeholder="例如 中文社会理论检索基线"
                    onChange={(event) => setEvaluationName(event.target.value)}
                  />
                </label>
                <label>
                  <span>说明</span>
                  <textarea
                    name="evaluation_description"
                    rows={3}
                    value={evaluationDescription}
                    placeholder="记录查询来源、适用范围和维护约定"
                    onChange={(event) => setEvaluationDescription(event.target.value)}
                  />
                </label>
                <label>
                  <span>主要语言</span>
                  <select
                    name="evaluation_language"
                    value={evaluationLanguage}
                    onChange={(event) => setEvaluationLanguage(event.target.value)}
                  >
                    <option value="zh-CN">简体中文</option>
                    <option value="zh-TW">繁体中文</option>
                    <option value="en">英文</option>
                    <option value="mul">中英混合</option>
                  </select>
                </label>
              </>
            ) : null}
            <div className="evaluation-selection-summary" aria-live="polite">
              已标注 {Object.keys(evaluationJudgments).length} 个结果，其中 {Object.values(evaluationJudgments).filter((value) => value >= 2).length} 个具有回答价值。
            </div>
            <button
              className="button secondary"
              type="submit"
              disabled={Boolean(busy) || !testResult || testResult.testedQuery !== query.trim()}
            >
              <Plus size={15} />{evaluationTargetSetId ? "加入评估集" : "建立评估集"}
            </button>
          </form>
          <details className="search-evaluation-sets"><summary>索引评估与评估集管理</summary>
            <div className="evaluation-index-picker">
              <label>
                <span>运行所用索引</span>
                <select
                  name="evaluation_index_version"
                  value={effectiveEvaluationIndexId}
                  onChange={(event) => setEvaluationIndexId(event.target.value)}
                >
                  <option value="">选择候选或活动索引</option>
                  {data?.index_versions
                    .filter((version) => ["ready", "active", "retired"].includes(version.status))
                    .map((version) => (
                      <option value={version.id} key={version.id}>{version.uid} · {version.status}</option>
                    ))}
                </select>
              </label>
              <p>运行前会再次核对模型配置和实际文档数。当前混合检索权重为 {Math.round((data?.runtime.semantic_ratio ?? 0) * 100)}%。</p>
            </div>
            <div className="evaluation-set-list">
              {evaluationSets.map((evaluationSet) => (
                <article key={evaluationSet.id}>
                  <div>
                    <strong>{evaluationSet.name}</strong>
                    <span>{evaluationSet.language || "未指定语言"} · {evaluationSet.query_count} 条查询 · {evaluationSet.judgment_count} 条判断</span>
                    {evaluationSet.description ? <p>{evaluationSet.description}</p> : null}
                  </div>
                  <div>
                    <span className={evaluationSet.is_active ? "status" : "status warning"}>{evaluationSet.is_active ? "已启用" : "已停用"}</span>
                    <button
                      className="button secondary"
                      type="button"
                      disabled={Boolean(busy)}
                      onClick={() => void toggleEvaluationSet(evaluationSet)}
                    >
                      {evaluationSet.is_active ? "停用" : "启用"}
                    </button>
                    <button
                      className="button"
                      type="button"
                      disabled={Boolean(busy) || !evaluationSet.is_active || !effectiveEvaluationIndexId}
                      onClick={() => void runEvaluation(evaluationSet.id)}
                    >
                      <Play size={14} />预检并运行
                    </button>
                  </div>
                </article>
              ))}
              {!evaluationsLoaded ? (
                <p className="evaluation-empty">正在读取馆内评估集……</p>
              ) : evaluationError ? (
                <p className="evaluation-empty">评估集暂时无法读取，请先排查上方错误。</p>
              ) : !evaluationSets.length ? (
                <p className="evaluation-empty">还没有评估集。运行一次测试查询并标注结果后，可以在左侧建立第一组基线。</p>
              ) : null}
            </div>
          </details>
        </div>
        {evaluationMessage ? <p className="evaluation-message" role="status" aria-live="polite">{evaluationMessage}</p> : null}
        <details className="evaluation-run-history"><summary>最近运行</summary>
          <h3>最近运行</h3>
          <div className="admin-table-scroll">
            <table>
              <thead><tr><th>评估集</th><th>索引</th><th>状态</th><th>进度</th><th>Recall@20</th><th>nDCG@10</th><th>MRR</th><th>Precision@5</th><th>Top 5 有用结果</th><th>Top 3 直接回应</th><th>p95</th><th>时间</th></tr></thead>
              <tbody>
                {evaluationRuns.slice(0, 20).map((run) => (
                  <tr key={run.id}>
                    <td><strong>{run.evaluation_set_name}</strong>{run.error_message ? <small className="attempt-error">{run.error_message}</small> : null}</td>
                    <td className="evaluation-index-uid">{run.index_uid || "索引已移除"}</td>
                    <td>{evaluationStatusLabels[run.status] ?? run.status}</td>
                    <td>{run.completed_query_count} / {run.query_count}</td>
                    <td>{run.metrics.recall_at_20 === undefined ? "—" : `${Math.round(run.metrics.recall_at_20 * 100)}%`}</td>
                    <td>{run.metrics.ndcg_at_10 === undefined ? "—" : `${Math.round(run.metrics.ndcg_at_10 * 100)}%`}</td>
                    <td>{run.metrics.mrr === undefined ? "—" : `${Math.round(run.metrics.mrr * 100)}%`}</td>
                    <td>{run.metrics.precision_at_5 === undefined ? "—" : `${Math.round(run.metrics.precision_at_5 * 100)}%`}</td>
                    <td>{run.metrics.top5_useful_passage_rate === undefined ? "—" : `${Math.round(run.metrics.top5_useful_passage_rate * 100)}%`}</td>
                    <td>{run.metrics.top3_direct_response_rate === undefined ? "—" : `${Math.round(run.metrics.top3_direct_response_rate * 100)}%`}</td>
                    <td>{run.metrics.p95_latency_ms === undefined ? "—" : `${run.metrics.p95_latency_ms} ms`}</td>
                    <td>{new Intl.DateTimeFormat("zh-CN", { dateStyle: "short", timeStyle: "short" }).format(new Date(run.created_at))}</td>
                  </tr>
                ))}
                {!evaluationsLoaded ? <tr><td colSpan={12}>正在读取评估记录……</td></tr> : evaluationError ? <tr><td colSpan={12}>评估记录暂时无法读取。</td></tr> : !evaluationRuns.length ? <tr><td colSpan={12}>尚未运行检索评估。</td></tr> : null}
              </tbody>
            </table>
          </div>
        </details>
      </section>
}
    </>}
    </div><div>
    {surface==="index" ? <AdminPublicPreviewFrame title="搜索结果预览" src={previewQuery ? `/explore?mode=semantic&q=${encodeURIComponent(previewQuery)}` : null} emptyMessage="输入查询后检查当前公开搜索"><div className={styles.switcher}><button type="button" disabled title="缺少候选索引的交互预览接口">修改后</button><span>当前线上</span></div><form onSubmit={event=>{event.preventDefault();setPreviewQuery(query.trim());}}><label>查询<input value={query} onChange={event=>setQuery(event.target.value)}/></label><button className="button" disabled={!query.trim()}>搜索</button></form></AdminPublicPreviewFrame> : <section className={styles.results}><h2>本次查询结果</h2><p>以下判断对应测试接口返回的原文段落。候选索引需另行运行评估。</p>{testResult ? <><h3>“{testResult.testedQuery}”的搜索结果</h3><p>返回 {testResult.count} 条</p>{resultList}</> : <p>—</p>}</section>}
    </div></div>
    {surface==="evaluation" ? <footer className={styles.actions}><button className="button secondary" type="button" disabled={Boolean(busy) || step===1} onClick={()=>setStep(value=>value-1)}>上一步</button>{step<3 ? <button className="button" type="button" disabled={Boolean(busy) || !testResult} onClick={()=>setStep(3)}>保存本次评价</button> : null}<p role="status">{evaluationMessage}</p></footer> : null}
      <ConfirmDialog
        open={Boolean(activateTarget)}
        title="验证并切换生产语义索引"
        description="系统会再次核对本地模型、全部候选任务和 Meilisearch 实际文档数。只有全部一致时才移动生产指针。"
        confirmLabel="确认验证并切换"
        pending={busy === "activate_version"}
        details={[
          `候选索引 ${activateTarget?.uid || ""}`,
          `文档 ${activateTarget?.document_count || 0} / 预期 ${activateTarget?.expected_document_count || 0}`,
          "当前活动索引将保留为已停用版本，不会删除。",
          "正在 OCR 的馆藏完成后会写入新的活动索引。",
        ]}
        onCancel={() => setActivateTarget(null)}
        onConfirm={() => void activateVersion()}
      />
  </div>;
}
