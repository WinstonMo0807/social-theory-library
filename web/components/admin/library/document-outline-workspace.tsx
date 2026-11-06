"use client";

import { createRequestKey } from "../../../lib/request-key";
import Link from "next/link";
import { BookOpen, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Plus, RefreshCw, Search, Trash2, GripVertical } from "lucide-react";
import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { useAdminSession, hasAdminCapability } from "@/lib/admin-session";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { normalizePublicResourceUrl } from "@/lib/api";
import { useDocumentOutline } from "@/lib/api/use-persistent-workspace";
import { actOnOutlineJob, correctOutline, readOutlineState, rebuildOutline, type OutlineRevision, type OutlineState } from "@/lib/api/curation-workspace.client";
import { filterOutline, outlinePosition } from "@/lib/api/document-outline";
import { isTaskRunning } from "@/lib/api/task-polling";
import { Dialog } from "@/components/ui/dialog";
import { downloadWorkFile } from "./work-file-preview";
import { OutlinePdfPreview } from "./outline-pdf-preview";
import { OutlineDiagnostics } from "./outline-diagnostics";
import { editableOutline, moveOutlineSibling, orderOutline, outlineCommandNodes, outlineDescendants, outlineSourceLabels, outlineStatusLabels, type EditableOutlineNode } from "./outline-edit-state";
import styles from "./document-outline.module.css";

type Draft = { revision: OutlineRevision | null; expected: number; nodes: EditableOutlineNode[] };
type Confirmation = { kind: "discard" } | { kind: "delete"; id: string } | { kind: "resave"; expected: number };
const jobLabels: Record<string, string> = { pending: "等待处理", queued: "等待处理", running: "正在处理", succeeded: "已完成", completed: "已完成", failed: "处理失败", cancelled: "已取消", canceled: "已取消", paused: "已暂停" };
const confirmed = (node: EditableOutlineNode) => Boolean(node.pdf_page && ["native", "confirmed", "matched", "generated"].includes(node.calibration_status || ""));
const date = (value: string) => new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" });

export function DocumentOutlineWorkspace({ assetId }: { assetId: string }) {
  const user = useAdminSession();
  if (!user) return <p role="status">正在核对管理会话……</p>;
  return <OutlineWorkspace key={`${user.id}:${assetId}`} assetId={assetId} ownerId={String(user.id)} canEdit={hasAdminCapability(user, "can_edit_metadata")} canRebuild={hasAdminCapability(user, "can_retry_jobs")} canDownload={hasAdminCapability(user, "can_view_evidence")} />;
}

function OutlineWorkspace({ assetId, ownerId, canEdit: editAllowed, canRebuild: rebuildAllowed, canDownload }: { assetId: string; ownerId: string; canEdit: boolean; canRebuild: boolean; canDownload: boolean }) {
  const resource = useDocumentOutline(assetId, ownerId);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const search = useDeferredValue(query);
  const [onlyUnconfirmed, setOnlyUnconfirmed] = useState(false);
  const [onlySamePage, setOnlySamePage] = useState(false);
  const dragNode=useRef("");
  const [limit, setLimit] = useState(100);
  const [pane, setPane] = useState<"tree" | "edit" | "preview">("tree");
  const [previewPage, setPreviewPage] = useState(1);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [message, setMessage] = useState("");
  const [reading, setReading] = useState(false);
  const editorRef = useRef<HTMLElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const data = resource.data;
  const revision = draft ? draft.revision : data?.active || data?.latest || null;
  const nodes = useMemo(() => draft?.nodes || editableOutline(revision?.nodes || []), [draft, revision]);
  const dirty = Boolean(draft && JSON.stringify(outlineCommandNodes(draft.nodes)) !== JSON.stringify(outlineCommandNodes(editableOutline(draft.revision?.nodes || []))));
  useUnsavedForm(dirty, false);
  const currentNode = nodes.find(node => node.id === selectedId) || nodes[0];
  const currentId = currentNode?.id || "";
  useEffect(() => {
    setPreviewPage(currentNode?.pdf_page || currentNode?.contents_page || 1);
  }, [currentId, currentNode?.pdf_page, currentNode?.contents_page]);
  const stale = Boolean(draft && data && draft.expected !== data.expected_revision);
  const busy = resource.pending || reading;
  const sourceUnavailable = data?.asset?.source_current === false;
  const canEdit = editAllowed && !sourceUnavailable;
  const canRebuild = rebuildAllowed && !sourceUnavailable;
  const descendants = useMemo(() => outlineDescendants(nodes, currentId), [nodes, currentId]);
  const samePage = useMemo(() => {
    const counts = new Map<number, number>();
    for (const node of nodes) if (node.pdf_page) counts.set(node.pdf_page, (counts.get(node.pdf_page) || 0) + 1);
    return counts;
  }, [nodes]);
  const unconfirmed = nodes.filter(node => !confirmed(node));
  const filtered = useMemo(() => filterOutline(nodes, search, collapsed).filter(node => (!onlyUnconfirmed || !confirmed(node)) && (!onlySamePage || (samePage.get(node.pdf_page || 0) || 0) > 1)), [nodes, search, collapsed, onlyUnconfirmed, onlySamePage, samePage]);
  const visible = filtered.slice(0, limit);
  const hasChildren = useMemo(() => new Set(nodes.map(node => node.parent_id).filter(Boolean)), [nodes]);
  const latestNodes = data?.latest?.nodes;
  const conflictDifferences = useMemo(() => {
    if (!stale || !latestNodes) return [];
    const incoming = new Map(editableOutline(latestNodes).map(node => [node.id, node]));
    const local = new Map(nodes.map(node => [node.id, node]));
    return [...new Set([...local.keys(), ...incoming.keys()])].flatMap(id => {
      const mine = local.get(id), latest = incoming.get(id);
      return JSON.stringify(mine && outlineCommandNodes([mine])) === JSON.stringify(latest && outlineCommandNodes([latest])) ? [] : [{ id, mine, latest }];
    });
  }, [stale, latestNodes, nodes]);

  function changeNodes(next: EditableOutlineNode[]) {
    if (!data || !canEdit) return;
    try { setDraft({ revision, expected: draft?.expected ?? data.expected_revision, nodes: orderOutline(next) }); setMessage(""); }
    catch (error) { setMessage(error instanceof Error ? error.message : "目录结构无效。"); }
  }
  function patchNode(patch: Partial<EditableOutlineNode>) {
    changeNodes(nodes.map(node => node.id === currentId ? { ...node, ...patch, calibration_status: "unverified" } : node));
  }
  function selectNode(node: EditableOutlineNode) { setSelectedId(node.id); if (node.pdf_page) setPreviewPage(node.pdf_page); setPane("edit"); }
  function inspectNode(node: EditableOutlineNode) {
    selectNode(node);
    requestAnimationFrame(() => { if (alive.current) editorRef.current?.focus(); });
  }
  function inspectPage(page: number) {
    setPreviewPage(page); setPane("preview");
    requestAnimationFrame(() => { if (alive.current) previewRef.current?.focus(); });
  }
  function dropNode(target:EditableOutlineNode){
    const id=dragNode.current;dragNode.current="";
    const node=nodes.find(row=>row.id===id);
    if(!canEdit||busy||!node||node.id===target.id||node.parent_id!==target.parent_id)return;
    const next=nodes.filter(row=>row.id!==node.id),at=next.findIndex(row=>row.id===target.id);
    next.splice(at,0,node);changeNodes(next);
  }
  function addNode(child = false) {
    const id = createRequestKey();
    const parent = child ? currentId || null : currentNode?.parent_id || null;
    const node: EditableOutlineNode = { id, title: "新目录节点", chapter_title: "", index: 0, level: 1, parent_id: parent, pdf_page: null, printed_label: "", source: "manual", calibration_status: "needs_review" };
    const position = currentNode ? nodes.findLastIndex(row => descendants.has(row.id)) + 1 : nodes.length;
    changeNodes([...nodes.slice(0, position), node, ...nodes.slice(position)]);
    setSelectedId(id); setPane("edit");
    if (parent) setCollapsed(previous => new Set([...previous].filter(value => value !== parent)));
  }
  function loadRevision(next: OutlineRevision | null) {
    if (!data) return;
    setDraft({ revision: next, expected: data.expected_revision, nodes: editableOutline(next?.nodes || []) });
    setSelectedId(next?.nodes?.[0]?.id || ""); setMessage("");
  }
  async function command(fingerprint: string, action: (state: OutlineState, requestId: string) => Promise<OutlineState>, success: string, clearDraft = false) {
    try {
      const result = await resource.mutate(fingerprint, action);
      if (!alive.current || !result) return;
      if (clearDraft) { const active = result.active || result.latest; setDraft({ revision: active, expected: result.expected_revision, nodes: editableOutline(active?.nodes || []) }); }
      setMessage(success); setConfirmation(null);
    } catch { /* The shared workspace retains input and surfaces the authoritative error. */ }
  }
  async function save() {
    if (!data || !dirty || !canEdit || stale) return;
    const body = { expected_revision: draft?.expected ?? data.expected_revision, ...(revision ? { base_revision_id: revision.id } : {}), nodes: outlineCommandNodes(nodes) };
    await command(JSON.stringify(["save", body]), (_, request_id) => correctOutline(assetId, { ...body, request_id }), "目录已更新，书签下载副本正在自动生成。", true);
  }
  async function confirmAction() {
    if (!confirmation || !data) return;
    if (confirmation.kind === "discard") { loadRevision(data.active || data.latest); setConfirmation(null); return; }
    if (confirmation.kind === "delete") {
      const target = nodes.find(node => node.id === confirmation.id);
      changeNodes(nodes.filter(node => node.id !== confirmation.id).map(node => node.parent_id === confirmation.id ? { ...node, parent_id: target?.parent_id || null, calibration_status: "unverified" } : node));
      setSelectedId(""); setConfirmation(null); return;
    }
    if (confirmation.kind === "resave") {
      const body = { expected_revision: confirmation.expected, ...(revision ? { base_revision_id: revision.id } : {}), nodes: outlineCommandNodes(nodes) };
      await command(JSON.stringify(["save", body]), (_, request_id) => correctOutline(assetId, { ...body, request_id }), "修正已保存，下载副本正在更新。", true);
      return;
    }
  }
  if (!data) return <div className={styles.workspace}><h1>目录校准</h1>{resource.error ? <div role="alert"><p>{resource.error}</p><button type="button" onClick={resource.reload}>重新读取</button></div> : <p role="status">正在读取目录与文件信息……</p>}</div>;
  const asset = data.asset;
  const pendingJobs = data.jobs.some(job => isTaskRunning(job.status));
  const currentIndex=nodes.findIndex(node=>node.id===currentId);
  const samePageNodes=nodes.filter(node=>node.id!==currentId&&currentNode?.pdf_page&&node.pdf_page===currentNode.pdf_page);
  const rebuild=()=>void command("rebuild",async(_,requestId)=>{await rebuildOutline(assetId,requestId);return readOutlineState(assetId);},"已提交目录提取任务。原有人工目录继续保留。");
  const position=currentNode?.normalized_position||[];
  const positionValue=position.length?(position[0]===0&&position[1]===.5?"middle":position[0]===0&&position[1]===.75?"lower":"custom"):currentNode?.pdf_position?.length||currentNode?.source_locator?.bbox?"source":"page";
  return <div className={styles.workspace} aria-busy={busy}>
    <div className={styles.topline}><nav className={styles.breadcrumb} aria-label="目录校准位置"><Link href="/admin/processing">文件与处理</Link><ChevronRight size={12}/><span>目录校准</span>{asset?.title?<><ChevronRight size={12}/><span>{asset.title}</span></>:null}</nav><div className={styles.actions}><span className={styles.saveState}>{dirty?"有未保存改动":revision?"已保存":"尚无目录"}{revision?.is_active?" · 已生效":""}</span><button type="button" className={styles.primary} disabled={!canEdit||busy||!dirty||stale} onClick={()=>void save()}>保存修正</button></div></div>
    {onlySamePage?<header className={styles.heading}><div><h1>目录校准</h1></div></header>:<h1 className={styles.srOnly}>目录校准</h1>}
    <section className={styles.book} aria-label="当前文件">
      {asset?.cover_url ? <picture><img src={normalizePublicResourceUrl(asset.cover_url)} alt="当前书目封面" /></picture> : <div className={styles.coverEmpty}><BookOpen size={26} /></div>}
      <div><h2>{asset?.title || "当前阅读文件"}</h2><p>{asset?.authors?.join("、") || "责任者尚未填写"}</p><p>{asset?.publication_year ? `${asset.publication_year} · ` : ""}PDF {asset?.page_count ? ` · ${asset.page_count} 页` : ""}</p>
        {asset?.work_id ? <Link href={`/admin/library/works/${encodeURIComponent(asset.work_id)}?edition=${encodeURIComponent(asset.edition_id)}`}>馆藏信息 <ChevronRight size={11} /></Link> : null}</div>
    </section>
    {resource.error ? <div className={styles.notice} role="alert">{resource.error}<button type="button" disabled={busy} onClick={resource.reload}>重新读取状态</button></div> : null}
    {sourceUnavailable ? <p className={styles.notice} role="alert">{asset?.source_error || "此文件来源已变化，请从馆藏选择当前文件。"}</p> : null}
    {message ? <p className={styles.notice} role="status">{message}</p> : null}
    {stale ? <div className={styles.notice} role="alert">已有其他修改保存，当前输入仍保留。<button type="button" disabled={!canEdit || busy} onClick={() => setConfirmation({ kind: "resave", expected: data.expected_revision })}>核对并保存当前修正</button><button type="button" onClick={() => setConfirmation({ kind: "discard" })}>载入最新目录</button></div> : null}
    <div className={styles.calibrationToolbar}><h2>目录校准</h2><button type="button" disabled={!canRebuild || busy || pendingJobs || dirty} onClick={rebuild}><RefreshCw size={13}/>重新生成目录</button></div>
      <div className={styles.mobilePanes} aria-label="切换目录工作区域"><button type="button" aria-pressed={pane!=="preview"} onClick={()=>setPane("tree")}>目录与节点</button><button type="button" aria-pressed={pane==="preview"} onClick={()=>setPane("preview")}>页面预览</button></div>
      <div className={styles.grid} data-pane={pane}>
        <section className={styles.tree} aria-label="目录树"><header><h2>目录树 <small>共 {nodes.length} 个节点</small></h2><button type="button" aria-label="新增同级节点" disabled={!canEdit || busy} onClick={() => addNode()}><Plus size={14} /></button></header>
          <label className={styles.search}><Search size={14} /><input type="search" aria-label="搜索目录" value={query} placeholder="在目录中搜索…" onChange={event => { setQuery(event.target.value); setLimit(100); }} /></label>
          <div className={styles.filters}><label><input type="checkbox" checked={onlyUnconfirmed} onChange={event => setOnlyUnconfirmed(event.target.checked)} />仅显示待修改节点（{unconfirmed.length}）</label><label><input type="checkbox" checked={onlySamePage} onChange={event => setOnlySamePage(event.target.checked)} />同页多节点</label></div>
          <ul className={styles.nodes}>{visible.map(node => <li key={node.id} data-selected={node.id === currentId} onDragOver={event=>{const source=nodes.find(row=>row.id===dragNode.current);if(canEdit&&!busy&&source&&source.parent_id===node.parent_id)event.preventDefault();}} onDrop={event=>{event.preventDefault();dropNode(node);}} style={{ paddingInlineStart: `${Math.min(node.level - 1, 8) * 12 + 5}px` }}>
            <button type="button" className={styles.dragHandle} draggable={canEdit&&!busy} disabled={!canEdit||busy} aria-label={`拖动调整 ${node.title} 的同级顺序`} onDragStart={event=>{dragNode.current=node.id;event.dataTransfer.effectAllowed="move";event.dataTransfer.setData("application/x-stl-outline-node",node.id);}} onDragEnd={()=>{dragNode.current="";}}><GripVertical size={12}/></button>
            {hasChildren.has(node.id) ? <button type="button" aria-label={`${collapsed.has(node.id) ? "展开" : "收起"} ${node.title}`} aria-expanded={!collapsed.has(node.id)} onClick={() => setCollapsed(previous => { const next = new Set(previous); if (next.has(node.id)) next.delete(node.id); else next.add(node.id); return next; })}>{collapsed.has(node.id) ? <ChevronRight size={12} /> : <ChevronDown size={12} />}</button> : <span className={styles.leaf} />}
            <button type="button" className={styles.node} aria-current={node.id === currentId ? "true" : undefined} onClick={() => selectNode(node)}><span>{node.title}</span><small>{node.printed_label ? `p.${node.printed_label}` : node.pdf_page ? `PDF ${node.pdf_page}` : "待定位"}</small><em data-confirmed={confirmed(node)}>{outlineStatusLabels[node.calibration_status || ""] || "待确认"}</em></button>
          </li>)}</ul>
          {!visible.length ? <p className={styles.empty}>{nodes.length ? "没有符合筛选的节点。" : "尚无可用目录。可重新生成或添加节点。"}</p> : null}
          {filtered.length > limit ? <button type="button" onClick={() => setLimit(value => value + 100)}>继续显示目录（剩余 {filtered.length - limit} 项）</button> : null}
        </section>
        <section ref={editorRef} tabIndex={-1} className={styles.editor} aria-label="节点详情"><header><h2>节点编辑</h2><div><button type="button" aria-label="上一个节点" disabled={currentIndex<=0} onClick={()=>selectNode(nodes[currentIndex-1])}><ChevronLeft size={12}/>上一个</button><button type="button" aria-label="下一个节点" disabled={currentIndex<0||currentIndex>=nodes.length-1} onClick={()=>selectNode(nodes[currentIndex+1])}>下一个<ChevronRight size={12}/></button></div></header><div className={styles.nodeOrder}><span>同级顺序</span><button type="button" aria-label="上移节点" disabled={!canEdit || busy || !currentNode} onClick={() => changeNodes(moveOutlineSibling(nodes, currentId, -1))}><ChevronUp size={14} /></button><button type="button" aria-label="下移节点" disabled={!canEdit || busy || !currentNode} onClick={() => changeNodes(moveOutlineSibling(nodes, currentId, 1))}><ChevronDown size={14} /></button></div>
          {currentNode ? <form onSubmit={event => { event.preventDefault(); void save(); }}><fieldset disabled={!canEdit || busy}>
            <label>标题 <span className={styles.required}>*</span><input required maxLength={600} value={currentNode.title} onChange={event => patchNode({ title: event.target.value })} /></label>
            <div className={styles.fields}><label>层级<select value={currentNode.parent_id || ""} onChange={event => patchNode({ parent_id: event.target.value || null })}><option value="">一级标题（章）</option>{nodes.filter(node => !descendants.has(node.id)).map(node => <option key={node.id} value={node.id}>{node.level+1}级 · {node.title}</option>)}</select></label>
              <label>PDF 物理页 <span className={styles.required}>*</span><input type="number" min={1} max={asset?.page_count || undefined} value={currentNode.pdf_page ?? ""} onChange={event => { const page = event.target.value ? Number(event.target.value) : null; patchNode({ pdf_page: page, pdf_position: [], normalized_position: [], source_locator: undefined, clear_position: true }); if (page && page <= (asset?.page_count || Infinity)) setPreviewPage(page); }} /></label>
              <label>印刷标签<input maxLength={40} placeholder="如 iii、3、A-1" value={currentNode.printed_label} onChange={event => patchNode({ printed_label: event.target.value })} /></label>
              <label>同页节点<select aria-label="查看同页其他节点" value="" onChange={event=>{const node=samePageNodes.find(row=>row.id===event.target.value);if(node)selectNode(node);}}><option value="">{samePageNodes.length?`${samePageNodes.length} 个同页节点`:"无"}</option>{samePageNodes.map(node=><option key={node.id} value={node.id}>{node.title}</option>)}</select></label></div>
            <label>页内位置<select value={positionValue} onChange={event=>{if(event.target.value!=="source")patchNode({pdf_position:[],source_locator:undefined,clear_position:true,normalized_position:event.target.value==="middle"?[0,.5]:event.target.value==="lower"?[0,.75]:event.target.value==="custom"?[0,0]:[]});}}><option value="page">页面顶部</option><option value="middle">页面中部</option><option value="lower">页面下半部分</option>{currentNode.pdf_position?.length || currentNode.source_locator?.bbox ? <option value="source">保留来源定位</option> : null}<option value="custom">自定义页面落点</option></select></label>
            {positionValue==="custom"&&currentNode.normalized_position?.length === 2 ? <div className={styles.fields}>{[0, 1].map((axis) => <label key={axis}>{axis ? "距顶部 (%)" : "距左侧 (%)"}<input type="number" min={0} max={100} step={0.1} value={Math.round(currentNode.normalized_position![axis] * 1000) / 10} onChange={event => { const point = [...currentNode.normalized_position!]; point[axis] = Number(event.target.value) / 100; patchNode({ normalized_position: point }); }} /></label>)}</div> : null}
            <label>识别来源<output>{outlineSourceLabels[currentNode.source || ""] || "来源待核对"}</output></label><details className={styles.sourceDetails}><summary>原始定位信息</summary><label>目录来源页<input type="number" min={1} max={asset?.page_count || undefined} value={currentNode.contents_page ?? ""} onChange={event=>patchNode({contents_page:event.target.value?Number(event.target.value):null})}/></label></details>
            <div className={styles.actions}><button type="button" disabled={!dirty||busy} onClick={()=>setConfirmation({kind:"discard"})}>取消</button><button type="submit" className={styles.primary} disabled={!dirty || stale}>保存修正</button></div>
            <div className={styles.minorActions}><button type="button" onClick={() => addNode(true)}><Plus size={12} />新增子节点</button><button type="button" onClick={() => setConfirmation({ kind: "delete", id: currentId })}><Trash2 size={12} />移除此节点</button></div>
          </fieldset></form> : <p className={styles.empty}>选择一个目录节点，或手工添加目录。</p>}
        </section>
        <div ref={previewRef} tabIndex={-1} aria-label="PDF 原稿预览" className={styles.previewColumn}>{asset?.preview_url ? <OutlinePdfPreview key={`${ownerId}:${asset.id}:${asset.sha256}`} asset={asset} ownerId={ownerId} page={previewPage} setPage={setPreviewPage} navigationTarget={currentNode?.pdf_page === previewPage ? outlinePosition(currentNode) || [0, 0] : undefined} /> : <p className={styles.empty}>当前文件尚无可用 PDF 预览。</p>}</div>
      </div>
    {revision ? <OutlineDiagnostics key={revision.id} items={revision.diagnostics} nodes={nodes} pageCount={asset?.page_count || 0} onSelect={inspectNode} onPreview={inspectPage} /> : null}
    <div className={styles.mobileActions}><button type="button" disabled={!canRebuild || busy || pendingJobs || dirty} onClick={rebuild}>重新生成目录</button><button type="button" className={styles.primary} disabled={!canEdit || busy || !dirty || stale} onClick={() => void save()}>保存修正</button></div>
    {data.jobs.length ? <section className={styles.jobs} aria-label="目录任务"><h2>目录任务</h2>{data.jobs.map(job => <article key={job.id}><span>{job.operation === "outline_export" ? "书签副本 · " : "目录提取 · "}{jobLabels[job.status] || job.status}</span>{isTaskRunning(job.status) ? <progress max={100} value={job.progress} aria-label="目录任务进度" /> : null}<time>{date(job.updated_at)}</time>{job.error ? <p role="alert">{job.error}</p> : null}{job.download_url && canDownload ? <><span>{job.outline_revision_id === data.active?.id ? "当前目录" : "历史目录副本"}</span><button type="button" disabled={busy} onClick={() => { setReading(true); void downloadWorkFile(ownerId, job.download_url!, "校准书签.pdf").then(() => { if (alive.current) setMessage("已开始下载独立书签副本，原件未改动。"); }).catch(reason => { if (alive.current) setMessage(reason instanceof Error ? reason.message : "副本下载暂未完成。"); }).finally(() => { if (alive.current) setReading(false); }); }}>下载书签副本</button></> : null}{canRebuild && (isTaskRunning(job.status) || job.status === "failed") ? <button type="button" disabled={busy} onClick={() => void command(`${job.id}:${job.status}`, async () => { await actOnOutlineJob(job.id, isTaskRunning(job.status) ? "cancel" : "retry"); return readOutlineState(assetId); }, "任务状态已更新。")}>{isTaskRunning(job.status) ? "取消任务" : "重试"}</button> : null}</article>)}</section> : null}
    <Dialog open={Boolean(confirmation)} className={styles.dialog} aria-labelledby="outline-confirm-title" onRequestClose={() => { if (!busy) setConfirmation(null); }}><h2 id="outline-confirm-title">{confirmation?.kind === "resave" ? "保存当前修正" : confirmation?.kind === "discard" ? "载入最新目录" : "移除目录节点"}</h2>
      <p>{confirmation?.kind === "resave" ? `请核对下方差异。当前 ${nodes.length} 个节点将保存为新修订并生效，下载副本自动更新。其他人的已保存修订仍会保留。` : confirmation?.kind === "discard" ? "放弃未保存的输入，载入当前生效目录。" : "此节点将从目录中移除，子节点提升到上一级。保存修正后生效，PDF正文不变。"}</p>
      {confirmation?.kind === "resave" ? <div className={styles.conflictChanges}><p>与最新修订相比，{conflictDifferences.length} 项内容不同（仅列出前 20 项；顺序以当前编辑目录为准）。</p>{conflictDifferences.slice(0, 20).map(item => <div key={item.id}><span>最新：{item.latest ? `${item.latest.title} · PDF ${item.latest.pdf_page || "待定位"}` : "不存在此节点"}</span><span>当前输入：{item.mine ? `${item.mine.title} · PDF ${item.mine.pdf_page || "待定位"}` : "移除此节点"}</span></div>)}</div> : null}
      <div className={styles.actions}><button type="button" disabled={busy} onClick={() => setConfirmation(null)}>取消</button><button type="button" className={styles.primary} disabled={busy} onClick={() => void confirmAction()}>{busy ? "正在处理…" : "确认"}</button></div>
    </Dialog>
  </div>;
}
