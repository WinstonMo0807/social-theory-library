"use client";

import Link from "next/link";
import { ArrowRight, CircleAlert, LoaderCircle, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { getServerSessionCredential, isUnauthenticatedError } from "@/lib/api";
import { readAllPages } from "@/lib/api/read-all-pages";
import type { ResearchRecord } from "@/lib/api/research.client";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { ResearchCenterNav, type ReaderCenterSection } from "./research-center-nav";

type CollectionKind = "notes" | "plans" | "citation" | "confirmed";
const config: Record<CollectionKind, { title: string; subtitle: string; endpoint: string; nav: ReaderCenterSection; empty: string }> = {
  notes: { title: "笔记", subtitle: "你保存的高亮、摘录和阅读笔记。", endpoint: "/reading/annotations/", nav: "notes", empty: "还没有保存笔记或批注。" },
  plans: { title: "阅读计划", subtitle: "按照你设定的目标和规则继续阅读。", endpoint: "/reading/reading-plans/", nav: "plans", empty: "还没有阅读计划。" },
  citation: { title: "引文核验", subtitle: "你的文稿体检任务和可追溯的原文核验记录。", endpoint: "/reading/citation-audits/", nav: "citation", empty: "还没有引文核验任务。" },
  confirmed: { title: "已确认笔记", subtitle: "只有你主动确认的内容才会进入个人学术记忆。", endpoint: "/reading/research-memories/", nav: "confirmed", empty: "还没有已确认笔记。" },
};

function rowTitle(row: ResearchRecord<Record<string, unknown>>, index: number) {
  const data = row.data || {};
  for (const key of ["title", "goal", "body", "question"]) {
    if (typeof data[key] === "string" && data[key].trim()) return data[key].trim();
  }
  return `未命名记录 ${index + 1}`;
}

export function ReaderCollectionList({ kind }: { kind: CollectionKind }) {
  const page = config[kind];
  const { state: session } = useSessionBootstrap();
  const [rows, setRows] = useState<ResearchRecord<Record<string, unknown>>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (session.status === "unauthenticated") { window.location.replace(`/login?next=/account/${kind === "citation" ? "citation-audits" : kind}`); return; }
    if (session.status !== "authenticated") return;
    const credential = getServerSessionCredential();
    if (!credential) { Promise.resolve().then(() => setError("登录状态只能在浏览器中验证，请重新打开此页面。")); return; }
    const controller = new AbortController();
    Promise.resolve().then(() => { if (!controller.signal.aborted) { setRows([]); setError(""); setLoading(true); } });
    readAllPages<ResearchRecord<Record<string, unknown>>>(page.endpoint, credential, controller.signal)
      .then((nextRows) => { if (!controller.signal.aborted) { setRows(nextRows); setLoading(false); } })
      .catch((reason: unknown) => { if (controller.signal.aborted) return; if (isUnauthenticatedError(reason)) { window.location.replace(`/login?next=/account/${kind}`); return; } setError(reason instanceof Error ? reason.message : "资料暂时无法加载，请稍后重试。"); setLoading(false); });
    return () => controller.abort();
  }, [attempt, kind, page.endpoint, session.status]);

  if (session.status === "loading" || session.status === "unknown" || loading) {
    return <CollectionFrame><div className="stl4-research-state" role="status"><LoaderCircle className="stl4-spin" size={22} /><p>正在读取{page.title}……</p></div></CollectionFrame>;
  }
  return <CollectionFrame><nav className="stl4-research-breadcrumb" aria-label="面包屑"><Link href="/">首页</Link><span>/</span><Link href="/account">读者中心</Link><span>/</span><strong>{page.title}</strong></nav><header className="stl4-research-heading"><h1>{page.title}</h1><p>{page.subtitle}</p></header><section className="stl4-research-panel"><ResearchCenterNav active={page.nav} />{error ? <div className="stl4-research-state stl4-research-state-error" role="alert"><CircleAlert size={22} /><p>{error}</p><button type="button" onClick={() => setAttempt((value) => value + 1)}><RefreshCw size={14} />重试</button></div> : rows.length ? <div className="stl4-research-list">{rows.map((row, index) => <article className="stl4-research-card" key={row.id}><div className="stl4-research-card-copy"><h3>{rowTitle(row, index)}</h3><time dateTime={row.updated_at}>{new Date(row.updated_at).toLocaleDateString("zh-CN")}</time></div><span className="stl4-research-status is-neutral"><i />{row.status || row.state || "已保存"}</span><Link className="stl4-research-open" href={kind === "plans" ? `/account/plans/${row.id}` : kind === "citation" ? `/account/citation-audits/${row.id}` : "/account"}>查看 <ArrowRight size={14} /></Link></article>)}</div> : <div className="stl4-research-empty"><h2>{page.empty}</h2><p>当前页面只显示属于你自己的资料。</p></div>}</section></CollectionFrame>;
}

function CollectionFrame({ children }: { children: React.ReactNode }) { return <div className="stl4-research-page"><div className="stl4-research-detail-shell">{children}</div><p className="stl4-research-footnote">读者中心　·　私人内容</p></div>; }
