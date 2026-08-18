"use client";

import { BarChart3, Pause, Play, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

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

export function SemanticIndexAdmin() {
  const [data, setData] = useState<IndexPayload | null>(null);
  const [dataLoaded, setDataLoaded] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [query, setQuery] = useState("");
  const [testResult, setTestResult] = useState<TestPayload | null>(null);
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

  async function runAction(action: string, assetId?: string | null) {
    const token = getServerSessionCredential();
    if (!token) return;
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
      setBusy("");
    }
  }

  async function testQuery(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token || query.trim().length < 2) return;
    setBusy("test");
    setError("");
    setTestResult(null);
    setEvaluationJudgments({});
    try {
      setTestResult(await apiRequest<TestPayload>("/catalog/admin/semantic-index/test-query/", {
        method: "POST",
        body: JSON.stringify({ query: query.trim() }),
      }, token));
    } catch (reason) {
      setTestResult(null);
      setError(reason instanceof Error ? reason.message : "测试查询失败。");
    } finally {
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
    if (!token || !testResult || !query.trim()) return;
    if (!judgments.some((judgment) => judgment.relevance >= 2)) {
      setEvaluationMessage("至少要把一个结果标为具有证据价值或直接回应。");
      return;
    }
    if (!evaluationTargetSetId && !evaluationName.trim()) {
      setEvaluationMessage("新建评估集时需要填写名称。");
      return;
    }
    setBusy("save_evaluation_query");
    setEvaluationMessage("");
    try {
      if (evaluationTargetSetId) {
        await apiRequest(
          `/catalog/admin/search-evaluations/sets/${evaluationTargetSetId}/queries/`,
          {
            method: "POST",
            body: JSON.stringify({
              query_text: query.trim(),
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
            queries: [{ query_text: query.trim(), judgments }],
          }),
        }, token);
        setEvaluationMessage("评估集已建立。可以继续加入查询，或先运行一次基线评估。");
        setEvaluationName("");
        setEvaluationDescription("");
      }
      setEvaluationJudgments({});
      await refreshEvaluations();
    } catch (reason) {
      setEvaluationMessage(reason instanceof Error ? reason.message : "评估查询保存失败。");
    } finally {
      setBusy("");
    }
  }

  async function runEvaluation(evaluationSetId: string) {
    const token = getServerSessionCredential();
    if (!token || !effectiveEvaluationIndexId || !data) {
      setEvaluationMessage("请先选择一个候选或活动索引版本。");
      return;
    }
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
      setBusy("");
    }
  }

  async function toggleEvaluationSet(evaluationSet: EvaluationSetSummary) {
    const token = getServerSessionCredential();
    if (!token) return;
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
      setBusy("");
    }
  }

  async function activateVersion() {
    const token = getServerSessionCredential();
    if (!token || !activateTarget) return;
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
      setBusy("");
    }
  }

  return (
    <div className="admin-page">
      <header className="admin-page-title">
        <div><p>观点检索</p><h1>语义索引管理</h1><span>查看分块与向量进度，重试失败项目，并用真实查询检查排序。</span></div>
        <button className="button secondary" type="button" onClick={refresh} disabled={Boolean(busy)}><RefreshCw size={16} />刷新</button>
      </header>
      {error ? <p className="form-message error" role="alert">{error}</p> : null}
      <section className="metric-grid semantic-index-metrics">
        {[
          ["可处理文献", data?.documents.eligible],
          ["已建立索引", data?.documents.indexed],
          ["等待处理", data?.documents.pending],
          ["失败", data?.documents.failed],
        ].map(([label, value]) => <article className="metric-card" key={String(label)}><span>{label}</span><strong>{value ?? "—"}</strong></article>)}
      </section>
      <section className="admin-grid semantic-index-grid">
        <article className="admin-panel semantic-index-runtime">
          <header><h2>当前配置</h2><span className={data?.paused ? "status warning" : "status"}>{!data ? "加载中" : data.paused ? "已暂停" : "运行中"}</span></header>
          <dl>
            <div><dt>功能状态</dt><dd>{!data ? "加载中" : data.runtime.enabled ? "已启用" : "已关闭"}</dd></div>
            <div><dt>检索引擎</dt><dd>{data?.runtime.engine || "加载中"}</dd></div>
            <div><dt>Embedding</dt><dd>{data?.runtime.model || "加载中"}</dd></div>
            <div><dt>模型状态</dt><dd>{!data ? "加载中" : data.model_health.available === true ? "本地文件已就绪" : data.model_health.available === false ? "语义模型不可用" : "尚未完成运行验证"}</dd></div>
            <div><dt>混合检索权重</dt><dd>{data ? `${Math.round(data.runtime.semantic_ratio * 100)}%` : "加载中"}</dd></div>
            <div><dt>离线模式</dt><dd>{!data ? "加载中" : data.runtime.offline_mode ? "禁止运行时联网下载" : "允许联网"}</dd></div>
            <div><dt>Reranker</dt><dd>{data?.runtime.reranker || "规则回退"}</dd></div>
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
        <form className="admin-panel semantic-index-test" onSubmit={testQuery}>
          <header><h2>测试一条查询</h2></header>
          <label><span>观点或问题</span><textarea rows={4} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="例如：为什么农业现代化以后，农民反而更依赖组织？" /></label>
          <button className="button" type="submit" disabled={busy === "test" || query.trim().length < 2} aria-busy={busy === "test"}><Search size={15} />{busy === "test" ? "正在测试" : "运行测试"}</button>
          {testResult ? <p className="semantic-index-test-summary">返回 {testResult.count} 条 · {testResult.timing_ms ?? "未记录"} ms · {testResult.fallback_used || testResult.engine === "keyword_fallback" ? "服务端确认使用关键词检索" : testResult.engine === "hybrid" ? "服务端确认完成混合检索" : "服务端已完成查询"}{testResult.effective_configuration?.semantic_ratio === undefined ? " · 混合检索权重未返回" : ` · 实际混合检索权重 ${Math.round(testResult.effective_configuration.semantic_ratio * 100)}%`}</p> : null}
          {testResult?.comparison ? <dl className="ocr-runtime-status"><div><dt>关键词结果</dt><dd>{testResult.comparison.keyword_results.length} 条 · {testResult.comparison.latency_ms.keyword ?? "—"} ms</dd></div><div><dt>语义结果</dt><dd>{testResult.comparison.semantic_results.length} 条 · {testResult.comparison.latency_ms.semantic ?? "—"} ms</dd></div><div><dt>最终结果</dt><dd>{testResult.comparison.final_results.length} 条 · {testResult.comparison.latency_ms.final ?? "—"} ms</dd></div></dl> : null}
          <div className="semantic-index-test-results">
            {testResult?.results.slice(0, 10).map((item, index) => (
              <article key={item.id}>
                <strong>{item.relevance} · {item.title}</strong>
                <span>{item.printed_label ? `引用第 ${item.printed_label} 页 · ` : ""}PDF 第 {item.page_index} 页</span>
                <p>{item.snippet}</p>
                <label className="evaluation-relevance-field">
                  <span>评估相关性</span>
                  <select
                    name={`evaluation_relevance_${index}`}
                    value={evaluationJudgments[item.id] ?? ""}
                    onChange={(event) => {
                      const value = event.target.value;
                      setEvaluationJudgments((current) => {
                        if (value === "") {
                          const next = { ...current };
                          delete next[item.id];
                          return next;
                        }
                        return { ...current, [item.id]: Number(value) };
                      });
                    }}
                  >
                    <option value="">不纳入标注</option>
                    <option value="0">不相关</option>
                    <option value="1">同主题但未回应</option>
                    <option value="2">具有实质证据价值</option>
                    <option value="3">直接回应问题</option>
                  </select>
                </label>
              </article>
            ))}
          </div>
        </form>
      </section>
      <section className="admin-panel semantic-job-list">
        <header><h2>索引版本</h2><span>新版本完整验证后才切换生产指针</span></header>
        <div className="admin-table-scroll"><table><thead><tr><th>索引</th><th>模型</th><th>revision</th><th>维度</th><th>文档</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead><tbody>
          {data?.index_versions.map((version) => <tr key={version.id}><td><strong>{version.uid}</strong>{version.error ? <small className="attempt-error">{version.error}</small> : null}</td><td>{version.model_repo_id}</td><td>{version.model_revision}</td><td>{version.dimensions ?? "模型默认"}</td><td>{version.document_count}{version.expected_document_count ? ` / ${version.expected_document_count}` : ""}</td><td>{indexStatusLabels[version.status] ?? version.status}</td><td>{new Date(version.created_at).toLocaleString("zh-CN")}</td><td>{version.status === "ready" && data.permissions.can_manage ? <button type="button" disabled={Boolean(busy)} onClick={() => setActivateTarget(version)}>验证并切换</button> : version.status === "active" ? "当前生产" : "—"}</td></tr>)}
          {!dataLoaded ? <tr><td colSpan={8}>正在读取索引版本……</td></tr> : !data ? <tr><td colSpan={8}>索引版本暂时无法读取。</td></tr> : !data.index_versions.length ? <tr><td colSpan={8}>尚未建立版本化索引。</td></tr> : null}
        </tbody></table></div>
      </section>
      <section className="admin-panel search-evaluation-panel" aria-labelledby="search-evaluation-title">
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
            <p>先在上方运行真实查询，再给结果标注相关性。至少需要一个相关结果。</p>
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
              disabled={busy === "save_evaluation_query" || !testResult || !Object.keys(evaluationJudgments).length}
            >
              <Plus size={15} />{evaluationTargetSetId ? "加入评估集" : "建立评估集"}
            </button>
          </form>
          <div className="search-evaluation-sets">
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
          </div>
        </div>
        {evaluationMessage ? <p className="evaluation-message" role="status" aria-live="polite">{evaluationMessage}</p> : null}
        <div className="evaluation-run-history">
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
        </div>
      </section>
      <section className="admin-panel semantic-job-list">
        <header><h2>最近索引任务</h2><span>{data ? `${data.recent_jobs.length} 条` : "加载中"}</span></header>
        <div className="admin-table-scroll"><table><thead><tr><th>文献</th><th>操作</th><th>状态</th><th>进度</th><th>尝试</th><th>时间</th><th>操作</th></tr></thead><tbody>
          {data?.recent_jobs.map((job) => <tr key={job.id}><td><strong>{job.title || "全库任务"}</strong>{job.error ? <small className="attempt-error">{job.error}</small> : null}</td><td>{job.operation}</td><td>{jobStatusLabels[job.status] ?? job.status}</td><td>{job.progress}%</td><td>{job.attempts}</td><td>{new Date(job.created_at).toLocaleString("zh-CN")}</td><td>{job.asset_id && data.permissions.can_manage ? <button type="button" onClick={() => runAction("rebuild_asset", job.asset_id)}>单本重建</button> : null}</td></tr>)}
          {!dataLoaded ? <tr><td colSpan={7}>正在读取索引任务……</td></tr> : !data ? <tr><td colSpan={7}>索引任务暂时无法读取。</td></tr> : !data.recent_jobs.length ? <tr><td colSpan={7}>还没有语义索引任务。</td></tr> : null}
        </tbody></table></div>
      </section>
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
    </div>
  );
}
