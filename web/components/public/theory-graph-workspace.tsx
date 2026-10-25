"use client";

import Link from "next/link";
import { MediaPlacement } from "@/components/media-placement";
import { useEffect, useEffectEvent, useId, useRef, useState, useSyncExternalStore, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, BookOpen, ChevronDown, Filter, LoaderCircle, LockKeyhole, Share2 } from "lucide-react";
import { ApiRequestError, apiRequest, subscribeToSessionChanges } from "@/lib/api";
import { CollectionLink } from "@/components/collection-link";
import { Dialog } from "@/components/ui/dialog";
import { graphFilterKeys, graphHref, graphKindLabels, graphNodeLabels, graphParams, graphParamsForView, type GraphEdge, type GraphKind, type GraphMode, type GraphNode, type GraphParams, type GraphViewState, type PublicTheoryGraph } from "@/lib/api/graph.types";
import { GraphCanvas } from "./graph-canvas";
import { GraphCenterSearch, GraphDisciplineFilter } from "./graph-center-search";
import { GraphInspector } from "./graph-inspector";
import { GraphSavedViews } from "./graph-saved-views";
import styles from "./theory-graph.module.css";

const modes: { value: GraphMode; label: string }[] = [{ value: "graph", label: "关系图谱" }, { value: "list", label: "关系列表" }, { value: "topics", label: "相关主题" }, { value: "scholars", label: "相关学者" }, { value: "works", label: "相关文献" }];
function subscribeMobile(callback: () => void) { const media = window.matchMedia("(max-width: 760px)"); media.addEventListener("change", callback); return () => media.removeEventListener("change", callback); }
const mobileSnapshot = () => window.matchMedia("(max-width: 760px)").matches;
const serverSnapshot = () => false;
const number = (value: string | undefined, fallback: number) => value !== undefined && Number.isFinite(Number(value)) ? Number(value) : fallback;
const choices = (value: string | undefined) => value?.split(",").filter(Boolean) || [];

export function TheoryGraphWorkspace({ initialGraph, initialParams, initialError, initialSavedView = "" }: { initialGraph: PublicTheoryGraph | null; initialParams: GraphParams; initialError: string; initialSavedView?: string }) {
  const mobile = useSyncExternalStore(subscribeMobile, mobileSnapshot, serverSnapshot), tabId = useId();
  const [graph, setGraph] = useState(initialGraph), [applied, setApplied] = useState(initialParams), [draft, setDraft] = useState(initialParams);
  const [selectedNode, setSelectedNode] = useState(initialParams.selected_node || initialGraph?.selected_node || initialGraph?.center || "");
  const [selectedEdge, setSelectedEdge] = useState(initialParams.selected_edge || ""), [inspectorOpen, setInspectorOpen] = useState(true), [drawerOpen, setDrawerOpen] = useState(Boolean(initialParams.selected_node || initialParams.selected_edge));
  const [modeChoice, setMode] = useState<GraphMode | null>(modes.some(row => row.value === initialParams.view) ? initialParams.view as GraphMode : null);
  const centerKind = graph?.nodes.find(row => row.id === graph.center)?.kind || applied.center_kind;
  const focusedMap = centerKind === "topic" || centerKind === "scholar";
  const mode = modeChoice || (mobile && centerKind === "topic" ? "list" : "graph");
  const [zoom, setZoom] = useState(Math.max(.15, Math.min(4, number(initialParams.zoom, 1))));
  const [offset, setOffset] = useState({ x: number(initialParams.offset_x, 0), y: number(initialParams.offset_y, 0) });
  const [busy, setBusy] = useState(false), [error, setError] = useState(initialError), [notice, setNotice] = useState("");
  const [awaitingSaved, setAwaitingSaved] = useState(Boolean(initialSavedView));
  const [shareUrl, setShareUrl] = useState(""), [previousCenters, setPreviousCenters] = useState<GraphParams[]>([]);
  const operation = useRef<AbortController | null>(null), generation = useRef(0), lastAttempt = useRef(initialParams);
  const center = graph?.nodes.find(row => row.id === graph.center), node = graph?.nodes.find(row => row.id === selectedNode), edge = graph ? [...graph.edges, ...graph.candidate_edges].find(row => row.id === selectedEdge) : undefined;
  const savedView: GraphViewState | null = graph && center ? { center_kind: center.kind, center: center.entity_id, depth: graph.depth, limit: graph.limit, edge_limit: graph.edge_limit, node_type: graph.filters.node_type, relation_type: graph.filters.relation_type, discipline: graph.filters.discipline, start_year: graph.filters.start_year, end_year: graph.filters.end_year, has_collection: graph.filters.has_collection, selected_node: selectedNode, selected_edge: graph.edges.some(row => row.id === selectedEdge) ? selectedEdge : "", view_mode: mode, zoom, offset } : null;

  async function read(next: GraphParams, history: "push" | "replace" | "none" = "push", restore?: GraphViewState) {
    setAwaitingSaved(false);
    operation.current?.abort(); const controller = new AbortController(), version = ++generation.current;
    operation.current = controller; lastAttempt.current = next; setBusy(true); setError(""); setNotice(""); setShareUrl("");
    if (restore) { setGraph(null); setApplied(next); setDraft(next); }
    const query = new URLSearchParams(); for (const key of graphFilterKeys) if (next[key]) query.set(key, next[key]);
    try {
      const value = await apiRequest<PublicTheoryGraph>(`/catalog/theory-system/graph/${query.size ? `?${query}` : ""}`, { cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]) });
      if (controller.signal.aborted || version !== generation.current) return;
      const requestedNode = restore?.selected_node || next.selected_node || value.selected_node || value.center || "";
      const validNode = value.nodes.some(row => row.id === requestedNode) ? requestedNode : value.center || "";
      const requestedEdge = restore?.selected_edge || next.selected_edge || "", validEdge = [...value.edges, ...value.candidate_edges].some(row => row.id === requestedEdge) ? requestedEdge : "";
      setGraph(value); setApplied(next); setDraft(next); setSelectedNode(validNode); setSelectedEdge(validEdge);
      if (restore) { setZoom(Math.max(.15, Math.min(4, restore.zoom))); setOffset(restore.offset); setMode(restore.view_mode); }
      if (requestedNode && requestedNode !== validNode || requestedEdge && requestedEdge !== validEdge) setNotice("原选中对象已不在当前公开范围，已回到中心节点。");
      if (history !== "none") window.history[history === "push" ? "pushState" : "replaceState"]({}, "", graphHref(next));
    } catch (failure) {
      if (controller.signal.aborted || version !== generation.current) return;
      setError(failure instanceof ApiRequestError && [400, 404].includes(failure.status) ? "当前中心或筛选范围不可用，请调整条件或重新选择公开条目。" : failure instanceof Error ? failure.message : "关系暂时无法读取，请重试。");
    } finally { if (!controller.signal.aborted && version === generation.current) setBusy(false); }
  }
  const restoreHistory = useEffectEvent(() => {
    if (window.location.pathname !== "/theories/graph") return;
    const next = graphParams(Object.fromEntries(new URLSearchParams(window.location.search)));
    setMode(modes.some(row => row.value === next.view) ? next.view as GraphMode : null);
    setZoom(Math.max(.15, Math.min(4, number(next.zoom, 1)))); setOffset({ x: number(next.offset_x, 0), y: number(next.offset_y, 0) });
    void read(next, "none");
  });
  const resetSession = useEffectEvent(() => {
    setGraph(null); setSelectedNode(""); setSelectedEdge(""); setDrawerOpen(false);
    if (awaitingSaved) { generation.current += 1; operation.current?.abort(); setBusy(false); return; }
    void read({ ...applied, include_candidates: "", selected_edge: "" }, "replace");
  });
  useEffect(() => {
    const unsubscribe = subscribeToSessionChanges(() => resetSession());
    const pop = () => restoreHistory(); window.addEventListener("popstate", pop);
    return () => { generation.current += 1; operation.current?.abort(); unsubscribe(); window.removeEventListener("popstate", pop); };
  }, []);
  function cancel() { generation.current += 1; operation.current?.abort(); setBusy(false); setNotice(graph ? "已取消本次读取，保留上次已加载的范围。" : "已取消本次读取，选择条件仍保留，可重试读取。"); }
  function chooseNode(row: GraphNode) {
    setSelectedNode(row.id); setSelectedEdge(""); setInspectorOpen(true); setDrawerOpen(true);
    void read({ ...applied, selected_node: row.id, selected_edge: "", works_page: "" });
  }
  function chooseEdge(row: GraphEdge) {
    setSelectedEdge(row.id); setInspectorOpen(true); setDrawerOpen(true);
    window.history.replaceState({}, "", graphHref(applied, { selected_node: selectedNode, selected_edge: row.id, view: mode }));
  }
  function changeCenter(kind: GraphKind, id: string) {
    setPreviousCenters(previous => [...previous.slice(-19), applied]); setSelectedEdge(""); setZoom(1); setOffset({ x: 0, y: 0 }); setDrawerOpen(false);
    void read({ ...applied, center_kind: kind, center: id, selected_node: "", selected_edge: "", works_page: "" });
  }
  function changeMode(next: GraphMode) { setMode(next); setApplied(previous => ({ ...previous, view: next })); setDraft(previous => ({ ...previous, view: next })); window.history.replaceState({}, "", graphHref(applied, { view: next, selected_node: selectedNode, selected_edge: selectedEdge })); }
  function apply(event: FormEvent) { event.preventDefault(); setDrawerOpen(false); void read({ ...draft, selected_node: "", selected_edge: "", works_page: "" }); }
  function toggle(key: "node_type" | "relation_type", value: string, checked: boolean) { setDraft(previous => ({ ...previous, [key]: (checked ? [...new Set([...choices(previous[key]), value])] : choices(previous[key]).filter(item => item !== value)).join(",") })); }
  async function share() {
    if (!savedView) return;
    const publicParams = graphParamsForView(savedView), url = new URL(graphHref(publicParams), window.location.origin).href;
    setShareUrl(url);
    try { await navigator.clipboard.writeText(url); setNotice("公开图谱链接已复制。"); }
    catch { setNotice("浏览器未允许复制，请从下方选择并复制链接。"); }
  }
  const inspector = graph ? <GraphInspector key={edge?.id || node?.id || "none"} graph={graph} node={node} edge={edge} onNode={chooseNode} onEdge={chooseEdge} onCenter={row => changeCenter(row.kind, row.entity_id)} onClose={() => { setInspectorOpen(false); setDrawerOpen(false); }} disabled={busy} /> : null;
  const filteredNodes = graph?.nodes.filter(row => mode === "topics" ? row.kind === "topic" : mode === "scholars" ? row.kind === "scholar" : true) || [];
  return <div className={styles.page} data-graph-kind={centerKind || "overview"}>
    <header className={styles.hero}><div><nav aria-label="面包屑"><Link href="/">首页</Link><span>›</span><Link href="/explore">探索</Link><span>›</span><span>知识地图与学科目录</span></nav><h1>{centerKind === "topic" ? "知识地图" : "知识地图与学科目录"}</h1><p>在局部关系中找方向，并能从图回到叙事、目录与原文。</p></div>{!focusedMap ? <img src="/visual/stl4/graph/hero-final-r2.png" alt="" width={608} height={177} /> : null}</header>
    <div className={styles.topbar}><nav aria-label="知识探索视图"><span aria-current="page">知识地图</span><Link href="/theories/directory">目录视图</Link><button type="button" onClick={() => { if (graph?.edges.length) chooseEdge(graph.edges[0]); else changeMode("list"); }}>关系依据</button></nav><div className={styles.toolbarActions}><GraphSavedViews view={savedView} title={center ? `${center.name}的关系图` : "我的知识地图"} initialSavedView={initialSavedView} onRestore={view => void read(graphParamsForView(view), "replace", view)} disabled={busy || !graph} /><button className={styles.outlineButton} type="button" disabled={!savedView || busy} onClick={() => void share()}><Share2 size={15} />分享链接</button>{center ? <Link className={styles.primaryButton} href={center.href}>进入条目<ArrowRight size={14} /></Link> : null}</div></div>
    {notice ? <p role="status" className={styles.status}>{notice}</p> : null}
    {shareUrl ? <label className={styles.shareLink}>公开图谱链接<input value={shareUrl} readOnly onFocus={event => event.currentTarget.select()} /></label> : null}
    <div className={styles.workspace}>
      <aside className={styles.sidebar}>
        <GraphCenterSearch disabled={busy} onSelect={changeCenter} />
        {center ? <section className={styles.currentNode}><h2>当前中心节点</h2><div>{center.image_url ? <MediaPlacement uses={center.image_media?.display_uses} fallback={<span className={styles.nodePlaceholder}><BookOpen size={24}/></span>}><img src={center.image_url} alt="" /></MediaPlacement> : <span className={styles.nodePlaceholder}><BookOpen size={24} /></span>}<span><strong>{center.name}</strong><small>{graphNodeLabels[center.node_type] || graphKindLabels[center.kind]}</small></span></div>{center.summary ? <p>{center.summary}</p> : null}<Link className={styles.outlineButton} href={center.href}>查看简介<ArrowRight size={14} /></Link></section> : null}
        <details className={styles.filterDisclosure} open={!mobile}><summary><Filter size={15} />关系类型与范围<ChevronDown size={15} /></summary><form onSubmit={apply} aria-label="图谱范围筛选">
          <fieldset><legend>关系类型</legend>{graph?.relation_types.length ? <><p className={styles.muted}>未勾选时显示全部正式关系</p><div className={styles.checks}>{graph.relation_types.map(type => <label key={type.value}><input type="checkbox" checked={choices(draft.relation_type).includes(type.value)} onChange={event => toggle("relation_type", type.value, event.target.checked)} />{type.label}</label>)}</div></> : <p className={styles.muted}>读取关系后可按类型筛选。</p>}</fieldset>
          <fieldset><legend>范围层级</legend><div className={styles.depth}>{[1, 2, 3].map(value => <label key={value}><input type="radio" name="depth" value={value} checked={Number(draft.depth || 1) === value} onChange={() => setDraft(previous => ({ ...previous, depth: String(value) }))} /><span>{value} 层邻居</span></label>)}</div></fieldset>
          <details className={styles.additionalFilters}><summary>更多范围条件<ChevronDown size={13} /></summary><fieldset><legend>理论节点类型</legend><div className={styles.checks}>{Object.entries(graphNodeLabels).map(([value, label]) => <label key={value}><input type="checkbox" checked={choices(draft.node_type).includes(value)} onChange={event => toggle("node_type", value, event.target.checked)} />{label}</label>)}</div></fieldset>
            <GraphDisciplineFilter value={draft.discipline || ""} onChange={value => setDraft(previous => ({ ...previous, discipline: value }))} />
            <label>起始年份<input type="number" min={-32768} max={32767} value={draft.start_year || ""} onChange={event => setDraft(previous => ({ ...previous, start_year: event.target.value }))} /></label><label>结束年份<input type="number" min={-32768} max={32767} value={draft.end_year || ""} onChange={event => setDraft(previous => ({ ...previous, end_year: event.target.value }))} /></label>
            <label>馆藏依据<select value={draft.has_collection || ""} onChange={event => setDraft(previous => ({ ...previous, has_collection: event.target.value }))}><option value="">不限</option><option value="true">有公开馆藏</option><option value="false">无公开馆藏</option></select></label>
            <label>节点上限<select value={draft.limit || "60"} onChange={event => setDraft(previous => ({ ...previous, limit: event.target.value }))}>{[30, 60, 120].map(value => <option key={value} value={value}>{value}</option>)}</select></label>
            <label>关系上限<select value={draft.edge_limit || "150"} onChange={event => setDraft(previous => ({ ...previous, edge_limit: event.target.value }))}>{[75, 150, 300].map(value => <option key={value} value={value}>{value}</option>)}</select></label>
            {draft.discipline ? <p className={styles.scopeNote}>当前限定学科范围<button type="button" onClick={() => setDraft(previous => ({ ...previous, discipline: "" }))}>移除学科限制</button></p> : null}
            {graph?.filters.scope_note ? <p className={styles.muted}>{graph.filters.scope_note}</p> : null}
          </details>
          <button className={styles.primaryButton} type="submit" disabled={busy}>应用范围<ArrowRight size={14} /></button><button className={styles.outlineButton} type="button" disabled={busy || !graph || graph.depth >= 3} onClick={() => void read({ ...applied, depth: String((graph?.depth || 1) + 1), selected_node: "", selected_edge: "", works_page: "" })}>展开一层关系<ArrowRight size={14} /></button>
          <button className={styles.outlineButton} type="button" disabled={busy || !previousCenters.length} onClick={() => { const previous = previousCenters.at(-1); if (previous) { setPreviousCenters(rows => rows.slice(0, -1)); void read(previous); } }}><ArrowLeft size={14} />返回之前中心</button>
          <button className={styles.clearButton} type="button" disabled={busy} onClick={() => void read(center ? { center_kind: center.kind, center: center.entity_id } : {})}>清空范围筛选</button>
        </form></details>
        <div className={styles.candidateNotice}><LockKeyhole size={15} /><p>候选关系尚待审核，公开图谱只展示已发布的关系。</p>{graph?.candidate_access.can_review ? <><label><input type="checkbox" checked={graph.filters.include_candidates} disabled={busy} onChange={event => void read({ ...applied, include_candidates: event.target.checked ? "true" : "", selected_edge: "" })} />查看待审核候选</label>{graph.candidate_count !== null ? <p>已显示 {graph.candidate_edges.length} 条待审核关系{graph.candidates_truncated ? "，仍有更多候选" : ""}。</p> : null}{graph.candidate_access.review_href ? <Link href={graph.candidate_access.review_href}>进入候选关系审核<ArrowRight size={13} /></Link> : null}</> : null}</div>
      </aside>
      <div className={styles.mainColumn}>
        <nav className={styles.viewTabs} role="tablist" aria-label="图谱显示内容">{modes.map((row, index) => <button key={row.value} id={`${tabId}-${row.value}`} type="button" role="tab" aria-controls={`${tabId}-panel`} aria-selected={mode === row.value} tabIndex={mode === row.value ? 0 : -1} onClick={() => changeMode(row.value)} onKeyDown={event => { const next = event.key === "ArrowRight" ? (index + 1) % modes.length : event.key === "ArrowLeft" ? (index + modes.length - 1) % modes.length : event.key === "Home" ? 0 : event.key === "End" ? modes.length - 1 : -1; if (next >= 0) { event.preventDefault(); changeMode(modes[next].value); event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('button')[next]?.focus(); } }}>{row.label}</button>)}</nav>
        <div className={styles.graphHeading}><h2>{mode === "graph" ? "知识关系图" : modes.find(row => row.value === mode)?.label}</h2>{graph ? <p>当前显示 {graph.depth} 层邻居 · {graph.counts.nodes} 个节点 · {graph.counts.edges} 条关系</p> : null}</div>
        {error ? <section role="alert" className={styles.error}><h3>当前图谱未能读取</h3><p>{error}</p>{graph ? <p>下方保留上次成功读取的范围。</p> : null}<button type="button" disabled={busy} onClick={() => void read(lastAttempt.current, "replace")}>重试读取</button><button type="button" disabled={busy} onClick={() => void read({})}>重新选择公开范围</button></section> : null}
        {graph?.truncated ? <p className={styles.scopeNote}>当前范围达到节点或关系上限，仅展示已读取的局部关系。请缩小范围，或在更多条件中提高上限。</p> : null}
        <div className={styles.contentPanel} role="tabpanel" id={`${tabId}-panel`} aria-labelledby={`${tabId}-${mode}`} tabIndex={0} aria-busy={busy}>
          {graph ? graph.state === "empty" ? <div className={styles.empty}><BookOpen size={28} /><h3>尚无符合条件的公开节点</h3><p>可调整筛选，或从左侧选择其他公开条目。</p></div> : <>
            {mode === "graph" ? <GraphCanvas graph={graph} selectedNode={selectedNode} selectedEdge={selectedEdge} onNode={chooseNode} onEdge={chooseEdge} zoom={zoom} offset={offset} onTransform={(nextZoom, nextOffset) => { setZoom(nextZoom); setOffset(nextOffset); }} /> : mode === "list" ? <ul className={styles.relationList}>{graph.edges.map(row => { const source = graph.nodes.find(item => item.id === row.source), target = graph.nodes.find(item => item.id === row.target); return <li key={row.id}><button type="button" aria-pressed={row.id === selectedEdge} onClick={() => chooseEdge(row)}><span><strong>{source?.name}</strong><i>{row.direction === "undirected" ? "—" : row.direction === "bidirectional" ? "↔" : "→"}</i><strong>{target?.name}</strong></span><small>{row.relation_label}</small><ArrowRight size={14} /></button></li>; })}</ul> : mode === "works" ? <>
              <p className={styles.muted}>{graph.nodes.find(row => row.id === graph.selected_node)?.name || "当前节点"}的公开馆藏 · 共 {graph.related_works_count} 个版本</p>
              {graph.related_works.length ? <ul className={styles.workCards}>{graph.related_works.map(work => <li key={work.edition_id || work.id}>{work.cover_url ? <MediaPlacement uses={work.cover_media?.display_uses} fallback={<BookOpen size={25}/>}><img src={work.cover_url} alt="" /></MediaPlacement> : <BookOpen size={25} />}<div><strong>{work.title}</strong>{work.version_label ? <small>{work.version_label}</small> : null}<p>{work.author}</p><small>{work.year ?? "出版年份未详"}{work.publisher ? ` · ${work.publisher}` : ""}</small><div>{work.detail_href ? <Link href={work.detail_href}>查看此版书目<ArrowRight size={12} /></Link> : null}{work.reader_href ? <CollectionLink href={work.reader_href}>阅读原文</CollectionLink> : <span>原文当前不可用</span>}</div></div></li>)}</ul> : <p className={styles.empty}>尚无与此节点正式关联的公开馆藏版本。</p>}
              {graph.related_works_total_pages > 1 ? <nav className={styles.pagination} aria-label="图谱相关文献分页"><button type="button" disabled={busy || graph.related_works_page <= 1} onClick={() => void read({ ...applied, selected_node: graph.selected_node || "", works_page: String(graph.related_works_page - 1) })}>上一页</button><span>{graph.related_works_page} / {graph.related_works_total_pages}</span><button type="button" disabled={busy || graph.related_works_page >= graph.related_works_total_pages} onClick={() => void read({ ...applied, selected_node: graph.selected_node || "", works_page: String(graph.related_works_page + 1) })}>下一页</button></nav> : null}
            </> : filteredNodes.length ? <ul className={styles.nodeCards}>{filteredNodes.map(row => <li key={row.id}><button type="button" onClick={() => chooseNode(row)}>{row.image_url ? <MediaPlacement uses={row.image_media?.display_uses} fallback={<BookOpen size={24}/>}><img src={row.image_url} alt="" /></MediaPlacement> : <span className={styles.nodePlaceholder}><BookOpen size={24} /></span>}<span><strong>{row.name}</strong><small>{row.summary || graphKindLabels[row.kind]}</small></span><ArrowRight size={14} /></button></li>)}</ul> : <p className={styles.empty}>当前范围内没有已公开的{mode === "topics" ? "主题" : "学者"}。</p>}
            {["isolated", "filtered"].includes(graph.state) && ["graph", "list"].includes(mode) ? <p className={styles.empty}>{graph.state === "filtered" ? "当前关系类型下没有关联记录，请调整筛选。" : "当前范围内尚无已发布的关系，可以继续查看中心条目。"}</p> : null}
            {mode === "list" && graph.candidate_count !== null ? <section className={styles.candidateList} aria-label="待审核候选关系列表"><h3><LockKeyhole size={15} />待审核候选关系</h3><p>以下连接尚未公开，不计入正式关系数量。</p><ul className={styles.relationList}>{graph.candidate_edges.map(row => <li key={row.id}><button type="button" aria-pressed={selectedEdge === row.id} onClick={() => chooseEdge(row)}><span><strong>{graph.nodes.find(item => item.id === row.source)?.name}</strong><i>{row.direction === "undirected" ? "—" : row.direction === "bidirectional" ? "↔" : "→"}</i><strong>{graph.nodes.find(item => item.id === row.target)?.name}</strong></span><small>{row.relation_label} · 待审核</small><ArrowRight size={14} /></button></li>)}</ul>{!graph.candidate_edges.length ? <p>当前范围没有可查看的候选关系。</p> : null}</section> : null}
          </> : !error ? <p className={styles.empty}>{awaitingSaved ? "等待核对当前账户并读取本人保存的视图。也可从左侧重新选择公开中心。" : "选择公开中心后查看实际关系。"}</p> : null}
          {busy ? <div className={styles.loadingOverlay} role="status"><LoaderCircle size={26} /><h3>正在读取知识关系…</h3><p>保留当前范围，完成后更新图谱。</p><button type="button" onClick={cancel}>取消读取</button></div> : null}
        </div>
        {graph && mode !== "topics" && mode !== "scholars" && graph.nodes.length > 1 ? <section className={styles.relatedEntries} aria-label="当前图谱条目"><header><h2>相关条目 <small>{graph.nodes.length - 1}</small></h2><button type="button" onClick={() => { setInspectorOpen(true); setDrawerOpen(true); }}>查看所选详情<ArrowRight size={14} /></button></header><ul>{graph.nodes.filter(row => !row.is_center).map(row => <li key={row.id}><button type="button" onClick={() => chooseNode(row)}>{row.image_url ? <MediaPlacement uses={row.image_media?.display_uses} fallback={<BookOpen size={24}/>}><img src={row.image_url} alt="" /></MediaPlacement> : <BookOpen size={23} />}<span><strong>{row.name}</strong><small>{graphNodeLabels[row.node_type] || graphKindLabels[row.kind]}</small></span><ArrowRight size={13} /></button></li>)}</ul></section> : null}
      </div>
      {!mobile && inspectorOpen ? <aside className={styles.detailColumn}>{inspector}</aside> : null}
    </div>
    {mobile ? <Dialog className={styles.mobileDrawer} open={drawerOpen && !!graph} onRequestClose={() => setDrawerOpen(false)} aria-label="图谱详情">{inspector}</Dialog> : null}
  </div>;
}
