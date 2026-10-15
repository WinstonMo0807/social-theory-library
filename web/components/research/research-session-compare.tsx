"use client";

import Link from "next/link";
import { ArrowLeft, CircleAlert, LoaderCircle, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { classifyClientError, getServerSessionCredential, isUnauthenticatedError } from "@/lib/api";
import { readResearchRecord, type ComparisonCell, type ProjectData, type ResearchRecord } from "@/lib/api/research.client";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { ResearchCenterNav } from "./research-center-nav";

export function ResearchSessionCompare({ id }: { id: string }) {
  const { state: session } = useSessionBootstrap();
  const [record, setRecord] = useState<ResearchRecord<ProjectData> | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (session.status === "unauthenticated") {
      window.location.replace(`/login?next=${encodeURIComponent(`/account/research/${id}/compare`)}`);
      return;
    }
    if (session.status !== "authenticated") return;
    const controller = new AbortController();
    Promise.resolve().then(() => {
      if (controller.signal.aborted) return;
      setRecord(null);
      setError("");
    });
    const credential = getServerSessionCredential();
    if (!credential) {
      Promise.resolve().then(() => setError("登录状态只能在浏览器中验证，请重新打开此页面。"));
      return () => controller.abort();
    }
    readResearchRecord<ProjectData>("research-projects", id, controller.signal)
      .then((nextRecord) => { if (!controller.signal.aborted) setRecord(nextRecord); })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        if (isUnauthenticatedError(reason)) {
          window.location.replace(`/login?next=${encodeURIComponent(`/account/research/${id}/compare`)}`);
          return;
        }
        const category = classifyClientError(reason);
        setError(category === "auth_403" ? "当前账户没有访问这个研究会话的权限。" : reason instanceof Error ? reason.message : "比较资料暂时无法加载，请稍后重试。");
      });
    return () => controller.abort();
  }, [attempt, id, session.status]);

  if (session.status === "loading" || session.status === "unknown" || !record && !error) {
    return <CompareFrame><div className="stl4-research-state" role="status"><LoaderCircle className="stl4-spin" size={22} /><p>正在读取证据比较……</p></div></CompareFrame>;
  }
  if (error || session.status === "forbidden") {
    return <CompareFrame><div className="stl4-research-state stl4-research-state-error" role="alert"><CircleAlert size={24} /><h2>证据比较暂时不可用</h2><p>{session.message || error}</p><button type="button" onClick={() => setAttempt((value) => value + 1)}><RefreshCw size={15} />重试</button></div></CompareFrame>;
  }

  const comparison = record?.data.comparison;
  const dimensions = comparison?.dimensions ?? [];
  const cells = comparison?.cells ?? [];
  return <CompareFrame>
    <nav className="stl4-research-breadcrumb" aria-label="面包屑"><Link href="/">首页</Link><span>/</span><Link href="/account">读者中心</Link><span>/</span><Link href={`/account/research/${encodeURIComponent(id)}`}>持续研究</Link><span>/</span><strong>证据比较</strong></nav>
    <header className="stl4-research-heading"><h1>选材比较与证据矩阵</h1><p>只比较当前研究会话中由你选择的来源。</p></header>
    <section className="stl4-research-workspace stl4-research-compare-surface"><ResearchCenterNav active="research" /><div className="stl4-research-compare-head"><div><p className="stl4-research-kicker">当前研究</p><h2>{record?.data.title || "未命名研究"}</h2></div><Link href={`/account/research/${encodeURIComponent(id)}`}><ArrowLeft size={14} />返回工作区</Link></div>{dimensions.length && cells.length ? <div className="stl4-research-matrix" role="table" aria-label="证据比较矩阵"><div className="stl4-research-matrix-row is-head" role="row"><div role="columnheader">研究维度</div>{dimensions.map((dimension) => <div role="columnheader" key={dimension}>{dimension}</div>)}</div>{cells.map((cell: ComparisonCell, index) => <div className="stl4-research-matrix-row" role="row" key={`${cell.dimension}-${index}`}><div role="rowheader">{cell.dimension}</div>{dimensions.map((dimension) => <div role="cell" key={dimension}>{cell.note && dimension === cell.dimension ? cell.note : cell.reference_ids?.length ? `${cell.reference_ids.length} 条证据` : "暂无已确认证据"}</div>)}</div>)}</div> : <div className="stl4-research-empty"><h2>还没有比较维度</h2><p>在工作区选择来源后，比较维度和证据矩阵会保存在当前研究会话中。</p><Link className="stl4-research-secondary" href={`/account/research/${encodeURIComponent(id)}`}>返回工作区</Link></div>}</section>
  </CompareFrame>;
}

function CompareFrame({ children }: { children: React.ReactNode }) {
  return <div className="stl4-research-page"><div className="stl4-research-detail-shell">{children}</div><p className="stl4-research-footnote">/account/research/[id]/compare　·　私人内容</p></div>;
}
