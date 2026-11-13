"use client";
import { SourceText } from "@/components/source-text";


import Link from "next/link";
import { ArrowRight, CircleAlert, LoaderCircle, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { getServerSessionCredential, isUnauthenticatedError, subscribeToSessionChanges } from "@/lib/api";
import { readAllPages } from "@/lib/api/read-all-pages";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { researchReaderHref } from "@/lib/api/research-evidence";
import type { MemoryData, ResearchRecord } from "@/lib/api/research.client";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { ResearchCenterNav, type ReaderCenterSection } from "./research-center-nav";

type CollectionKind = "notes" | "confirmed";
const config: Record<CollectionKind, { title: string; subtitle: string; endpoint: string; route: string; nav: ReaderCenterSection; empty: string }> = {
  notes: { title: "笔记", subtitle: "你保存的高亮、摘录和阅读笔记。", endpoint: "/reading/annotations/", route: "/account/notes", nav: "notes", empty: "还没有保存笔记或批注。" },
  confirmed: { title: "已确认笔记", subtitle: "只有你主动确认的内容才会进入个人学术记忆。", endpoint: "/reading/research-memories/", route: "/account/confirmed-notes", nav: "confirmed", empty: "还没有已确认笔记。" },
};

type AnnotationRow = {
  id: string; asset?: string; work?: { title?: string }; kind: string; quote?: string; body_text?: string | null;
  selector?: { page_index?: number }; orphaned?: boolean; created_at: string; updated_at?: string;
};
type CollectionRow = {
  id: string; title: string; text?: string; quote?: string; updatedAt: string; status: string;
  href?: string; linkLabel?: string; summary?: string;
};

async function loadCollection(kind: CollectionKind, credential: string, signal: AbortSignal, owner: string): Promise<CollectionRow[]> {
  const endpoint = config[kind].endpoint;
  if (kind === "notes") {
    const rows = await readAllPages<AnnotationRow>(endpoint, credential, signal, owner);
    return rows.map((row) => {
      const page = row.selector?.page_index;
      const hasPage = Number.isInteger(page) && Number(page) > 0;
      const href = row.asset && hasPage && !row.orphaned
        ? `/reader/${encodeURIComponent(row.asset)}?page=${page}&focus=${encodeURIComponent(row.id)}`
        : row.asset && row.kind === "note" ? `/account/notes/${encodeURIComponent(row.asset)}#note-${encodeURIComponent(row.id)}` : undefined;
      return { id: row.id, title: row.work?.title?.trim() || "未命名文献", text: row.body_text?.trim() || undefined,
        quote: row.quote?.trim() || undefined, updatedAt: row.updated_at || row.created_at,
        status: row.orphaned ? "原文定位待核对" : row.kind === "note" ? "阅读笔记" : row.kind === "underline" ? "划线" : "高亮",
        href, linkLabel: hasPage && !row.orphaned ? "打开原页" : "查看笔记" };
    });
  }
  if (kind === "confirmed") {
    const rows = await readAllPages<ResearchRecord<MemoryData>>(endpoint, credential, signal, owner);
    // Filter after reading every page: a first page of suggestions is not an empty collection.
    return rows.filter(row => row.state === "confirmed").map((row) => {
      const source = row.data.sources?.find(reference => researchReaderHref(reference));
      const href = source ? researchReaderHref(source) : row.project_id ? `/account/research/${encodeURIComponent(row.project_id)}` : undefined;
      return { id: row.id, title: row.data.body?.trim() || "未填写正文的笔记", updatedAt: row.updated_at,
        status: "已确认", href, linkLabel: source ? "查看原文" : "返回研究" };
    });
  }
  return [];
}

export function ReaderCollectionList({ kind }: { kind: CollectionKind }) {
  const page = config[kind];
  const { state: session, retry: retrySession } = useSessionBootstrap();
  const ownerId = session.user?.id;
  const [snapshot, setSnapshot] = useState<{ key: string; rows: CollectionRow[] } | null>(null);
  const [error, setError] = useState("");
  const epoch = useRef(0);
  const lastReadAt = useRef(0);
  const key = `${ownerId}:${kind}`;
  const clearPrivateState = useCallback(() => {
    epoch.current += 1;
    setSnapshot(null); setError(""); lastReadAt.current = 0;
  }, []);
  useEffect(() => subscribeToSessionChanges(clearPrivateState), [clearPrivateState]);
  useEffect(() => {
    const controller = new AbortController();
    const generation = ++epoch.current;
    const current = () => !controller.signal.aborted && generation === epoch.current;
    const cleanup = () => { controller.abort(); epoch.current += 1; };
    Promise.resolve().then(() => { if (current()) { setSnapshot(null); setError(""); } });
    if (session.status === "unauthenticated") window.location.replace(`/login?next=${encodeURIComponent(page.route)}`);
    if (session.status !== "authenticated" || ownerId === undefined) return cleanup;
    const credential = getServerSessionCredential();
    if (!credential) {
      Promise.resolve().then(() => { if (current()) setError("登录状态只能在浏览器中验证，请重新打开此页面。"); });
      return cleanup;
    }
    withPrivateOwner(String(ownerId), () => loadCollection(kind, credential, controller.signal, String(ownerId)), controller.signal)
      .then(rows => { if (current()) { setSnapshot({ key, rows }); lastReadAt.current = Date.now(); } })
      .catch((reason: unknown) => {
        if (!current()) return;
        setSnapshot(null);
        setError(reason instanceof Error ? reason.message : "资料暂时无法加载，请稍后重试。");
        if (isUnauthenticatedError(reason)) window.location.replace(`/login?next=${encodeURIComponent(page.route)}`);
      });
    return cleanup;
  }, [kind, page.route, session.status, ownerId, key]);

  useEffect(() => {
    const revalidate = () => {
      if (document.visibilityState !== "visible" || session.status !== "authenticated" || Date.now() - lastReadAt.current < 30_000) return;
      clearPrivateState(); lastReadAt.current = Date.now(); retrySession();
    };
    window.addEventListener("focus", revalidate);
    window.addEventListener("pageshow", revalidate);
    document.addEventListener("visibilitychange", revalidate);
    return () => { window.removeEventListener("focus", revalidate); window.removeEventListener("pageshow", revalidate); document.removeEventListener("visibilitychange", revalidate); };
  }, [session.status, clearPrivateState, retrySession]);

  const retry = () => { clearPrivateState(); retrySession(); };
  if (session.status === "forbidden" || session.status === "temporary_error" || session.status === "authenticated" && error) {
    return <CollectionFrame><div className="stl4-research-state stl4-research-state-error" role="alert"><CircleAlert size={22} /><h2>{page.title}暂时不可用</h2><p>{session.message || error || "登录状态暂时无法验证，请重试。"}</p><button type="button" onClick={retry}><RefreshCw size={14} />重试</button></div></CollectionFrame>;
  }
  if (session.status !== "authenticated" || snapshot?.key !== key) {
    return <CollectionFrame><div className="stl4-research-state" role="status"><LoaderCircle className="stl4-spin" size={22} /><p>{session.status === "unauthenticated" ? "正在前往登录页面……" : `正在读取${page.title}……`}</p></div></CollectionFrame>;
  }
  const rows = snapshot.rows;
  return <CollectionFrame>
    <nav className="stl4-research-breadcrumb" aria-label="面包屑"><Link href="/home">首页</Link><span>/</span><Link href="/account">读者中心</Link><span>/</span><strong>{page.title}</strong></nav>
    <header className="stl4-research-heading"><h1>{page.title}</h1><p>{page.subtitle}</p></header>
    <section className="stl4-research-panel"><ResearchCenterNav active={page.nav} counts={{ [page.nav]: rows.length }} />
      {rows.length ? <div className="stl4-research-list">{rows.map(row => <article className="stl4-research-card" key={row.id}>
        <div className="stl4-research-card-copy"><h3>{row.title}</h3>{row.quote ? <blockquote><SourceText text={(row.quote) || ""} /></blockquote> : null}{row.text ? <p>{row.text}</p> : null}
          {row.summary ? <details data-disclosure="collection"><summary>查看任务记录</summary><p>{row.summary}</p></details> : null}
          <time dateTime={row.updatedAt}>{Number.isNaN(Date.parse(row.updatedAt)) ? "更新时间未知" : new Date(row.updatedAt).toLocaleDateString("zh-CN")}</time></div>
        <span className="stl4-research-status is-neutral"><i aria-hidden="true" />{row.status}</span>
        {row.href ? <Link className="stl4-research-open" href={row.href}>{row.linkLabel} <ArrowRight size={14} /></Link> : null}
      </article>)}</div> : <div className="stl4-research-empty"><h2>{page.empty}</h2><p>当前页面只显示属于你自己的资料。</p></div>}
    </section>
  </CollectionFrame>;
}

function CollectionFrame({ children }: { children: React.ReactNode }) {
  return <div className="stl4-research-page"><div className="stl4-research-detail-shell">{children}</div></div>;
}
