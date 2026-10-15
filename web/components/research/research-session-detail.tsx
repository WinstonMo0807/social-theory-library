"use client";

import Link from "next/link";
import { ArrowRight, CircleAlert, LoaderCircle, RefreshCw, Search, Send, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { classifyClientError, getServerSessionCredential, isUnauthenticatedError } from "@/lib/api";
import {
  changeResearchSelection,
  listResearchTurns,
  readResearchRecord,
  retryResearchTurn,
  startResearchTurn,
  type ProjectData,
  type ResearchRecord,
  type ResolvedEvidence,
  type TurnData,
} from "@/lib/api/research.client";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { ResearchCenterNav } from "./research-center-nav";

type LoadState = "loading" | "ready" | "error";

const statusLabel: Record<string, string> = {
  completed: "已完成", complete: "已完成", running: "处理中", queued: "排队中",
  partial: "部分完成", failed: "处理失败", canceled: "已取消", cancelled: "已取消",
};

function recordStatus(record: ResearchRecord | null) {
  const status = String(record?.status || record?.state || "saved").toLowerCase();
  return statusLabel[status] || "已保存";
}

function evidenceTitle(reference: ResolvedEvidence, index: number) {
  return reference.title?.trim() || `原文证据 ${index + 1}`;
}

function evidenceLocation(reference: ResolvedEvidence) {
  if (reference.pdf_page) return `PDF 第 ${reference.pdf_page} 页`;
  return reference.locator_precision === "span" ? "原文段落" : "原文定位";
}

export function ResearchSessionDetail({ id }: { id: string }) {
  const { state: session } = useSessionBootstrap();
  const [record, setRecord] = useState<ResearchRecord<ProjectData> | null>(null);
  const [turns, setTurns] = useState<ResearchRecord<TurnData>[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [question, setQuestion] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [actionPending, setActionPending] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    const credential = getServerSessionCredential();
    if (!credential) throw new Error("登录状态只能在浏览器中验证，请重新打开此页面。");
    const [project, turnPage] = await Promise.all([
      readResearchRecord<ProjectData>("research-projects", id, signal),
      listResearchTurns(id, 1, signal),
    ]);
    return { project, turnRows: turnPage.results };
  }, [id]);

  useEffect(() => {
    if (session.status === "unauthenticated") {
      window.location.replace(`/login?next=${encodeURIComponent(`/account/research/${id}`)}`);
      return;
    }
    if (session.status !== "authenticated") return;
    const controller = new AbortController();
    Promise.resolve().then(() => {
      if (controller.signal.aborted) return;
      setLoadState("loading");
      setError("");
    });
    load(controller.signal)
      .then(({ project, turnRows }) => {
        if (controller.signal.aborted) return;
        setRecord(project);
        setTurns(turnRows);
        setLoadState("ready");
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        if (isUnauthenticatedError(reason)) {
          window.location.replace(`/login?next=${encodeURIComponent(`/account/research/${id}`)}`);
          return;
        }
        const category = classifyClientError(reason);
        setError(category === "auth_403" ? "当前账户没有访问这个研究会话的权限。" : reason instanceof Error ? reason.message : "研究会话暂时无法加载，请稍后重试。");
        setLoadState("error");
      });
    return () => controller.abort();
  }, [attempt, id, load, session.status]);

  const currentTurn = turns[turns.length - 1] ?? null;
  const selected = record?.data.selections ?? [];
  const candidates = useMemo(() => {
    const refs = currentTurn?.data.result_refs ?? [];
    return refs.filter((reference, index) => refs.findIndex((candidate) => `${candidate.asset_id}:${candidate.pdf_page}` === `${reference.asset_id}:${reference.pdf_page}`) === index).slice(0, 12);
  }, [currentTurn]);
  const activeStatus = String(currentTurn?.status || record?.status || "saved").toLowerCase();

  async function addSelection(reference: ResolvedEvidence) {
    if (!record || actionPending) return;
    setActionPending(true);
    setActionMessage("");
    try {
      const next = await changeResearchSelection(record.id, {
        expected_revision: record.revision,
        action: "add",
        references: [{ asset_id: reference.asset_id, document_revision_id: reference.document_revision_id, pdf_page: reference.pdf_page, evidence_span_id: reference.evidence_span_id }],
      });
      setRecord(next);
      setActionMessage("已加入当前选材。来源身份和版本已重新核对。");
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : "加入选材失败，请重试。");
    } finally {
      setActionPending(false);
    }
  }

  async function removeSelection(reference: ResolvedEvidence) {
    if (!record || actionPending) return;
    const referenceId = reference.reference_id || `${reference.asset_id}:${reference.pdf_page}`;
    setActionPending(true);
    setActionMessage("");
    try {
      const next = await changeResearchSelection(record.id, { expected_revision: record.revision, action: "remove", reference_id: referenceId });
      setRecord(next);
      setActionMessage("已从当前选材移除。");
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : "移除选材失败，请重试。");
    } finally {
      setActionPending(false);
    }
  }

  async function submitQuestion(event: FormEvent) {
    event.preventDefault();
    if (!record || question.trim().length < 2 || actionPending) return;
    setActionPending(true);
    setActionMessage("");
    try {
      const nextTurn = await startResearchTurn(record.id, { request_id: crypto.randomUUID(), expected_revision: record.revision, question: question.trim(), mode: "search" });
      setTurns((current) => [...current, nextTurn]);
      setQuestion("");
      setActionMessage("新的研究轮次已加入队列；完成后会自动保留在本会话中。");
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : "无法开始新的研究轮次，请稍后重试。");
    } finally {
      setActionPending(false);
    }
  }

  async function retryTurn() {
    if (!record || !currentTurn || actionPending) return;
    setActionPending(true);
    setActionMessage("");
    try {
      const nextTurn = await retryResearchTurn(currentTurn.id, { request_id: crypto.randomUUID(), expected_revision: currentTurn.revision });
      setTurns((current) => [...current, nextTurn]);
      setActionMessage("已重新排入这一轮研究；完成后会把新的来源写回本会话。");
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : "研究轮次重试失败，请稍后再试。");
    } finally {
      setActionPending(false);
    }
  }

  if (session.status === "loading" || session.status === "unknown" || loadState === "loading") {
    return <DetailFrame><div className="stl4-research-state" role="status"><LoaderCircle className="stl4-spin" size={22} /><p>正在读取研究会话……</p></div></DetailFrame>;
  }
  if (error || session.status === "forbidden" || loadState === "error" || !record) {
    return <DetailFrame><div className="stl4-research-state stl4-research-state-error" role="alert"><CircleAlert size={24} /><h2>研究会话暂时不可用</h2><p>{session.message || error || "研究会话不存在或已无法访问。"}</p><button type="button" onClick={() => setAttempt((value) => value + 1)}><RefreshCw size={15} />重试</button></div></DetailFrame>;
  }

  const title = record.data.title?.trim() || "未命名研究";
  const questionText = record.data.question?.trim() || "尚未填写研究问题。";
  return <DetailFrame>
    <nav className="stl4-research-breadcrumb" aria-label="面包屑"><Link href="/">首页</Link><span>/</span><Link href="/account">读者中心</Link><span>/</span><Link href="/account/research">我的研究</Link><span>/</span><strong>持续研究</strong></nav>
    <header className="stl4-research-heading stl4-research-workspace-heading"><h1>{title}</h1><p>{questionText}</p><span className="stl4-research-privacy">仅本人可见 · {recordStatus(record)}</span></header>
    <section className="stl4-research-workspace" aria-label="持续研究工作区">
      <ResearchCenterNav active="research" />
      <div className={`stl4-research-status-panel status-${activeStatus}`} role={activeStatus === "failed" ? "alert" : "status"}>
        <div><strong>{statusLabel[activeStatus] || "已保存"}</strong><span>{currentTurn?.error_code ? `错误标识：${currentTurn.error_code}` : activeStatus === "queued" ? "已进入队列，等待可用的检索资源。" : activeStatus === "running" ? "正在核对来源、版本和页码，结果会自动回到这一轮。" : activeStatus === "partial" ? "本轮只完成了部分来源核对，可以继续提问或补充范围。" : activeStatus === "failed" ? "本轮没有完成，已保留问题和研究范围。" : activeStatus === "canceled" || activeStatus === "cancelled" ? "本轮已取消，原有选材仍保留在当前会话。" : "当前轮次的来源已经可以继续核对。"}</span></div>
        {currentTurn && (activeStatus === "failed" || activeStatus === "canceled" || activeStatus === "cancelled") ? <button type="button" onClick={() => void retryTurn()} disabled={actionPending}><RefreshCw size={14} />重新检索</button> : null}
      </div>
      <div className="stl4-research-workspace-grid">
        <aside className="stl4-research-turns" aria-label="研究轮次"><header><h2>研究轮次</h2><span>{turns.length}</span></header>{turns.length ? <ol>{turns.map((turn, index) => <li className={turn.id === currentTurn?.id ? "is-active" : undefined} key={turn.id}><span>{index + 1}</span><div><strong>{turn.data.question || "未命名问题"}</strong><small>{statusLabel[turn.status || ""] || turn.status || "已保存"}</small></div></li>)}</ol> : <p>还没有研究轮次。</p>}<button type="button" className="stl4-research-secondary" onClick={() => setQuestion("")}><span>＋</span> 新建分支</button></aside>
        <main className="stl4-research-results"><div className="stl4-research-results-head"><div><p className="stl4-research-kicker">研究问题</p><h2>{currentTurn?.data.question || questionText}</h2></div><Link href={`/account/research/${encodeURIComponent(id)}/compare`}>打开证据比较 <ArrowRight size={14} /></Link></div><div className="stl4-research-filter-row"><span><Search size={14} /> 证据片段（{candidates.length}）</span><span>来源按当前公开版本重新核对</span></div>{candidates.length ? <div className="stl4-research-evidence-list">{candidates.map((reference, index) => <article className="stl4-research-evidence" key={`${reference.asset_id}-${reference.pdf_page}-${index}`}><div className="stl4-evidence-number">{String(index + 1).padStart(2, "0")}</div><div className="stl4-evidence-copy"><h3>{evidenceTitle(reference, index)}</h3><p>{reference.quote || "当前只返回原文身份，正文将在打开 Reader 时重新读取。"}</p><small>{evidenceLocation(reference)} · {reference.source_status === "available" ? "可定位" : "来源暂不可用"}</small></div><div className="stl4-evidence-actions">{reference.reader_url && reference.source_status === "available" ? <Link href={reference.reader_url}>查看原文 <ArrowRight size={14} /></Link> : null}{selected.some((item) => item.reference_id === reference.reference_id || (item.asset_id === reference.asset_id && item.pdf_page === reference.pdf_page)) ? <span className="is-selected">已在选材</span> : <button type="button" onClick={() => void addSelection(reference)} disabled={actionPending}>加入选材</button>}</div></article>)}</div> : <div className="stl4-research-empty"><Search size={24} /><h2>{activeStatus === "queued" || activeStatus === "running" ? "研究正在进行" : "还没有可展示的证据"}</h2><p>{activeStatus === "queued" || activeStatus === "running" ? "完成后会把来源、页码和定位写入本会话。" : "从下方继续提问，或回到观点检索开始新的研究。"}</p></div>}{actionMessage ? <p className="stl4-research-action-message" role="status">{actionMessage}</p> : null}</main>
        <aside className="stl4-research-selected" aria-label="当前选材"><header><h2>当前选材</h2><span>{selected.length}</span></header>{selected.length ? <ol>{selected.map((reference, index) => <li key={`${reference.asset_id}-${reference.pdf_page}-${index}`}><div><strong>{evidenceTitle(reference, index)}</strong><small>{evidenceLocation(reference)}</small></div><button type="button" aria-label={`移除${evidenceTitle(reference, index)}`} onClick={() => void removeSelection(reference)} disabled={actionPending}><X size={14} /></button></li>)}</ol> : <p>选择证据后会出现在这里。</p>}<Link className="stl4-research-secondary" href={`/account/research/${encodeURIComponent(id)}/compare`}>查看选材比较 <ArrowRight size={14} /></Link></aside>
      </div>
      <form className="stl4-research-prompt" onSubmit={submitQuestion}><label htmlFor="research-follow-up">继续提问</label><div><input id="research-follow-up" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="基于当前选材继续追问……" minLength={2} maxLength={1200} /><button type="submit" disabled={actionPending || question.trim().length < 2}>{actionPending ? <LoaderCircle className="stl4-spin" size={15} /> : <Send size={15} />}<span>发送</span></button></div></form>
    </section>
  </DetailFrame>;
}

function DetailFrame({ children }: { children: React.ReactNode }) {
  return <div className="stl4-research-page"><div className="stl4-research-detail-shell">{children}</div><p className="stl4-research-footnote">/account/research/[id]　·　私人内容</p></div>;
}
