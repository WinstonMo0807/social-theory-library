"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, ChevronDown, FileSearch, LoaderCircle, RefreshCw, Search, SlidersHorizontal, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential, normalizePublicResourceUrl, subscribeToSessionChanges } from "@/lib/api";
import { actOnDiscoverySearch, createDiscoverySearch, readDiscoveryContext, readDiscoverySearch } from "@/lib/api/discovery.client";
import type { DiscoveryContext, DiscoveryCuration, DiscoveryEntity, DiscoveryFilters, DiscoveryPassage, DiscoverySearch } from "@/lib/api/discovery.types";
import type { SearchPayload } from "@/lib/api/search.types";
import { CollectionLink } from "./collection-link";
import { SearchModeSwitch } from "./search-mode-switch";
import { Dialog } from "./ui/dialog";
import styles from "@/app/explore/opinions/viewpoint-search.module.css";

const running = (status?: string) => status === "queued" || status === "running";
const statusLabels: Record<string, string> = { queued: "已排队", running: "正在检索", partial: "部分完成", completed: "检索完成", failed: "检索未完成", canceled: "已取消" };
const kindLabels: Record<string, string> = { scholar: "学者", scholar_profile: "学者", theory: "理论", topic: "主题", concept: "概念", discipline: "学科", subdiscipline: "子学科", knowledge_node: "知识条目", timeline: "时间线", timeline_event: "历史事件", reading_path: "阅读路径", recommendation: "推荐书目" };
const filterLabels: Record<string, string> = { work_id: "指定作品", author: "责任者", scholar: "学者", theory: "理论", topic: "主题", concept: "概念", language: "语言", year: "出版年", year_min: "起始年", year_max: "截止年", document_type: "文献类型", source_type: "来源类型", access: "访问范围" };
const channelLabels: Record<string, string> = { passages: "原文", entities: "知识", curation: "策展" };
const first = (value: string | string[] | undefined) => Array.isArray(value) ? value[0] || "" : value || "";
const internalHref = (value: string) => value.startsWith("/") && !value.startsWith("//") ? value : "";
const errorMessage = (reason: unknown) => reason instanceof Error ? reason.message : "请求未完成，请重试。";
const invalidSession = (reason: unknown) => reason instanceof ApiRequestError && [401, 403, 404, 410].includes(reason.status);

export function DiscoverySearchWorkspace({ initialQuery, initialFilters, legacyRelation = false }: {
  initialQuery: string; initialFilters: DiscoveryFilters; legacyRelation?: boolean;
}) {
  const [result, setResult] = useState<DiscoverySearch | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(initialQuery ? "create" : "");
  const [pollPaused, setPollPaused] = useState(false);
  const [contextItem, setContextItem] = useState<DiscoveryPassage | null>(null);
  const [context, setContext] = useState<DiscoveryContext | null>(null);
  const [contextError, setContextError] = useState("");
  const [contextBusy, setContextBusy] = useState(false);
  const [filters, setFilters] = useState(initialFilters);
  const [facets, setFacets] = useState<SearchPayload["facets"] | null>(null);
  const [facetError, setFacetError] = useState("");
  const [facetBusy, setFacetBusy] = useState(false);
  const resultRef = useRef<DiscoverySearch | null>(null);
  const tokenRef = useRef("");
  const shownRef = useRef(3);
  const actionRef = useRef("");
  const requestRevision = useRef(0);
  const contextRevision = useRef(0);
  const pollStarted = useRef(0);
  const createRef = useRef<Promise<DiscoverySearch> | null>(null);
  const refreshInFlight = useRef(false);
  const contextItemRef = useRef<DiscoveryPassage | null>(null);
  const discard = useCallback(() => {
    contextRevision.current += 1;
    contextItemRef.current = null;
    resultRef.current = null;
    tokenRef.current = "";
    setContextItem(null); setContext(null); setResult(null);
  }, []);

  const accept = useCallback((next: DiscoverySearch) => {
    if (next.access_token) tokenRef.current = next.access_token;
    resultRef.current = next;
    setResult(next);
    // Context text is also a permission-sensitive snapshot. Close it whenever
    // a fresh response removes its source, rather than retaining revoked text.
    if (contextItemRef.current && !next.passages.some(row => row.id === contextItemRef.current?.id)) {
      contextRevision.current += 1;
      contextItemRef.current = null;
      setContext(null); setContextItem(null);
    }
  }, []);

  useEffect(() => {
    if (!initialQuery) return;
    let active = true;
    const revision = requestRevision.current;
    createRef.current ??= createDiscoverySearch(initialQuery, initialFilters);
    void createRef.current.then(next => {
      if (!active || revision !== requestRevision.current) return;
      pollStarted.current = Date.now();
      accept(next);
      setError("");
    }).catch(reason => { if (active) setError(errorMessage(reason)); }).finally(() => { if (active) setBusy(""); });
    return () => { active = false; };
  }, [initialQuery, initialFilters, accept]);

  const refresh = useCallback(async () => {
    const current = resultRef.current;
    if (!current || actionRef.current || refreshInFlight.current) return;
    refreshInFlight.current = true;
    const revision = requestRevision.current;
    try {
      const next = await readDiscoverySearch(current.id, tokenRef.current, { limit: shownRef.current });
      if (revision !== requestRevision.current || resultRef.current?.id !== current.id) return;
      accept(next);
      setError("");
    } catch (reason) {
      if (revision !== requestRevision.current) return;
      if (invalidSession(reason)) discard();
      setError(errorMessage(reason));
      setPollPaused(true);
    } finally { refreshInFlight.current = false; }
  }, [accept, discard]);

  const resultId = result?.id;
  const resultStatus = result?.status;
  useEffect(() => {
    if (!resultId || !running(resultStatus) || pollPaused) return;
    let active = true;
    let timer = 0;
    const poll = async () => {
      if (!active) return;
      if (Date.now() - pollStarted.current > 10 * 60 * 1000) { setPollPaused(true); return; }
      if (document.visibilityState === "visible") await refresh();
      if (active) timer = window.setTimeout(() => void poll(), 2000);
    };
    timer = window.setTimeout(() => void poll(), 1500);
    return () => { active = false; window.clearTimeout(timer); };
  }, [resultId, resultStatus, pollPaused, refresh]);

  useEffect(() => {
    const revalidate = () => { if (document.visibilityState === "visible") void refresh(); };
    const sessionChanged = () => {
      requestRevision.current += 1;
      // Never leave authenticated excerpts visible after a logout.
      discard(); setFacets(null);
      setError("登录状态已变化，请重新检索以使用当前访问权限。");
    };
    window.addEventListener("focus", revalidate);
    document.addEventListener("visibilitychange", revalidate);
    const unsubscribe = subscribeToSessionChanges(sessionChanged);
    return () => { window.removeEventListener("focus", revalidate); document.removeEventListener("visibilitychange", revalidate); unsubscribe(); };
  }, [refresh, discard]);

  async function sessionAction(action: "more" | "expand" | "cancel" | "refresh") {
    const current = resultRef.current;
    if (!current || actionRef.current) return;
    actionRef.current = action;
    requestRevision.current += 1;
    setBusy(action); setError("");
    try {
      let limit = shownRef.current;
      if (action === "more") {
        if (!current.next_cursor) return;
        const page = await readDiscoverySearch(current.id, tokenRef.current, { cursor: current.next_cursor, limit: 3 });
        limit = Math.min(400, shownRef.current + page.passages.length);
      } else if (action === "expand" || action === "cancel") {
        await actOnDiscoverySearch(current.id, tokenRef.current, action);
      }
      // Reload the displayed prefix so every previously shown result is checked
      // against current permissions, including during pagination and expansion.
      const next = await readDiscoverySearch(current.id, tokenRef.current, { limit });
      if (resultRef.current?.id !== current.id) return;
      shownRef.current = limit;
      pollStarted.current = Date.now();
      setPollPaused(false);
      accept(next);
    } catch (reason) { if (invalidSession(reason)) discard(); setError(errorMessage(reason)); }
    finally { actionRef.current = ""; setBusy(""); }
  }

  async function openContext(item: DiscoveryPassage) {
    const current = resultRef.current;
    if (!current) return;
    const revision = ++contextRevision.current;
    contextItemRef.current = item;
    setContextItem(item); setContext(null); setContextError(""); setContextBusy(true);
    try {
      const next = await readDiscoveryContext(current.id, tokenRef.current, item.id);
      if (contextRevision.current === revision) setContext(next);
    } catch (reason) {
      if (contextRevision.current === revision) {
        setContextError(errorMessage(reason));
        // A removed source must also disappear from the underlying result list.
        if (invalidSession(reason)) void refresh();
      }
    }
    finally { if (contextRevision.current === revision) setContextBusy(false); }
  }

  async function loadFacets() {
    if (facets || facetBusy) return;
    const revision = requestRevision.current;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    setFacetBusy(true); setFacetError("");
    try {
      const payload = await apiRequest<SearchPayload>("/catalog/search/?context=global&page_size=1", { signal: controller.signal }, getServerSessionCredential());
      if (revision === requestRevision.current) setFacets(payload.facets);
    } catch (reason) { setFacetError(errorMessage(reason)); }
    finally { window.clearTimeout(timeout); setFacetBusy(false); }
  }

  const isRunning = running(result?.status);
  const selectedCount = Object.values(filters).filter(value => first(value)).length;
  const retryParams = new URLSearchParams({ q: initialQuery });
  for (const [name, value] of Object.entries(initialFilters)) {
    for (const entry of Array.isArray(value) ? value : [value]) if (entry) retryParams.append(name, entry);
  }
  const retryHref = initialQuery ? `/explore/opinions?${retryParams}` : "/explore/opinions";
  const closeContext = () => { contextRevision.current += 1; contextItemRef.current = null; setContextItem(null); setContext(null); };
  return <div className={`page-shell explore-page ${styles.page}`}>
    <header className="explore-workbench-head exact-workbench-head viewpoint-workbench-head">
      <div className="explore-workbench-title"><h1>观点检索</h1><p>从概念、问题或记忆中的表述，找到馆藏原文、知识入口与阅读推荐。</p></div>
      <form className={styles.searchForm} action="/explore/opinions">
        <div className={styles.queryRow}><Search size={19} aria-hidden="true" /><label className="sr-only" htmlFor="discovery-query">概念、研究问题或观点线索</label><input id="discovery-query" type="search" name="q" required minLength={2} maxLength={1200} defaultValue={initialQuery} placeholder="输入概念、研究问题或观点线索" /><button className="button" type="submit">开始检索 <ArrowRight size={15} /></button></div>
        <details className={styles.filterDisclosure} onToggle={event => { if (event.currentTarget.open) void loadFacets(); }}>
          <summary><SlidersHorizontal size={14} />限定检索范围{selectedCount ? ` · ${selectedCount} 项` : ""}</summary>
          <div className={styles.filterGrid}>
            <label><span>文献类型</span><select name="document_type" value={first(filters.document_type)} onChange={e => setFilters(current => ({ ...current, document_type: e.target.value }))}><option value="">全部文献</option><option value="book">图书</option><option value="journal_article">期刊论文</option><option value="journal_issue">期刊整期</option><option value="thesis">学位论文</option><option value="report">研究报告</option></select></label>
            {([ ["author", "责任者", facets?.authors], ["theory", "理论", facets?.theories], ["topic", "主题", facets?.topics], ["concept", "概念", facets?.concepts], ["language", "文献语言", facets?.languages] ] as const).map(([name, label, options]) => <label key={name}><span>{label}</span><select name={name} value={first(filters[name])} onChange={e => setFilters(current => ({ ...current, [name]: e.target.value }))}><option value="">不限</option>{first(filters[name]) && !options?.some(row => row.value === first(filters[name])) ? <option value={first(filters[name])}>当前选择</option> : null}{options?.map(row => <option key={row.value} value={row.value}>{row.label}</option>)}</select></label>)}
            <label><span>出版年起</span><input type="number" name="year_min" min="1" max="3000" value={first(filters.year_min)} onChange={e => setFilters(current => ({ ...current, year_min: e.target.value }))} placeholder="不限" /></label>
            <label><span>出版年止</span><input type="number" name="year_max" min="1" max="3000" value={first(filters.year_max)} onChange={e => setFilters(current => ({ ...current, year_max: e.target.value }))} placeholder="不限" /></label>
          </div>
          {Object.entries(filters).filter(([name, value]) => !["document_type", "author", "theory", "topic", "concept", "language", "year_min", "year_max"].includes(name) && first(value)).map(([name, value]) => <span className={styles.filterChip} key={name}>{filterLabels[name] || "已有范围"}{(Array.isArray(value) ? value : [value]).map(entry => <input type="hidden" key={entry} name={name} value={entry} />)}<button type="button" aria-label={`取消${filterLabels[name] || "已有范围"}筛选`} onClick={() => setFilters(current => { const next = { ...current }; delete next[name]; return next; })}><X size={12} /></button></span>)}
          <p className={styles.help}>筛选由你选择。没有人工标签的文献仍参与全库正文检索；混合语言内容默认一并查找。</p>
          {facetBusy ? <p role="status">正在读取馆内筛选项……</p> : null}
          {facetError ? <p role="alert">{facetError}<button type="button" className="text-link" onClick={() => void loadFacets()}>重试读取筛选项</button></p> : null}
          <div className={styles.actions}><button className="button secondary" type="submit">应用范围并检索</button>{selectedCount ? <Link href={initialQuery ? `/explore/opinions?q=${encodeURIComponent(initialQuery)}` : "/explore/opinions"}>清除全部筛选</Link> : null}</div>
        </details>
      </form>
      <SearchModeSwitch mode="semantic" query={initialQuery} />
    </header>

    {legacyRelation ? <p className={styles.notice}>这个旧链接中的问题和文献筛选已保留。新版按相关原文、知识与策展呈现，不再按支持或相斥分类。</p> : null}
    {error ? <div className={styles.error} role="alert"><strong>本次请求未完成</strong><p>{error}</p>{result ? <button className="button secondary" type="button" disabled={Boolean(busy)} onClick={() => void sessionAction("refresh")}>重新读取本次结果</button> : <a className="button secondary" href={retryHref}>重新检索</a>}</div> : null}
    {result?.warnings?.length ? <div className={styles.notice} role="status">{result.warnings.map((warning, index) => <p key={index}>{typeof warning === "string" ? warning : warning.message}</p>)}</div> : null}
    {result?.source_changed ? <p className={styles.notice}>资料或访问范围已有变化，已重新核验当前结果。重新检索可使用最新馆藏与策展内容。</p> : null}

    <div className={styles.resultLayout}>
      <main className={styles.results} aria-label="原文检索结果">
        <header className={styles.resultsHeader}><div><p>馆藏原文</p><h2>原文材料</h2></div><span>{result ? `${result.passages.length}${typeof result.count === "number" ? ` / ${result.count}` : ""} 段` : initialQuery ? "等待检索结果" : "等待输入"}</span></header>
        {(busy === "create" || isRunning) ? <div className={styles.progress} role="status"><LoaderCircle size={18} className={styles.spinner} /><div><strong>{busy === "create" ? "正在创建检索" : result?.expansion_count ? "正在扩大研究范围" : statusLabels[result?.status || "running"]}</strong><p>{result?.status_message || "后台正在查找并排序材料。你可以先阅读已找到的结果。"}</p>{result?.completed_channels?.length ? <small>已完成：{result.completed_channels.map(name => channelLabels[name] || name).join("、")}</small> : null}</div>{result ? <button type="button" disabled={Boolean(busy)} onClick={() => void sessionAction("cancel")}>取消检索</button> : null}</div> : null}
        {pollPaused && isRunning ? <div className={styles.notice}><p>自动更新已暂停，后台任务可能仍在继续。可重新读取进度或取消任务。</p><button className="button secondary" type="button" disabled={Boolean(busy)} onClick={() => void sessionAction("refresh")}>继续读取进度</button></div> : null}
        {result && !isRunning ? <p className={styles.resultStatus} role="status">{statusLabels[result.status]}{result.mode === "expanded" ? " · 已扩大检索预算" : ""}{result.status_message ? ` · ${result.status_message}` : ""}</p> : null}
        <div className={styles.cardList}>{result?.passages.map((item, index) => <DiscoveryPassageCard key={item.id} item={item} index={index} onContext={() => void openContext(item)} />)}</div>
        {!result?.passages.length && !isRunning && busy !== "create" ? <section className={styles.empty}><FileSearch size={29} aria-hidden="true" /><h3>{!initialQuery ? "从你关心的问题开始" : result?.status === "failed" ? "原文通道暂未完成" : result?.status === "canceled" ? "本次检索已取消" : error ? "还没有可显示的结果" : "本次未找到可展示的原文"}</h3><p>{!initialQuery ? "输入概念、开放问题或近似引句。结果直接回到馆内材料，你也可以沿知识与策展线索继续阅读。" : "没有结果不代表馆内不存在相关讨论。可调整问题、扩大研究范围，或继续查看相关知识与策展。"}</p>{initialQuery ? <Link href={`/explore/original?context=global&q=${encodeURIComponent(initialQuery)}`} className="button secondary">转到原文检索 <ArrowRight size={14} /></Link> : null}</section> : null}
        {result ? <footer className={styles.more}><div className={styles.actions}>{result.next_cursor ? <button type="button" className="button secondary" disabled={Boolean(busy)} onClick={() => void sessionAction("more")}>{busy === "more" ? "正在读取" : "查看更多材料"}<ChevronDown size={15} /></button> : null}{result.can_expand && !isRunning ? <button type="button" className="button" disabled={Boolean(busy)} onClick={() => void sessionAction("expand")}>{busy === "expand" ? "正在提交" : "扩大研究范围"}<Search size={14} /></button> : null}{!isRunning ? <button className="text-link" type="button" disabled={Boolean(busy)} onClick={() => void sessionAction("refresh")}><RefreshCw size={13} />刷新本次结果</button> : null}</div><p>默认展示三段。查看更多读取本次已找到的材料；扩大研究范围会增加后台检索预算，保留现有顺序。</p></footer> : null}
      </main>
      <aside className={styles.inspector} aria-label="相关知识与策展推荐">
        <section><header><h2>相关知识</h2><span>{result?.entities.length || 0}</span></header><p className={styles.help}>馆内已有的学者、理论与主题入口。关联线索不代表观点最早归属。</p>{result?.entities.map(item => <DiscoveryEntityCard key={`${item.kind}-${item.id}`} item={item} />)}{!result?.entities.length ? <p className={styles.sideEmpty}>{isRunning ? "知识通道正在查找。" : initialQuery ? "本次暂无相关知识入口。" : "检索后在这里查看相关知识。"}</p> : null}</section>
        <section><header><h2>策展推荐</h2><span>{result?.curation.length || 0}</span></header><p className={styles.help}>管理员已发布的导读和推荐理由，独立标明来源。</p>{result?.curation.map(item => <DiscoveryCurationCard key={item.id} item={item} />)}{!result?.curation.length ? <p className={styles.sideEmpty}>{isRunning ? "策展通道正在查找。" : initialQuery ? "本次暂无相关策展推荐。" : "检索后在这里查看阅读推荐。"}</p> : null}</section>
        <DiscoveryCoverageDetails result={result} />
      </aside>
    </div>
    <Dialog open={Boolean(contextItem)} onRequestClose={closeContext} className={styles.contextDialog} aria-labelledby="discovery-context-title"><header className={styles.dialogHeader}><div><p>连续上下文</p><h2 id="discovery-context-title">{contextItem?.work.title || "原文上下文"}</h2></div><button type="button" aria-label="关闭上下文" onClick={closeContext}><X size={21} /></button></header><div className={styles.contextBody}>{contextBusy ? <p role="status">正在从同一修订读取上下文……</p> : contextError ? <div role="alert"><p>{contextError}</p><button type="button" className="button secondary" onClick={() => contextItem && void openContext(contextItem)}>重试读取上下文</button></div> : context ? <><p className={styles.help}>{context.notice || "以下内容来自同一正文修订，按原有次序展示。"}</p>{context.blocks?.length ? context.blocks.map((block, index) => <section key={`${block.pdf_page}-${index}`} className={(block.role === "hit" || block.role === "match") ? styles.contextMatch : styles.contextBlock}><small>PDF 第 {block.pdf_page} 页{(block.role === "hit" || block.role === "match") ? " · 命中段落" : ""}</small><p>{block.text}</p></section>) : <><p>{context.before}</p><blockquote>{context.excerpt}</blockquote><p>{context.after}</p></>}<p className={styles.help}>{context.locator_precision === "exact" ? "可在原始 PDF 中核对定位。" : "当前按页定位，请在原始 PDF 中核对具体位置。"}</p>{internalHref(context.reader_url) ? <CollectionLink className="button" href={context.reader_url}>阅读原始 PDF <BookOpen size={15} /></CollectionLink> : null}</> : null}</div></Dialog>
  </div>;
}

export function DiscoveryPassageCard({ item, index, onContext }: { item: DiscoveryPassage; index: number; onContext: () => void }) {
  const reader = internalHref(item.reader_url);
  const isOcr = /ocr/i.test(item.source_kind);
  return <article className={styles.evidenceCard} id={`material-${item.id}`}>
    <header><span className={styles.resultNumber}>{String(index + 1).padStart(2, "0")}</span><div><p>{item.authors?.length ? item.authors.join("、") : "责任者待核对"}</p><h3>{item.work.slug ? <CollectionLink href={`/works/${encodeURIComponent(item.work.slug)}`}>{item.work.title}</CollectionLink> : item.work.title}</h3></div><span className={styles.sourceTag}>{isOcr ? "OCR 原文" : "原文材料"}</span></header>
    <blockquote>{item.excerpt}</blockquote>
    <div className={styles.locator}><span>PDF 第 {item.pdf_page} 页</span>{item.printed_page && item.printed_page !== String(item.pdf_page) ? <span>印刷页 {item.printed_page}</span> : null}<span>{item.locator_precision === "exact" ? "原文定位" : "按页定位"}</span></div>
    {isOcr ? <p className={styles.help}>文字来自 OCR 识别，可回到扫描画面核对。</p> : null}
    {item.match_basis?.length ? <p className={styles.reason}>{item.match_basis.join(" · ")}</p> : null}
    <footer><details><summary>来源与版本</summary><dl><div><dt>正文修订</dt><dd>{item.document_revision_id || "未提供"}</dd></div><div><dt>源文件</dt><dd>{item.asset_id}</dd></div></dl></details><div className={styles.actions}><button className="button secondary" type="button" onClick={onContext}>查看上下文</button>{reader ? <CollectionLink className="button secondary" href={reader}>阅读原文 <ArrowRight size={14} /></CollectionLink> : <span>阅读定位暂不可用</span>}</div></footer>
  </article>;
}

export function DiscoveryEntityCard({ item }: { item: DiscoveryEntity }) {
  const href = internalHref(item.url);
  const [portraitFailed, setPortraitFailed] = useState(false);
  return <article className={styles.entityCard}>{item.portrait_url && !portraitFailed ? <img src={normalizePublicResourceUrl(item.portrait_url)} alt="" width={48} height={60} loading="lazy" onError={() => setPortraitFailed(true)} /> : null}<div><small>{kindLabels[item.kind] || "知识条目"}</small><h3>{href ? <CollectionLink href={href}>{item.title}<ArrowRight size={12} /></CollectionLink> : item.title}</h3>{item.excerpt ? <p>{item.excerpt}</p> : null}{item.match_basis?.length ? <small>{item.match_basis.join(" · ")}</small> : null}</div></article>;
}

export function DiscoveryCurationCard({ item, preview = false }: { item: DiscoveryCuration; preview?: boolean }) {
  const href = internalHref(item.url);
  return <article className={styles.curationCard}><span className={styles.sourceTag}>{preview ? "策展推荐 · 草稿预览" : "策展推荐"}</span><h3>{item.title || item.source_title}</h3><p>{item.recommendation_excerpt}</p><small>来源：{item.source_title}</small>{item.match_basis?.length ? <small>{item.match_basis.join(" · ")}</small> : null}{href && !preview ? <CollectionLink className="text-link" href={href}>阅读完整策展 <ArrowRight size={13} /></CollectionLink> : null}</article>;
}

function DiscoveryCoverageDetails({ result }: { result: DiscoverySearch | null }) {
  const coverage = result?.coverage_summary;
  const labels = { eligible_editions: "本次可访问文献", indexed_editions: "关键词已就绪", vector_editions: "向量已就绪", pending_editions: "等待更新", passage_count: "索引段落" } as const;
  return <section className={styles.coverage}><details><summary>本次检索覆盖</summary>{coverage?.message ? <p>{coverage.message}</p> : !result ? <p>开始检索后显示实际覆盖状态。</p> : null}{coverage?.partial ? <p>当前仍有文献等待文本或索引更新，本次检索覆盖尚未完整。</p> : null}<dl>{Object.entries(labels).map(([key, label]) => { const value = coverage?.[key as keyof typeof labels]; return typeof value === "number" ? <div key={key}><dt>{label}</dt><dd>{value}</dd></div> : null; })}</dl><p>覆盖只说明当前可检索的资料范围，不表示已经找齐所有相关论证。</p>{result?.corpus_version ? <p className={styles.version}>资料版本 {result.corpus_version}</p> : null}</details></section>;
}
