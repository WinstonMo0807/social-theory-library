"use client";

import { LoadingState } from "@/components/ui/loading-state";
import { useEvidenceLanguage } from "./evidence-language";
import { SourceText } from "./source-text";
import { MediaPlacement } from "./media-placement";

import Link from "next/link";
import { ScholarPortraitFallback } from "@/components/default-scholar-portrait";
import { ArrowRight, ChevronDown, FileSearch, LayoutGrid, List, LoaderCircle, Quote, RefreshCw, Search, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential, normalizePublicResourceUrl, subscribeToSessionChanges } from "@/lib/api";
import { actOnDiscoverySearch, canKeepDiscoveryContext, canRetryDiscoveryRead, createDiscoverySearch, discoveryCoverageRows, readDiscoveryContext, readDiscoverySearch, removeDiscoveryDocument } from "@/lib/api/discovery.client";
import type { DiscoveryContext, DiscoveryCuration, DiscoveryEntity, DiscoveryFilters, DiscoveryPassage, DiscoverySearch, DiscoverySort } from "@/lib/api/discovery.types";
import type { SearchPayload } from "@/lib/api/search.types";
import { CollectionLink } from "./collection-link";
import { EvidenceContextBody, EvidenceResultCard, EvidenceSummary } from "./discovery-evidence-detail";
import { DiscoveryDocumentProgress } from "./discovery-document-progress";
import { SavedWorkStatusProvider } from "./save-work-button";
import { Dialog } from "./ui/dialog";
import { usePublicSession } from "./public-session-provider";
import { saveGuestRecord } from "@/lib/guest-records";
import styles from "@/app/explore/opinions/viewpoint-search.module.css";

const running = (status?: string) => status === "queued" || status === "running";
const statusLabels: Record<string, string> = { queued: "已排队", running: "正在检索", partial: "部分完成", completed: "检索完成", failed: "检索未完成", canceled: "已取消" };
const deepStatusLabels: Record<string, string> = { baseline_ready: "基础结果已就绪", deep_queued: "深度整理已排队", deep_running: "正在深度整理", completed: "深度结果已完成", partial: "深度结果部分完成", unavailable: "深度层暂不可用", pending: "深度整理待启动", queued: "深度整理已排队", running: "正在深度整理", degraded: "深度结果部分完成", disabled: "深度层暂不可用", skipped: "深度层暂跳过", failed: "深度层暂不可用" };
const kindLabels: Record<string, string> = { scholar: "学者", scholar_profile: "学者", theory: "理论", topic: "主题", concept: "概念", discipline: "学科", subdiscipline: "子学科", knowledge_node: "知识条目", timeline: "时间线", timeline_event: "历史事件", reading_path: "阅读路径", recommendation: "推荐书目" };
const filterLabels: Record<string, string> = { work_ids: "指定作品", authors: "责任者", topic_ids: "主题", theory_node_ids: "理论", topics: "主题", theories: "理论流派", concepts: "概念", document_types: "文献类型", languages: "语言", years: "出版年", source_types: "来源类型", work_id: "指定作品", author: "责任者", scholar: "学者", theory: "理论", topic: "主题", concept: "概念", language: "语言", year: "出版年", year_min: "起始年", year_max: "截止年", document_type: "文献类型", source_type: "来源类型", access: "访问范围" };
const channelLabels: Record<string, string> = { passages: "原文", entities: "知识", curation: "策展", deep: "材料整理" };
const evidenceYears = [["全部", "", ""], ["2020 以后", "2020", ""], ["2010–2019", "2010", "2019"], ["2000–2009", "2000", "2009"], ["1990–1999", "1990", "1999"], ["1990 以前", "", "1989"]] as const;
const first = (value: string | string[] | undefined) => Array.isArray(value) ? value[0] || "" : value || "";
const internalHref = (value: string) => value.startsWith("/") && !value.startsWith("//") && !/[\\\u0000-\u001f\u007f]/.test(value) ? value : "";
// Disposable navigation state holds identifiers only, never stored excerpts or search history.
const returnSessions = new Map<string, { id: string; token: string; limit: number; sort: DiscoverySort; at: number }>();
const errorMessage = (reason: unknown) => reason instanceof Error ? reason.message : "请求未完成，请重试。";
const invalidSession = (reason: unknown) => reason instanceof ApiRequestError && [401, 403, 404, 410].includes(reason.status);

export function DiscoverySearchWorkspace({ initialQuery, initialFilters, legacyRelation = false }: {
  initialQuery: string; initialFilters: DiscoveryFilters; legacyRelation?: boolean;
}) {
  const { t } = useEvidenceLanguage();
  const { state: publicSession } = usePublicSession();
  const savedGuestSearch = useRef("");
  const cacheKey = JSON.stringify([initialQuery, initialFilters]);
  const [selectedId, setSelectedId] = useState("");
  const [queryInput, setQueryInput] = useState(initialQuery);
  const queryInputRef = useRef<HTMLInputElement>(null);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [summaryHidden, setSummaryHidden] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [view, setView] = useState<"list" | "grid">("list");
  const restored = useRef(false);
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
  const sortRef = useRef<DiscoverySort>("relevance");
  const actionRef = useRef("");
  const requestRevision = useRef(0);
  const contextRevision = useRef(0);
  const pollStarted = useRef(0);
  const createRef = useRef<Promise<DiscoverySearch> | null>(null);
  const refreshInFlight = useRef(false);
  const failedReads = useRef(0);
  const contextItemRef = useRef<DiscoveryPassage | null>(null);
  useEffect(() => {
    if (publicSession.status !== "unauthenticated" || !result?.id || savedGuestSearch.current === result.id) return;
    if (saveGuestRecord({ kind: "search", query: result.original_query || initialQuery, filters: result.filters || initialFilters })) savedGuestSearch.current = result.id;
  }, [publicSession.status, result?.id, result?.original_query, result?.filters, initialQuery, initialFilters]);
  const discard = useCallback(() => {
    contextRevision.current += 1;
    contextItemRef.current = null;
    resultRef.current = null;
    tokenRef.current = "";
    returnSessions.delete(cacheKey);
    setContextItem(null); setContext(null); setResult(null); setSelectedId(""); setSummaryOpen(false);
  }, [cacheKey]);

  const accept = useCallback((next: DiscoverySearch) => {
    failedReads.current = 0;
    if (next.access_token) tokenRef.current = next.access_token;
    if (next.sort) sortRef.current = next.sort;
    resultRef.current = next;
    setResult(next);
    returnSessions.set(cacheKey, { id: next.id, token: tokenRef.current, limit: shownRef.current, sort: sortRef.current, at: Date.now() });
    if (returnSessions.size > 10) returnSessions.delete(returnSessions.keys().next().value!);
    // Context text is also a permission-sensitive snapshot. Close it whenever
    // a fresh response removes its source, rather than retaining revoked text.
    if (contextItemRef.current && !canKeepDiscoveryContext(contextItemRef.current, next)) {
      const item = contextItemRef.current;
      const revision = ++contextRevision.current;
      setContext(null);
      if (next.source_changed || next.passages.some(row => row.id === item.id)) {
        contextItemRef.current = null; setContextItem(null);
      } else {
        // A same-book candidate may sit beyond the loaded result prefix.
        // Revalidate its identity instead of treating pagination as withdrawal.
        setContextBusy(true); setContextError("");
        void readDiscoveryContext(next.id, tokenRef.current, item.id).then(value => {
          if (revision === contextRevision.current) setContext(value);
        }).catch(reason => { if (revision === contextRevision.current) setContextError(errorMessage(reason)); })
          .finally(() => { if (revision === contextRevision.current) setContextBusy(false); });
      }
    }
  }, [cacheKey]);

  useEffect(() => {
    if (!initialQuery) return;
    let active = true;
    const revision = requestRevision.current;
    const saved = returnSessions.get(cacheKey);
    if (!createRef.current && saved && Date.now() - saved.at < 30 * 60 * 1000) {
      tokenRef.current = saved.token; shownRef.current = saved.limit; sortRef.current = saved.sort;
      createRef.current = readDiscoverySearch(saved.id, saved.token, { limit: saved.limit, sort: saved.sort });
    }
    createRef.current ??= createDiscoverySearch(initialQuery, initialFilters);
    void createRef.current.then(next => {
      if (!active || revision !== requestRevision.current) return;
      pollStarted.current = Date.now();
      accept(next);
      setError("");
    }).catch(reason => { if (active) setError(errorMessage(reason)); }).finally(() => { if (active) setBusy(""); });
    return () => { active = false; };
  }, [initialQuery, initialFilters, cacheKey, accept]);

  const refresh = useCallback(async () => {
    const current = resultRef.current;
    if (!current || actionRef.current || refreshInFlight.current) return;
    refreshInFlight.current = true;
    const revision = requestRevision.current;
    try {
      const next = await readDiscoverySearch(current.id, tokenRef.current, { limit: shownRef.current, sort: sortRef.current });
      if (revision !== requestRevision.current || resultRef.current?.id !== current.id) return;
      accept(next);
      setError("");
    } catch (reason) {
      if (revision !== requestRevision.current) return;
      if (invalidSession(reason)) discard();
      setError(errorMessage(reason));
      // Retry only reads of this existing session; never recreate a search or
      // repeat an expansion after an uncertain network response.
      setPollPaused(!running(current.status) || !canRetryDiscoveryRead(reason, ++failedReads.current));
    } finally { refreshInFlight.current = false; }
  }, [accept, discard]);

  const resultId = result?.id;
  const resultStatus = result?.status;
  useEffect(() => {
    if (restored.current || !result?.passages.length) return;
    const hash = window.location.hash.slice(1);
    const item = result.passages.find(row => `material-${row.id}` === hash);
    if (!item) return;
    restored.current = true;
    const frame = window.requestAnimationFrame(() => {
      setSelectedId(item.id);
      document.getElementById(hash)?.scrollIntoView({ block: "start", behavior: "instant" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [result]);
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
      returnSessions.clear(); discard(); setFacets(null);
      setError("登录状态已变化，请重新检索以使用当前访问权限。");
    };
    window.addEventListener("focus", revalidate);
    document.addEventListener("visibilitychange", revalidate);
    const unsubscribe = subscribeToSessionChanges(sessionChanged);
    return () => { window.removeEventListener("focus", revalidate); document.removeEventListener("visibilitychange", revalidate); unsubscribe(); };
  }, [refresh, discard]);

  async function documentAction(id: string, remove = false) {
    const current = resultRef.current;
    if (!current || actionRef.current) return;
    actionRef.current = "document";
    const revision = ++requestRevision.current;
    setBusy("document"); setError("");
    try {
      if (remove) await removeDiscoveryDocument(current.id, tokenRef.current, id, current.generation ?? current.task_progress.generation);
      const limit = remove ? shownRef.current : 440;
      const next = await readDiscoverySearch(current.id, tokenRef.current, { limit, sort: sortRef.current });
      if (revision !== requestRevision.current || resultRef.current?.id !== current.id) return;
      shownRef.current = limit; accept(next); setPollPaused(false);
      if (!remove) {
        const item = next.passages.find(row => row.edition_id === id);
        if (item) { selectEvidence(item); window.requestAnimationFrame(() => document.getElementById(`material-${item.id}`)?.scrollIntoView({ block: "center" })); }
        else setError("该版本的原文来源已变化，请查看当前状态。");
      }
    } catch (reason) {
      if (revision === requestRevision.current) {
        if (invalidSession(reason)) discard();
        setError(`${errorMessage(reason)}${remove ? " 移除结果可能待确认；重试同一文献不会重复执行。" : ""}`);
      }
    } finally { actionRef.current = ""; if (revision === requestRevision.current) setBusy(""); }
  }

  async function sessionAction(action: "more" | "expand" | "cancel" | "refresh" | "retry" | "sort", nextSort?: DiscoverySort) {
    const current = resultRef.current;
    if (!current || actionRef.current) return;
    actionRef.current = action;
    const revision = ++requestRevision.current;
    setBusy(action); setError("");
    try {
      let limit = action === "sort" ? 3 : shownRef.current;
      const sort = nextSort || sortRef.current;
      if (action === "more") {
        if (!current.next_cursor) return;
        const page = await readDiscoverySearch(current.id, tokenRef.current, { cursor: current.next_cursor, limit: 3, sort });
        limit = Math.min(440, shownRef.current + page.passages.length);
      } else if (action === "expand" || action === "cancel" || action === "retry") {
        await actOnDiscoverySearch(current.id, tokenRef.current, action, current.generation ?? current.task_progress?.generation);
      }
      if (revision !== requestRevision.current || resultRef.current?.id !== current.id) return;
      // Reload the displayed prefix so every previously shown result is checked
      // against current permissions, including during pagination and expansion.
      const next = await readDiscoverySearch(current.id, tokenRef.current, { limit, sort });
      if (revision !== requestRevision.current || resultRef.current?.id !== current.id) return;
      shownRef.current = limit;
      pollStarted.current = Date.now();
      setPollPaused(false);
      accept(next);
    } catch (reason) {
      if (revision !== requestRevision.current) return;
      if (invalidSession(reason)) discard();
      setError(errorMessage(reason));
    }
    finally { actionRef.current = ""; setBusy(""); }
  }

  async function restart() {
    if (actionRef.current || running(resultRef.current?.status)) return;
    actionRef.current = "restart";
    const revision = ++requestRevision.current;
    setBusy("restart"); setError("");
    try {
      const pending = createDiscoverySearch(initialQuery, initialFilters);
      const next = await pending;
      if (revision !== requestRevision.current) return;
      createRef.current = pending;
      tokenRef.current = ""; shownRef.current = 3; sortRef.current = "relevance";
      contextRevision.current += 1; contextItemRef.current = null;
      setContextItem(null); setContext(null); setSelectedId(""); setSummaryOpen(false);
      pollStarted.current = Date.now(); setPollPaused(false);
      accept(next);
    } catch (reason) { if (revision === requestRevision.current) setError(errorMessage(reason)); }
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
      if (contextRevision.current !== revision) return;
      setContext(next);
      if (!current.passages.some(row => row.id === item.id)) {
        // An explicitly selected same-book candidate can be beyond the current
        // prefix. Load that bounded result set so Reader can return to its row.
        const expanded = await readDiscoverySearch(current.id, tokenRef.current, { limit: 440, sort: sortRef.current });
        if (contextRevision.current !== revision || resultRef.current?.id !== current.id) return;
        shownRef.current = 440;
        accept(expanded);
      }
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
      const payload = await apiRequest<SearchPayload>("/catalog/search/?context=global&scope=catalog&page_size=1", { signal: controller.signal }, getServerSessionCredential());
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
  const selected = result?.passages.find(item => item.id === selectedId) || result?.passages[0] || null;
  const returnTo = (item: DiscoveryPassage) => `/explore/evidence?${retryParams}#material-${item.id}`;
  function selectEvidence(item: DiscoveryPassage) {
    setSelectedId(item.id); setSummaryHidden(false);
    if (window.matchMedia("(max-width: 1000px)").matches) setSummaryOpen(true);
  }
  const retryHref = initialQuery ? `/explore/evidence?${retryParams}` : "/explore/opinions";
  const closeContext = () => { contextRevision.current += 1; contextItemRef.current = null; setContextItem(null); setContext(null); };
  function toggleFilter(name: string, value: string, checked: boolean) {
    setFilters(current => {
      const values = Array.isArray(current[name]) ? current[name] : current[name] ? [current[name]] : [];
      const next = { ...current, [name]: checked ? [...new Set([...values, value])] : values.filter(entry => entry !== value) };
      if (!next[name].length) delete next[name];
      return next;
    });
  }
  const checked = (name: string, value: string) => (Array.isArray(filters[name]) ? filters[name] : [filters[name]]).includes(value);
  const choiceField = (name: string, label: string, options: Array<{ value: string; label: string; count?: number }> = []) => <fieldset key={name}><legend>{t(label)}</legend>
    <label><input type="checkbox" checked={!first(filters[name])} onChange={() => setFilters(current => { const next = { ...current }; delete next[name]; return next; })} />{t("全部")}</label>
    {options.map(row => <label key={row.value}><input type="checkbox" name={name} value={row.value} checked={checked(name, row.value)} onChange={event => toggleFilter(name, row.value, event.target.checked)} /><span>{["document_type", "language", "availability"].includes(name) ? t(row.label) : row.label}</span></label>)}
    {(Array.isArray(filters[name]) ? filters[name] : [filters[name]]).filter(Boolean).filter(value => !options.some(row => row.value === value)).map(value => <label key={value}><input type="checkbox" name={name} value={value} checked onChange={() => toggleFilter(name, value, false)} />{t("当前范围")}</label>)}
  </fieldset>;
  function setYearRange(low: string, high: string) {
    setFilters(current => { const next: DiscoveryFilters = { ...current, year_min: low, year_max: high }; delete next.year; delete next.years; return next; });
  }
  const filterFields = <>
    <div className={styles.filterGrid}>
      {choiceField("document_type", t("文献类型"), facets?.document_types)}
      {choiceField("theories", t("理论流派"), facets?.theories)}
      <fieldset><legend>{t("年份")}</legend><div className={styles.yearRange}><label><span className="sr-only">{t("起始年")}</span><input type="number" name="year_min" min="1" max="3000" value={first(filters.year_min)} onChange={e => setYearRange(e.target.value, first(filters.year_max))} placeholder={t("起始年")} /></label><span aria-hidden="true">−</span><label><span className="sr-only">{t("结束年")}</span><input type="number" name="year_max" min="1" max="3000" value={first(filters.year_max)} onChange={e => setYearRange(first(filters.year_min), e.target.value)} placeholder={t("结束年")} /></label></div>
        {evidenceYears.map(([label, low, high]) => <label key={label}><input type="radio" name="year_preset" checked={!first(filters.year) && !first(filters.years) && first(filters.year_min) === low && first(filters.year_max) === high} onChange={() => setYearRange(low, high)} />{t(label)}</label>)}
      </fieldset>
      {choiceField("availability", t("可读版本"), [{ value: "readable", label: t("有在线阅读") }, { value: "pdf", label: t("有 PDF") }, { value: "zh_translation", label: t("有中译本") }])}
      <section data-content-section className={styles.extraFilters}><header data-section-heading>{t("更多筛选")}</header>
      {choiceField("language", t("文献语言"), facets?.languages)}
      {([ ["author", t("责任者"), facets?.authors], ["topics", t("主题"), facets?.topics], ["concept", t("概念"), facets?.concepts] ] as const).map(([name, label, options]) => <label key={name}><span>{t(label)}</span><select data-stl-select name={name} value={first(filters[name])} onChange={event => setFilters(current => ({ ...current, [name]: event.target.value }))}><option value="">{t("不限")}</option>{first(filters[name]) && !options?.some(row => row.value === first(filters[name])) ? <option value={first(filters[name])}>{t("当前选择")}</option> : null}{options?.map(row => <option key={row.value} value={row.value}>{row.label}</option>)}</select>{Array.isArray(filters[name]) ? filters[name].slice(1).map(value => <input key={value} type="hidden" name={name} value={value} />) : null}</label>)}
      </section>
    </div>
    {Object.entries(filters).filter(([name, value]) => !["document_type", "author", "theories", "topics", "concept", "language", "year_min", "year_max", "availability"].includes(name) && first(value)).map(([name, value]) => <span className={styles.filterChip} key={name}>{t(filterLabels[name] || "已有范围")}{(Array.isArray(value) ? value : [value]).map(entry => <input type="hidden" key={entry} name={name} value={entry} />)}<button type="button" aria-label={t("取消{label}筛选", { label: t(filterLabels[name] || "已有范围") })} onClick={() => setFilters(current => { const next = { ...current }; delete next[name]; return next; })}><X size={12} /></button></span>)}
    {facetBusy ? <LoadingState variant="compact">{t("正在读取馆内筛选项……")}</LoadingState> : null}
    {facetError ? <p role="alert">{t(facetError)}<button type="button" className="text-link" onClick={() => void loadFacets()}>{t("重试读取筛选项")}</button></p> : null}
    <div className={styles.actions}><button className="button secondary" type="submit">{t("应用范围并检索")}</button>{selectedCount ? <Link href={initialQuery ? `/explore/evidence?q=${encodeURIComponent(initialQuery)}` : "/explore/opinions"}>{t("清除全部筛选")}</Link> : null}</div>
  </>;
  return <SavedWorkStatusProvider workIds={result?.passages.map(item => item.work.id) || []}><div className={`page-shell ${styles.page}`}>
    <header className={styles.evidenceHead}>
      <p className={styles.breadcrumb}><Link href="/explore">{t("书库检索")}</Link><span>/</span>{t("原文证据")}</p>
      <h1>{t("原文证据结果")}</h1>
      <form className={styles.searchForm} action="/explore/evidence">
        <div className={styles.queryRow}><Search size={19} aria-hidden="true" /><label className="sr-only" htmlFor="discovery-query">{t("概念、研究问题或观点线索")}</label><input ref={queryInputRef} id="discovery-query" type="search" name="q" required minLength={2} maxLength={500} value={queryInput} onChange={event => setQueryInput(event.target.value)} placeholder={t("输入概念、研究问题或观点线索")} />{queryInput ? <button className={styles.queryClear} type="button" aria-label={t("清除检索问题")} onClick={() => { setQueryInput(""); queryInputRef.current?.focus(); }}><X size={16} /></button> : null}<button className="button" type="submit" aria-label={t("搜索原文证据")}><span>{t("搜索")}</span><Search size={16} aria-hidden="true" /></button></div>
        {Object.entries(filters).flatMap(([name, value]) => (Array.isArray(value) ? value : [value]).filter(Boolean).map(entry => <input type="hidden" key={`${name}-${entry}`} name={name} value={entry} />))}
      </form>
    </header>

    {legacyRelation ? <p className={styles.notice}>{t("这个旧链接中的问题和文献筛选已保留。新版按相关原文、知识与策展呈现，不再按支持或相斥分类。")}</p> : null}
    {error ? <div className={styles.error} role="alert"><strong>{t("本次请求未完成")}</strong><p>{t(error)}</p>{result ? <button className="button secondary" type="button" disabled={Boolean(busy)} onClick={() => void sessionAction("refresh")}>{t("重新读取本次结果")}</button> : <a className="button secondary" href={retryHref}>{t("重新检索")}</a>}</div> : null}
    {result?.warnings?.length ? <div className={styles.notice} role="status">{result.warnings.map((warning, index) => <p key={index}>{typeof warning === "string" ? warning : warning.message}</p>)}</div> : null}
    {result?.source_changed ? <p className={styles.notice}>{t("资料或访问范围已有变化，已重新核验当前结果。重新检索可使用最新馆藏与策展内容。")}</p> : null}

    <div className={styles.mobileFilters}>{[t("文献类型"), t("理论流派"), t("年份")].map(label => <button key={label} type="button" aria-label={t("按{label}筛选", { label: t(label) })} onClick={() => { setFilterOpen(true); void loadFacets(); }}>{t(label)}<ChevronDown size={12} /></button>)}<span className="sr-only">{selectedCount ? t("已选择{count}组条件", { count: selectedCount }) : t("全部范围")}</span></div>
    <Dialog open={filterOpen} onRequestClose={() => setFilterOpen(false)} className={styles.filterDialog} aria-labelledby="evidence-filter-title"><header className={styles.dialogHeader}><h2 id="evidence-filter-title">{t("筛选原文材料")}</h2><button type="button" onClick={() => setFilterOpen(false)} aria-label={t("关闭筛选")}><X size={18} /></button></header><form action="/explore/evidence"><input type="hidden" name="q" value={initialQuery} />{filterFields}</form></Dialog>
    <div className={`${styles.resultLayout} ${summaryHidden ? styles.summaryHidden : ""}`}>
      <aside className={styles.filterSidebar} aria-label={t("筛选馆藏原文")} onFocusCapture={() => void loadFacets()} onPointerEnter={() => void loadFacets()}><form action="/explore/evidence"><input type="hidden" name="q" value={initialQuery} />{filterFields}</form></aside>
      <section className={styles.results} id="discovery-passages" aria-label={t("原文检索结果")}>
        <header className={styles.resultsHeader}><div><h2>{t("检索结果")}</h2><span>{result ? t("已显示 {count} 段", { count: `${result.passages.length}${typeof result.count === "number" ? ` / ${result.count}` : ""}` }) : initialQuery ? t("等待检索结果") : t("等待输入")}</span></div><div className={styles.viewControls}><label><span className="sr-only">{t("结果排序")}</span><select data-stl-select aria-label={t("结果排序")} value={result?.sort || "relevance"} disabled={!result || Boolean(busy)} onChange={event => void sessionAction("sort", event.target.value as DiscoverySort)}><option value="relevance">{t("相关性排序")}</option><option value="year_desc">{t("出版年份从新到旧")}</option><option value="year_asc">{t("出版年份从旧到新")}</option></select></label><button type="button" aria-label={t("列表视图")} aria-pressed={view === "list"} onClick={() => setView("list")}><List size={17} /></button><button type="button" aria-label={t("网格视图")} aria-pressed={view === "grid"} onClick={() => setView("grid")}><LayoutGrid size={17} /></button></div></header>
        {(busy === "create" || isRunning) ? <div className={styles.progress} role="status"><LoaderCircle size={18} className={styles.spinner} /><div><strong>{busy === "create" ? t("正在创建检索") : result?.expansion_count ? t("正在扩大研究范围") : t(statusLabels[result?.status || "running"])}</strong><p>{result?.status_message || t("后台正在查找并排序材料。你可以先阅读已找到的结果。")}</p>{result?.completed_channels?.length ? <small>{t("已完成：")}{result.completed_channels.map(name => t(channelLabels[name] || name)).join("、")}</small> : null}{result ? <DiscoveryDeepProgress result={result} /> : null}</div>{result ? <button type="button" disabled={Boolean(busy)} onClick={() => void sessionAction("cancel")}>{t("取消检索")}</button> : null}</div> : null}
        {pollPaused && isRunning ? <div className={styles.notice}><p>{t("自动更新已暂停，后台任务可能仍在继续。可重新读取进度或取消任务。")}</p><button className="button secondary" type="button" disabled={Boolean(busy)} onClick={() => void sessionAction("refresh")}>{t("继续读取进度")}</button></div> : null}
        {result && !isRunning ? <><p className={styles.resultStatus} role="status">{t(statusLabels[result.status])}{result.mode === "expanded" ? t(" · 已扩大检索预算") : ""}{result.status_message ? ` · ${result.status_message}` : ""}</p><DiscoveryDeepProgress result={result} /></> : null}
        {(result?.added_count || 0) > 0 ? <p className={styles.resultStatus} role="status">{t("本轮新增 {count} 段可阅读原文", { count: result?.added_count || 0 })}</p> : null}
        <div className={`${styles.cardList} ${view === "grid" ? styles.resultGrid : ""}`}>{result?.passages.map((item, index) => <EvidenceResultCard key={item.id} item={item} index={index} selected={selected?.id === item.id && !summaryHidden} fresh={item.is_new === true} onSelect={() => selectEvidence(item)} onContext={() => void openContext(item)} />)}</div>
        {!error && !result?.passages.length && !isRunning && busy !== "create" ? <section className={styles.empty}><FileSearch size={29} aria-hidden="true" /><h3>{!initialQuery ? t("从你关心的问题开始") : result?.status === "failed" ? t("原文通道暂未完成") : result?.status === "canceled" ? t("本次检索已取消") : error ? t("还没有可显示的结果") : t("本次未找到可展示的原文")}</h3><p>{!initialQuery ? t("输入概念、开放问题或近似引句。结果直接回到馆内材料，你也可以沿知识与策展线索继续阅读。") : result?.status === "failed" ? t("检索服务未完成本次请求，请重试；筛选和查询已保留。") : result?.status === "canceled" ? t("查询已保留，可以重新发起检索。") : t("未找到结果。可以改写问题、扩大范围，或浏览相关知识与策展。")}</p>{initialQuery ? <Link href={`/explore/original?context=global&q=${encodeURIComponent(initialQuery)}`} className="button secondary">{t("转到原文检索")}<ArrowRight size={14} /></Link> : null}</section> : null}
        {result ? <footer className={styles.more}><div className={styles.actions}>{result.next_cursor ? <button type="button" className="button secondary" disabled={Boolean(busy)} onClick={() => void sessionAction("more")}>{busy === "more" ? t("正在读取") : t("查看更多材料")}<ChevronDown size={15} /></button> : null}{(result.can_retry || result.status === "failed" || result.status === "partial") && !isRunning ? <button type="button" className="button secondary" disabled={Boolean(busy)} onClick={() => void sessionAction("retry")}>{busy === "retry" ? t("正在重试") : result.status === "canceled" ? t("基于保留材料继续检索") : t("重试当前范围")}<RefreshCw size={14} /></button> : null}{result.can_expand && !isRunning ? <button type="button" className="button" disabled={Boolean(busy)} onClick={() => void sessionAction("expand")}>{busy === "expand" ? t("正在提交") : t("扩大研究范围")}<Search size={14} /></button> : null}{!isRunning ? <button className="text-link" type="button" disabled={Boolean(busy)} onClick={() => void sessionAction("refresh")}><RefreshCw size={13} />{t("刷新本次结果")}</button> : null}{!isRunning ? <button className="text-link" type="button" disabled={Boolean(busy)} onClick={() => void restart()}>{busy === "restart" ? t("正在重新开始") : t("重新开始检索")}</button> : null}</div><p>{t("默认展示三段。查看更多读取本次已找到的材料；扩大研究范围会继续查找材料，已找到的原文会保留。")}</p></footer> : null}
        {result?.documents && (result.documents.tracked > 0 || result.documents.excluded_count > 0) ? <DiscoveryDocumentProgress data={result.documents} busy={Boolean(busy)} onRemove={id => { pollStarted.current = Date.now(); void documentAction(id, true); }} onView={id => void documentAction(id)} onAdjust={() => { setFilterOpen(true); void loadFacets(); }} /> : null}
      </section>
      {!summaryHidden ? <aside className={styles.evidenceInspector} aria-labelledby="evidence-summary-title"><header><h2 id="evidence-summary-title">{t("证据摘要")}</h2><button type="button" aria-label={t("关闭证据摘要")} onClick={() => setSummaryHidden(true)}><X size={18} /></button></header>{selected ? <EvidenceSummary key={`${selected.id}:${selected.excerpt}`} item={selected} returnTo={returnTo(selected)} onContext={() => void openContext(selected)} /> : <p className={styles.help}>{t("选择结果可查看来源、页码和原文。")}</p>}</aside> : null}
    </div>
    <div className={styles.inspector} aria-label={t("相关知识与策展推荐")}>
        <section id="discovery-entities"><header><h2>{t("相关知识")}</h2><span>{result?.entities.length || 0}</span></header><p className={styles.help}>{t("相关学者、理论与主题。观点出处请核对原文。")}</p>{result?.entities.map(item => <DiscoveryEntityCard key={`${item.kind}-${item.id}`} item={item} />)}{!result?.entities.length ? <p className={styles.sideEmpty}>{isRunning ? t("知识通道正在查找。") : initialQuery ? t("本次暂无相关知识入口。") : t("检索后在这里查看相关知识。")}</p> : null}</section>
        <section id="discovery-curation"><header><h2>{t("策展推荐")}</h2><span>{result?.curation.length || 0}</span></header><p className={styles.help}>{t("管理员已发布的导读和推荐理由，独立标明来源。")}</p>{result?.curation.map(item => <DiscoveryCurationCard key={item.id} item={item} />)}{!result?.curation.length ? <p className={styles.sideEmpty}>{isRunning ? t("策展通道正在查找。") : initialQuery ? t("本次暂无相关策展推荐。") : t("检索后在这里查看阅读推荐。")}</p> : null}</section>
        <DiscoveryCoverageDetails result={result} />
    </div>
    <Dialog open={summaryOpen && Boolean(selected)} onRequestClose={() => setSummaryOpen(false)} className={styles.summaryDialog} aria-labelledby="mobile-evidence-summary"><header className={styles.dialogHeader}><h2 id="mobile-evidence-summary">{t("证据摘要")}</h2><button type="button" onClick={() => setSummaryOpen(false)} aria-label={t("关闭证据摘要")}><X size={20} /></button></header>{selected ? <EvidenceSummary key={`${selected.id}:${selected.excerpt}`} item={selected} returnTo={returnTo(selected)} onContext={() => { setSummaryOpen(false); void openContext(selected); }} /> : null}</Dialog>
    <Dialog open={Boolean(contextItem)} onRequestClose={closeContext} className={styles.contextDialog} aria-labelledby="discovery-context-title"><header className={styles.dialogHeader}><h2 id="discovery-context-title">{t("原文上下文")}</h2><button type="button" aria-label={t("关闭上下文")} onClick={closeContext}><X size={21} /></button></header><div className={styles.contextBody}>{contextBusy ? <LoadingState variant="compact">{t("正在读取原文上下文……")}</LoadingState> : contextError ? <div role="alert"><p>{t(contextError)}</p><button type="button" className="button secondary" onClick={() => contextItem && void openContext(contextItem)}>{t("重试读取上下文")}</button></div> : context && contextItem ? <EvidenceContextBody key={context.result_id} item={contextItem} context={context} returnTo={returnTo(contextItem)} onOpenCandidate={item => void openContext(item)} /> : null}</div></Dialog>
  </div></SavedWorkStatusProvider>;

}

export function DiscoveryPassageCard({ item, index, onContext }: { item: DiscoveryPassage; index: number; onContext: () => void }) {
  const { t } = useEvidenceLanguage();
  const reader = internalHref(item.reader_url);
  const isOcr = /ocr/i.test(item.source_kind);
  return <article className={styles.evidenceCard} id={`material-${item.id}`}>
    <header><span className={styles.resultNumber}>{String(index + 1).padStart(2, "0")}</span><div><p>{item.authors?.length ? item.authors.join("、") : t("责任者待核对")}</p><h3>{item.work.slug ? <CollectionLink href={`/works/${encodeURIComponent(item.work.slug)}`}>{item.work.title}</CollectionLink> : item.work.title}</h3></div><span className={styles.sourceTag}>{isOcr ? t("OCR 原文") : t("原文材料")}</span></header>
    <blockquote><Quote size={18} aria-hidden="true" /><p><SourceText text={item.excerpt} /></p></blockquote>
    <div className={styles.locator}><span>{t("PDF 第 {page} 页", { page: item.pdf_page })}</span>{item.printed_page && item.printed_page !== String(item.pdf_page) ? <span>{t("印刷页 {page}", { page: item.printed_page })}</span> : null}<span>{item.locator_precision === "exact" ? t("原文定位") : t("按页定位")}</span></div>
    {isOcr ? <p className={styles.help}>{t("文字来自 OCR 识别，可回到扫描画面核对。")}</p> : null}
    {item.match_basis?.length ? <p className={styles.reason}>{item.match_basis.join(" · ")}</p> : null}
    <footer><section data-content-section><header data-section-heading>{t("来源与版本")}</header><dl><div><dt>{t("正文修订")}</dt><dd>{item.document_revision_id || t("未提供")}</dd></div><div><dt>{t("源文件")}</dt><dd>{item.asset_id}</dd></div></dl></section><div className={styles.actions}><button className="button secondary" type="button" onClick={onContext}>{t("查看上下文")}</button>{reader ? <Link className="button secondary" href={reader}>{t("阅读原文")}<ArrowRight size={14} /></Link> : <span>{t("阅读定位暂不可用")}</span>}</div></footer>
  </article>;
}

export function DiscoveryEntityCard({ item }: { item: DiscoveryEntity }) {
  const { t } = useEvidenceLanguage();
  const href = internalHref(item.url);
  const [failedPortrait, setFailedPortrait] = useState("");
  const fallback = item.kind === "scholar" || item.kind === "scholar_profile" ? <ScholarPortraitFallback name={item.title} identity={href || item.id} className={styles.scholarFallback}/> : null;
  return <article className={styles.entityCard}>{item.portrait_url && failedPortrait !== item.portrait_url ? <MediaPlacement uses={item.portrait_media?.display_uses} fallback={fallback}><img src={normalizePublicResourceUrl(item.portrait_url)} alt="" width={48} height={60} loading="lazy" onError={() => setFailedPortrait(item.portrait_url || "")} /></MediaPlacement> : fallback}<div><small>{t(kindLabels[item.kind] || "知识条目")}</small><h3>{href ? <CollectionLink href={href}>{item.title}<ArrowRight size={12} /></CollectionLink> : item.title}</h3>{item.excerpt ? <p>{item.excerpt}</p> : null}{item.match_basis?.length ? <small>{item.match_basis.join(" · ")}</small> : null}</div></article>;
}

export function DiscoveryCurationCard({ item, preview = false }: { item: DiscoveryCuration; preview?: boolean }) {
  const { t } = useEvidenceLanguage();
  const href = internalHref(item.url);
  return <article className={styles.curationCard}><span className={styles.sourceTag}>{preview ? t("策展推荐 · 草稿预览") : t("策展推荐")}</span><h3>{item.title || item.source_title}</h3><p>{item.recommendation_excerpt}</p><small>{t("来源：")}{item.source_title}</small>{item.match_basis?.length ? <small>{item.match_basis.join(" · ")}</small> : null}{href && !preview ? <CollectionLink className="text-link" href={href}>{t("阅读完整策展")}<ArrowRight size={13} /></CollectionLink> : null}</article>;
}

function DiscoveryDeepProgress({ result }: { result: DiscoverySearch }) {
  const { t } = useEvidenceLanguage();
  const deep = result.task_progress?.deep;
  if (!deep || ["disabled", "skipped"].includes(result.channels?.deep?.status || "")) return null;
  return <div className={styles.help} role="status" aria-live="polite">
    <strong>{t(deepStatusLabels[deep.status] || "深度阶段")}</strong>
    {deep.notice ? <span> · {deep.notice}</span> : null}
    {deep.completed < deep.total && deep.total > 0 ? <span>（{deep.completed}/{deep.total}）</span> : null}
  </div>;
}

function DiscoveryCoverageDetails({ result }: { result: DiscoverySearch | null }) {
  const { t } = useEvidenceLanguage();
  const coverage = result?.coverage_summary;
  return <section className={styles.coverage}><section data-content-section><header data-section-heading>{t("本次检索覆盖")}</header>{coverage?.message ? <p>{coverage.message}</p> : !result ? <p>{t("开始检索后显示实际覆盖状态。")}</p> : null}{coverage?.partial ? <p>{t("当前仍有文献等待文本或索引更新，本次检索覆盖尚未完整。")}</p> : null}<dl>{discoveryCoverageRows(coverage).map(({ key, label, value }) => <div key={key}><dt>{t(label)}</dt><dd>{value}</dd></div>)}</dl><p>{t("覆盖只说明当前可检索的资料范围，不表示已经找齐所有相关论证。")}</p>{result?.corpus_version ? <p className={styles.version}>{t("资料版本")}{result.corpus_version}</p> : null}</section></section>;
}
