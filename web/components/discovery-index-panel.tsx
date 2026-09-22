"use client";

import Link from "next/link";
import { Clock3, RefreshCw, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import styles from "./discovery-index-panel.module.css";

type IndexStage = { status: string; message: string; count?: number; completed_pages?: number; total_pages?: number };
type IndexDocument = {
  edition_id: string; title: string; asset_id: string; source_revision: string;
  readable: IndexStage; text: IndexStage; keyword: IndexStage; vector: IndexStage; knowledge: IndexStage;
  last_activity: string | null; job_id: string | null; retry_allowed: boolean; overdue: boolean; workbench_url?: string;
};
type IndexJob = { id: string; status: string; progress: number; error_message: string; created_at: string };
type DiscoveryIndexPayload = {
  active_generation: { id: string; index_uid: string; model: string; revision: string; artifact_id: string; created_at: string } | null;
  model: { ready: boolean; embedding_ready: boolean; reranker_ready: boolean; message: string };
  summary: { readable: number; text_ready: number; keyword_ready: number; vector_ready: number; knowledge_ready: number; waiting: number; failed: number };
  capabilities: { rebuild: boolean; retry: boolean };
  count: number; page: number; page_size: number; results: IndexDocument[]; jobs: IndexJob[]; warnings: Array<string | { message: string }>;
};

const endpoint = "/catalog/admin/discovery-index/";
const labels: Record<string, string> = {
  ready: "已就绪", completed: "已完成", succeeded: "已完成", active: "已生效", readable: "可阅读",
  pending: "等待处理", queued: "已排队", running: "处理中", processing: "处理中", building: "构建中",
  failed: "失败", partial: "部分完成", missing: "尚未建立", waiting: "等待处理", blocked: "受阻",
  unavailable: "不可用", stale: "等待更新", not_ready: "尚未就绪", not_started: "未开始", canceled: "已取消",
  withdrawn: "已撤回", private: "非公开", empty: "暂无内容", paused: "已暂停", unknown: "待确认",
};
const activeStatus = (value: string) => ["pending", "queued", "running", "processing", "building"].includes(value);
const timeLabel = (value: string | null) => value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "暂无记录";

export function DiscoveryIndexPanel({ revision = 0 }: { revision?: number }) {
  const [data, setData] = useState<DiscoveryIndexPayload | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [operation, setOperation] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const operationRef = useRef(false);
  const requestRef = useRef<AbortController | null>(null);
  const selected = data?.results.find(row => row.edition_id === selectedId);

  const load = useCallback(() => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    return apiRequest<DiscoveryIndexPayload>(`${endpoint}?page=${page}&page_size=15`, { signal: controller.signal, cache: "no-store" }, getServerSessionCredential()).then(next => {
      if (requestRef.current !== controller) return;
      setData(next); setError("");
    }).catch(reason => {
      if (requestRef.current !== controller) return;
      setError(controller.signal.aborted ? "读取检索覆盖超时，可重试读取。后台任务不会因此重新启动。" : reason instanceof Error ? reason.message : "无法读取检索覆盖。");
    }).finally(() => {
      window.clearTimeout(timeout);
      if (requestRef.current === controller) { requestRef.current = null; setLoading(false); }
    });
  }, [page]);

  useEffect(() => { void load(); return () => { requestRef.current?.abort(); requestRef.current = null; }; }, [load, revision]);
  const hasActiveJobs = data?.jobs.some(job => activeStatus(job.status)) ?? false;
  useEffect(() => {
    if (!hasActiveJobs || error) return;
    const timer = window.setInterval(() => {
      if (!operationRef.current && !requestRef.current && document.visibilityState === "visible") void load();
    }, 6000);
    return () => window.clearInterval(timer);
  }, [hasActiveJobs, load, error]);

  async function perform(action: "rebuild" | "retry", jobId?: string) {
    if (operationRef.current) return;
    operationRef.current = true; setOperation(jobId || action); setError(""); setMessage("");
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 25000);
    try {
      const response = await apiRequest<{ job_id?: string; id?: string; status: string; message: string }>(endpoint, { method: "POST", body: JSON.stringify({ action, ...(jobId ? { job_id: jobId } : {}) }), signal: controller.signal }, getServerSessionCredential());
      setMessage(response.message || "任务已排队；写入确认前不会标记索引完成。");
      await load();
    } catch (reason) {
      setError(controller.signal.aborted ? "提交响应超时。请先刷新任务状态，确认是否已排队后再重试。" : reason instanceof Error ? reason.message : "操作未完成。");
    } finally { window.clearTimeout(timeout); operationRef.current = false; setOperation(""); }
  }

  const canRebuild = data?.capabilities?.rebuild === true;
  const canRetry = data?.capabilities?.retry === true;
  const pages = data ? Math.max(1, Math.ceil(data.count / data.page_size)) : 1;
  return <section className={`admin-panel ${styles.panel}`} aria-labelledby="discovery-index-heading" aria-busy={loading || Boolean(operation)}>
    <header className={styles.header}><div><p className="eyebrow">观点检索 · 覆盖与增量更新</p><h2 id="discovery-index-heading">从可阅读，到可检索</h2><p>正文、关键词、向量与知识投影分别确认完成，保留正在使用的索引直到新版本写入成功。</p></div><div className="admin-action-row"><button className="button secondary" type="button" disabled={loading || Boolean(operation)} onClick={() => { setLoading(true); void load(); }}><RefreshCw size={14} />{loading ? "读取中" : "刷新覆盖"}</button>{canRebuild ? <button className="button" type="button" disabled={Boolean(operation) || hasActiveJobs} onClick={() => void perform("rebuild")}>{operation === "rebuild" ? "正在提交" : "建立新索引版本"}</button> : null}</div></header>
    {error ? <p role="alert" className={styles.error}>{error}</p> : null}
    {message ? <p role="status" className={styles.notice}>{message}</p> : null}
    {data?.warnings?.map((warning, index) => <p className={styles.notice} key={index}>{typeof warning === "string" ? warning : warning.message}</p>)}
    <div className={styles.metrics}>{([ ["readable", "可阅读"], ["text_ready", "正文就绪"], ["keyword_ready", "关键词就绪"], ["vector_ready", "向量就绪"], ["knowledge_ready", "知识投影"], ["waiting", "等待更新"], ["failed", "失败"] ] as const).map(([key, label]) => <div key={key}><span>{label}</span><strong>{data?.summary[key] ?? "—"}</strong></div>)}</div>
    <div className={styles.model}><div><strong>本地编码</strong><span>{!data ? "未确认" : data.model.embedding_ready ? "就绪" : "未就绪"}</span></div><div><strong>本地重排</strong><span>{!data ? "未确认" : data.model.reranker_ready ? "就绪" : "未就绪"}</span></div><p>{data?.model.message || "正在读取本地推理状态。"}</p></div>
    <div className={styles.tableScroll}><table><caption className="sr-only">文献阅读和检索状态</caption><thead><tr><th>文献</th><th>阅读</th><th>正文 / OCR</th><th>关键词</th><th>向量</th><th>知识投影</th><th>操作</th></tr></thead><tbody>{data?.results.map(row => <tr key={row.edition_id}><td><strong>{row.title}</strong>{row.overdue ? <small className={styles.warning}><Clock3 size={12} />超过日常更新目标</small> : null}</td>{(["readable", "text", "keyword", "vector", "knowledge"] as const).map(stage => <td key={stage}><StageState stage={row[stage]} /></td>)}<td><button type="button" className="button secondary" onClick={() => setSelectedId(selectedId === row.edition_id ? "" : row.edition_id)}>{selectedId === row.edition_id ? "收起详情" : "查看详情"}</button></td></tr>)}</tbody></table></div>
    {!loading && data && !data.results.length ? <p className={styles.notice}>当前没有可展示的文献处理记录。</p> : null}
    {data ? <nav className="processing-pagination" aria-label="检索覆盖翻页"><span>共 {data.count} 份 · 第 {data.page} / {pages} 页</span><button type="button" disabled={loading || Boolean(operation) || page <= 1} onClick={() => { setSelectedId(""); setLoading(true); setPage(value => value - 1); }}>上一页</button><button type="button" disabled={loading || Boolean(operation) || page >= pages} onClick={() => { setSelectedId(""); setLoading(true); setPage(value => value + 1); }}>下一页</button></nav> : null}
    {selected ? <section className={styles.detail} aria-label="文献检索覆盖详情"><header><h3>{selected.title}</h3><button type="button" className="button secondary" onClick={() => setSelectedId("")}>关闭详情</button></header><dl>{([ ["readable", "阅读权限"], ["text", "文本与 OCR"], ["keyword", "关键词写入"], ["vector", "向量写入"], ["knowledge", "知识投影"] ] as const).map(([key, label]) => <div key={key}><dt>{label}</dt><dd><StageState stage={selected[key]} />{selected[key].message ? <p>{selected[key].message}</p> : null}</dd></div>)}<div><dt>当前正文修订</dt><dd>{selected.source_revision || "尚未建立"}</dd></div><div><dt>最近活动</dt><dd>{timeLabel(selected.last_activity)}</dd></div></dl><div className="admin-action-row">{selected.workbench_url?.startsWith("/") && !selected.workbench_url.startsWith("//") ? <Link className="button secondary" href={selected.workbench_url}>打开馆藏工作页</Link> : null}{canRetry && selected.retry_allowed && selected.job_id ? <button type="button" className="button" disabled={Boolean(operation)} onClick={() => void perform("retry", selected.job_id!)}><RotateCcw size={14} />{operation === selected.job_id ? "正在提交" : "重试失败索引"}</button> : null}</div></section> : null}
    {data?.jobs.length ? <details className={styles.jobs} open={hasActiveJobs}><summary>最近索引任务{hasActiveJobs ? " · 有任务进行中" : ""}</summary><div>{data.jobs.map(job => <article key={job.id}><div><strong>{labels[job.status] || job.status}</strong><span>{timeLabel(job.created_at)}</span>{activeStatus(job.status) ? <progress value={job.progress} max={100} aria-label="索引构建进度" /> : null}{job.error_message ? <p>{job.error_message}</p> : null}</div>{canRetry && job.status === "failed" ? <button type="button" className="button secondary" disabled={Boolean(operation)} onClick={() => void perform("retry", job.id)}>{operation === job.id ? "正在提交" : "重试"}</button> : null}</article>)}</div></details> : null}
    <details className={styles.generation}><summary>当前生效版本</summary>{data?.active_generation ? <dl><div><dt>建立时间</dt><dd>{timeLabel(data.active_generation.created_at)}</dd></div><div><dt>编码模型</dt><dd>{data.active_generation.model}</dd></div><div><dt>模型修订</dt><dd>{data.active_generation.revision}</dd></div><div><dt>构建标识</dt><dd>{data.active_generation.artifact_id}</dd></div><div><dt>索引版本</dt><dd>{data.active_generation.id}</dd></div></dl> : <p>尚未确认有效的观点检索索引。可阅读不代表已经完成全文或向量检索。</p>}</details>
  </section>;
}

function StageState({ stage }: { stage: IndexStage | undefined }) {
  if (!stage) return <span className="muted">未确认</span>;
  return <><span className={`${styles.state} ${["failed", "blocked", "partial", "unavailable"].includes(stage.status) ? styles.warning : ""}`}>{labels[stage.status] || stage.status}</span>{typeof stage.completed_pages === "number" && typeof stage.total_pages === "number" ? <small>{stage.completed_pages} / {stage.total_pages} 页</small> : typeof stage.count === "number" ? <small>{stage.count} 项</small> : null}</>;
}
