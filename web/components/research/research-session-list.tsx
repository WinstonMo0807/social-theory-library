"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, CircleAlert, LoaderCircle, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { classifyClientError, getServerSessionCredential, isUnauthenticatedError, type ClientErrorCategory } from "@/lib/api";
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
  const { state: session } = useSessionBootstrap();
  const [rows, setRows] = useState<ResearchRecord<ProjectData>[]>([]);
  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (session.status === "unauthenticated") {
      window.location.replace("/login?next=/account/research");
      return;
    }
    if (session.status !== "authenticated" || !session.user) return;
    const credential = getServerSessionCredential();
    if (!credential) {
      Promise.resolve().then(() => {
        setState("error");
        setError("登录状态只能在浏览器中验证，请重新打开此页面。 ");
      });
      return;
    }
    const controller = new AbortController();
    Promise.resolve().then(() => {
      if (controller.signal.aborted) return;
      setState("loading");
      setError("");
    });
    readAllPages<ResearchRecord<ProjectData>>("/reading/research-projects/", credential, controller.signal)
      .then((nextRows) => {
        if (controller.signal.aborted) return;
        setRows(nextRows.sort((left, right) => right.updated_at.localeCompare(left.updated_at)));
        setState("ready");
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        if (isUnauthenticatedError(reason)) {
          window.location.replace("/login?next=/account/research");
          return;
        }
        setState("error");
        setError(errorMessage(reason));
      });
    return () => controller.abort();
  }, [attempt, session.status, session.user]);

  const countLabel = useMemo(() => `${rows.length} 个会话`, [rows.length]);

  if (session.status === "loading" || session.status === "unknown" || state === "idle" || state === "loading") {
    return <ResearchPageFrame><div className="stl4-research-state" role="status"><LoaderCircle className="stl4-spin" size={22} /><p>正在读取你的研究会话……</p></div></ResearchPageFrame>;
  }

  if (session.status === "forbidden" || state === "error") {
    return <ResearchPageFrame><div className="stl4-research-state stl4-research-state-error" role="alert"><CircleAlert size={24} /><h2>研究会话暂时不可用</h2><p>{session.message || error}</p><button type="button" onClick={() => setAttempt((value) => value + 1)}><RefreshCw size={15} />重试</button></div></ResearchPageFrame>;
  }

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
  return <div className="stl4-research-page">{children}<p className="stl4-research-footnote">/account/research　·　私人内容</p></div>;
}
