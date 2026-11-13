"use client";

import { LoadingState } from "@/components/ui/loading-state";

import { useEffect, useState } from "react";
import { Check, Search, X } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { safeFeedbackPath } from "@/lib/api/feedback.client";
import type { ScopedSearchEnvelope } from "@/lib/api/search.types";
import type { EditorialDirectory } from "@/lib/api/recommendation-issues.types";
import { Dialog } from "@/components/ui/dialog";
import { usePublicSource } from "./feedback-source-card";
import styles from "./feedback-page-picker.module.css";

export const feedbackPages = [
  ["/", "欢迎页"], ["/home", "首页"], ["/explore", "书库检索"], ["/explore/original", "原文检索"],
  ["/explore/opinions", "观点检索"], ["/explore/evidence", "观点检索结果"],
  ["/theories", "理论流派"], ["/scholars", "学者"], ["/topics", "主题"],
  ["/recommendations", "特别策划"], ["/help", "使用帮助"], ["/about", "关于书库"],
] as const;
type Choice = { path: string; title: string; subtitle: string };
type Kind = "pages" | "works" | "scholars" | "theories" | "topics" | "issues";
const kinds = [["pages", "常用页面"], ["works", "书籍与文献"], ["scholars", "学者"], ["theories", "理论流派"], ["topics", "主题"], ["issues", "特别策划"]] as const;

export function FeedbackPagePicker({ path, title, error, onChange, onClose, onSave }: {
  path: string; title: string; error: string; onChange: (path: string, title?: string) => void; onClose: () => void; onSave: () => void;
}) {
  const [kind, setKind] = useState<Kind>("pages");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState({ query: "", page: 1, attempt: 0 });
  const [result, setResult] = useState<{ rows: Choice[]; pages: number } | null>(null);
  const [loadError, setLoadError] = useState("");
  const publicPath = safeFeedbackPath(path);
  const source = usePublicSource(/^\/(works|reader)\//.test(publicPath) ? publicPath.split("?", 1)[0] : "");
  const readerPath = safeFeedbackPath(source.source?.reader_url || "");
  useEffect(() => {
    if (kind === "pages") return;
    const controller = new AbortController();
    const options = { cache: "no-store" as const, signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20000)]) };
    setResult(null); setLoadError("");
    async function load() {
      const params = new URLSearchParams({ q: search.query, page: String(search.page), page_size: "8", visibility: "public" });
      if (kind === "issues") {
        params.set("view", "directory");
        const data = await apiRequest<EditorialDirectory>(`/catalog/recommendation-issues/?${params}`, options, null, false);
        return { rows: data.results.map(row => ({ path: safeFeedbackPath(row.href), title: row.title, subtitle: row.issue_label })), pages: data.total_pages };
      }
      params.set("context", kind); params.set("envelope", "1");
      const data = await apiRequest<ScopedSearchEnvelope>(`/catalog/search/?${params}`, options, null, false);
      if (data.visibility !== "public" || data.context !== kind) throw new Error("无法读取公开页面，请重试。");
      return { rows: data.groups.flatMap(group => group.results).map(row => ({ path: safeFeedbackPath(row.url), title: row.title, subtitle: row.subtitle })), pages: data.pagination.total_pages };
    }
    void load().then(data => { if (!controller.signal.aborted) setResult({ ...data, rows: data.rows.filter(row => row.path) }); })
      .catch(reason => { if (!controller.signal.aborted) setLoadError(reason instanceof Error ? reason.message : "页面列表暂时无法读取。"); });
    return () => controller.abort();
  }, [kind, search]);
  const rows = kind === "pages" ? feedbackPages.map(([path, title]) => ({ path, title, subtitle: "" })) : result?.rows || [];
  return <Dialog open onRequestClose={onClose} className={`stl4-support-path-dialog ${styles.picker}`} aria-labelledby="feedback-path-title">
    <header><h2 id="feedback-path-title">选择相关页面</h2><button type="button" aria-label="关闭关联页面" onClick={onClose}><X size={20} /></button></header>
    <form onSubmit={event => { event.preventDefault(); setSearch(value => ({ query: query.trim(), page: 1, attempt: value.attempt + 1 })); }} className={styles.search}>
      <label><span className="sr-only">页面类型</span><select data-stl-select value={kind} onChange={event => { setKind(event.target.value as Kind); setQuery(""); setResult(null); setLoadError(""); setSearch({ query: "", page: 1, attempt: 0 }); }}>{kinds.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      {kind !== "pages" ? <><label><span className="sr-only">按名称查找页面</span><input type="search" placeholder="输入名称查找" value={query} maxLength={120} onChange={event => setQuery(event.target.value)} /></label><button type="submit" aria-label="查找页面"><Search size={18} /></button></> : null}
    </form>
    <div className={styles.choices} aria-label="可关联页面" aria-busy={kind !== "pages" && !result && !loadError}>
      {rows.map(row => <button type="button" key={row.path} aria-pressed={path === row.path} onClick={() => onChange(row.path, row.title)}><span><strong>{row.title}</strong>{row.subtitle ? <small>{row.subtitle}</small> : null}</span>{path === row.path ? <Check size={18} aria-hidden="true" /> : null}</button>)}
      {kind !== "pages" && !result && !loadError ? <LoadingState variant="compact" role="status">正在读取页面…</LoadingState> : null}
      {result && !rows.length ? <p role="status">没有找到相关页面，试试其他名称。</p> : null}
      {loadError ? <p role="alert">{loadError}<button type="button" onClick={() => setSearch(value => ({ ...value, attempt: value.attempt + 1 }))}>重试</button></p> : null}
    </div>
    {kind !== "pages" && result && result.pages > 1 ? <nav className={styles.pagination} aria-label="页面列表翻页"><button type="button" disabled={search.page <= 1} onClick={() => setSearch(value => ({ ...value, page: value.page - 1 }))}>上一页</button><span>{search.page} / {result.pages}</span><button type="button" disabled={search.page >= result.pages} onClick={() => setSearch(value => ({ ...value, page: value.page + 1 }))}>下一页</button></nav> : null}
    {readerPath && publicPath.startsWith("/works/") ? <button className={styles.reader} type="button" onClick={() => onChange(`${readerPath}?page=1`, source.source?.title)}>选择这本书的阅读页</button> : null}
    {publicPath.startsWith("/reader/") ? <label className={styles.pageNumber}>PDF 页码<input type="number" min="1" max="999999" value={new URLSearchParams(publicPath.split("?")[1] || "").get("page") || "1"} onChange={event => {
      const page = Number(event.target.value);
      if (Number.isInteger(page) && page > 0 && page <= 999999) onChange(`${publicPath.split("?", 1)[0]}?page=${page}`, title || source.source?.title);
    }} /></label> : null}
    <details data-disclosure="collection" className={styles.address}><summary>手动填写网址</summary><label>本站页面地址<input value={path} maxLength={2048} onChange={event => onChange(event.target.value)} placeholder="粘贴本站页面的网址" /></label><p>网址仅保留页面路径与 PDF 页码，不附带检索词或私人信息。</p></details>
    {path ? <p className={styles.selected}>已选：{title || feedbackPages.find(([href]) => href === path)?.[1] || path}{publicPath.startsWith("/reader/") ? ` · PDF 第 ${new URLSearchParams(publicPath.split("?")[1] || "").get("page") || "1"} 页` : ""}</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    <footer><button type="button" onClick={onClose}>取消</button><button className="stl4-support-primary" type="button" disabled={!path.trim()} onClick={onSave}>关联页面</button></footer>
  </Dialog>;
}
