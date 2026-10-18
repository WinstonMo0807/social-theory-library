"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, CircleAlert, LoaderCircle, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { classifyClientError, getServerSessionCredential, isUnauthenticatedError, subscribeToSessionChanges, type ClientErrorCategory } from "@/lib/api";
import { readAllPages } from "@/lib/api/read-all-pages";
import type { ProjectData, ResearchRecord } from "@/lib/api/research.client";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { ResearchCenterNav } from "./research-center-nav";

type LoadState = "idle" | "loading" | "ready" | "error";

const statusMeta: Record<string, { label: string; tone: "success" | "working" | "warning" | "danger" | "neutral" }> = {
  completed: { label: "已完成", tone: "success" },
  complete: { label: "已完成", tone: "success" },
  running: { label: "处理中", tone: "working" },
  queued: { label: "处理中", tone: "working" },
  partial: { label: "部分完成", tone: "warning" },
  failed: { label: "处理失败", tone: "danger" },
  canceled: { label: "已取消", tone: "neutral" },
  cancelled: { label: "已取消", tone: "neutral" },
};

function displayStatus(record: ResearchRecord<ProjectData>) {
  const key = String(record.status || record.state || "saved").toLowerCase();
  return statusMeta[key] ?? { label: "已保存", tone: "neutral" as const };
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "更新时间未知";
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  if (day === today) return "今天";
  if (day === today - 86_400_000) return "昨天";
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
}

function errorMessage(reason: unknown) {
  const category: ClientErrorCategory = classifyClientError(reason);
  if (category === "auth_403") return "当前账户没有访问研究会话的权限。";
  if (category === "network_error") return "研究会话暂时无法加载，请检查连接后重试。";
  return reason instanceof Error ? reason.message : "研究会话暂时无法加载，请稍后重试。";
}

export function ResearchSessionList() {
  const { state: session, retry: retrySession } = useSessionBootstrap();
  const [snapshot, setSnapshot] = useState<{ owner: number; rows: ResearchRecord<ProjectData>[] } | null>(null);
  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState("");
  const lastReadAt = useRef(0);
  const epoch = useRef(0);
  const ownerId = session.user?.id;

  const clearPrivateState = useCallback(() => {
    epoch.current += 1;
    setSnapshot(null);
    setState("idle");
    setError("");
    lastReadAt.current = 0;
  }, []);

  useEffect(() => subscribeToSessionChanges(clearPrivateState), [clearPrivateState]);

  useEffect(() => {
    const controller = new AbortController();
    const generation = ++epoch.current;
    const current = () => !controller.signal.aborted && generation === epoch.current;
    const cleanup = () => { controller.abort(); epoch.current += 1; };
    if (session.status === "unauthenticated") {
      window.location.replace("/login?next=/account/research");
    }
    if (session.status !== "authenticated" || ownerId === undefined) {
      Promise.resolve().then(() => { if (current()) { setSnapshot(null); setState("idle"); setError(""); } });
      return cleanup;
    }
    const credential = getServerSessionCredential();
    if (!credential) {
      Promise.resolve().then(() => {
        if (!current()) return;
        setSnapshot(null);
        setState("error");
        setError("登录状态只能在浏览器中验证，请重新打开此页面。");
      });
      return cleanup;
    }
    Promise.resolve().then(() => {
      if (!current()) return;
      setSnapshot(null);
      setState("loading");
      setError("");
    });
    readAllPages<ResearchRecord<ProjectData>>("/reading/research-projects/", credential, controller.signal)
      .then((nextRows) => {
        if (!current()) return;
        setSnapshot({ owner: ownerId, rows: nextRows.sort((left, right) => right.updated_at.localeCompare(left.updated_at)) });
        lastReadAt.current = Date.now();
        setState("ready");
      })
      .catch((reason: unknown) => {
        if (!current()) return;
        setSnapshot(null);
        setState("error");
        if (isUnauthenticatedError(reason)) {
          setError("登录已过期，请重新登录。");
          window.location.replace("/login?next=/account/research");
          return;
        }
        setError(errorMessage(reason));
      });
    return cleanup;
  }, [session.status, ownerId]);

  useEffect(() => {
    const revalidate = () => {
      if (document.visibilityState !== "visible" || session.status !== "authenticated" || Date.now() - lastReadAt.current < 30_000) return;
      // Revalidate the cookie owner before attaching newly fetched private rows.
      clearPrivateState();
      lastReadAt.current = Date.now();
      retrySession();
    };
    window.addEventListener("focus", revalidate);
    window.addEventListener("pageshow", revalidate);
    document.addEventListener("visibilitychange", revalidate);
    return () => {
      window.removeEventListener("focus", revalidate);
      window.removeEventListener("pageshow", revalidate);
      document.removeEventListener("visibilitychange", revalidate);
    };
  }, [session.status, clearPrivateState, retrySession]);

  const retry = () => { clearPrivateState(); retrySession(); };

  if (session.status === "forbidden" || session.status === "temporary_error" || (session.status === "authenticated" && state === "error")) {
    return <ResearchPageFrame><div className="stl4-research-state stl4-research-state-error" role="alert"><CircleAlert size={24} /><h2>研究会话暂时不可用</h2><p>{session.message || error || "登录状态暂时无法验证，请重试。"}</p><button type="button" onClick={retry}><RefreshCw size={15} />重试</button></div></ResearchPageFrame>;
  }

  if (session.status !== "authenticated" || state !== "ready" || !snapshot || snapshot.owner !== ownerId) {
    return <ResearchPageFrame><div className="stl4-research-state" role="status"><LoaderCircle className="stl4-spin" size={22} /><p>{session.status === "unauthenticated" ? "正在前往登录页面……" : "正在读取你的研究会话……"}</p></div></ResearchPageFrame>;
  }

  const rows = snapshot.rows;
  const countLabel = `${rows.length} 个会话`;
  return <ResearchPageFrame>
    <section className="stl4-research-main" aria-labelledby="research-title">
      <nav className="stl4-research-breadcrumb" aria-label="面包屑"><Link href="/">首页</Link><span>/</span><Link href="/account">读者中心</Link><span>/</span><strong>研究会话</strong></nav>
      <header className="stl4-research-heading"><h1 id="research-title">研究会话</h1><p>只显示你自己的阅读和研究内容。</p></header>
      <div className="stl4-research-panel">
        <ResearchCenterNav active="research" counts={{ research: rows.length }} />
        <div className="stl4-research-panel-head"><div><h2>最近研究</h2><p>{countLabel}</p></div><Link href="/explore/opinions">开始新的研究 <ArrowRight size={15} /></Link></div>
        {rows.length ? <div className="stl4-research-list">{rows.map((record) => <ResearchSessionCard key={record.id} record={record} />)}</div> : <div className="stl4-research-empty"><BookOpen size={26} /><h2>还没有研究会话</h2><p>完成一次观点检索或保存一个研究问题后，会话会出现在这里。</p><Link href="/explore/opinions">去探索观点 <ArrowRight size={15} /></Link></div>}
      </div>
    </section>
  </ResearchPageFrame>;
}

function ResearchSessionCard({ record }: { record: ResearchRecord<ProjectData> }) {
  const meta = displayStatus(record);
  const title = record.data?.title?.trim() || "未命名研究";
  const question = record.data?.question?.trim();
  return <article className="stl4-research-card"><div className="stl4-research-card-copy"><h3>{title}</h3>{question && question !== title ? <p>{question}</p> : null}<time dateTime={record.updated_at}>{formatDate(record.updated_at)}</time></div><div className={`stl4-research-status is-${meta.tone}`}><i aria-hidden="true" /><span>{meta.label}</span></div><Link className="stl4-research-open" href={`/account/research/${encodeURIComponent(record.id)}`}>查看 <ArrowRight size={15} aria-hidden="true" /><span className="sr-only">{title}</span></Link></article>;
}

function ResearchPageFrame({ children }: { children: React.ReactNode }) {
  return <div className="stl4-research-page">{children}</div>;
}
