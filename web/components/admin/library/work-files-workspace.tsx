"use client";

import { createRequestKey } from "../../../lib/request-key";
import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, ArrowUpRight, BookOpen, Download, FileText, History, Plus, RefreshCw, Upload } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ApiRequestError, getServerSessionCredential, normalizePublicResourceUrl, subscribeToSessionChanges } from "@/lib/api";
import { useAdminSession } from "@/lib/admin-session";
import { adminListHref, adminPageNumber, safeAdminHref } from "@/lib/admin-route-context";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { generateWorkFileReader, resumeFileTask, workFileBytes, workFileDate, workFilesPath } from "@/lib/api/work-files.client";
import type { WorkFile, WorkFilesState } from "@/lib/api/work-files.types";
import { PrimaryEditionControl } from "@/components/admin/workflow/primary-edition-control";
import { fileKindLabel, fileProcessingStatusLabel, pdfValidationPresentation } from "@/components/admin/workflow/file-presentation";
import { AdoptWorkFileDialog, NewWorkEditionDialog, UploadWorkFileDialog } from "./work-file-actions";
import { downloadWorkFile, WorkFilePreview } from "./work-file-preview";
import { WorkFileRightsDialog } from "./work-file-rights";
import { WorkFilePublicPreparation } from "./work-file-public-preparation";
import styles from "./work-files.module.css";

const tabs = { versions: "版本列表", files: "文件与历史", rights: "版权与授权", publication: "发布记录" };
type Tab = keyof typeof tabs;
type Modal = { kind: "edition" | "rights" } | { kind: "upload"; action: "supplement" | "replace" } | { kind: "preview" | "adopt" | "prepare_public"; file: WorkFile } | null;
const stateNames: Record<string, string> = { draft: "草稿", published: "已公开", withdrawn: "已撤回", pending: "等待处理", processing: "处理中", applied: "已生效", completed: "已完成", complete: "已完成", succeeded: "已完成", failed: "处理失败", blocked: "需处理", cancelled: "已取消", paused: "已暂停", queued: "已排队", ready: "已就绪", unknown: "待核实" };
const accessNames: Record<string, string> = { public: "公开可读", restricted: "受限访问", private: "仅管理可见", unknown: "尚未确认", pending: "待核对" };
const kindNames: Record<string, string> = { catalog_evidence: "馆藏来源", work: "作品来源", theory: "理论来源", concept: "概念来源", viewpoint: "观点来源", scholar: "学者来源" };
const activeTasks = (state: WorkFilesState) => state.tasks.some(task => task.is_active) || state.history.results.some(row => ["preparing", "pending", "processing"].includes(row.status)) || [...state.files.results, ...(state.current_reader_file ? [state.current_reader_file] : [])].some(file => ["pending", "syncing"].includes(file.public_preparation.status));

function Pager({ page, size, count, label, change }: { page: number; size: number; count: number; label: string; change: (page: number) => void }) {
  const total = Math.max(1, Math.ceil(count / Math.max(1, size)));
  return <nav className={styles.pager} aria-label={label}><span>共 {count} 项 · 第 {page} / {total} 页</span><button disabled={page <= 1} onClick={() => change(page - 1)}>上一页</button><button disabled={page >= total} onClick={() => change(page + 1)}>下一页</button></nav>;
}

export function WorkFilesWorkspace({ workId }: { workId: string }) {
  const user = useAdminSession(), search = useSearchParams(), [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  if (!user) return <p role="status">正在核对管理会话…</p>;
  return <Workspace key={`${user.id}:${workId}:${search.get("edition") || ""}:${epoch}`} workId={workId} ownerId={String(user.id)} />;
}

function Workspace({ workId, ownerId }: { workId: string; ownerId: string }) {
  const search = useSearchParams(), pathname = usePathname(), router = useRouter();
  const editionId = search.get("edition") || "", page = adminPageNumber(search.get("page")), impactPage = adminPageNumber(search.get("impact_page")), historyPage = adminPageNumber(search.get("history_page"));
  const selectedTab = search.get("tab") || "versions", tab: Tab = Object.hasOwn(tabs, selectedTab) ? selectedTab as Tab : "versions";
  const resource = usePersistentWorkspace<WorkFilesState>(workFilesPath(workId, editionId, page, impactPage, historyPage), ownerId, state => activeTasks(state) ? 3000 : null);
  const [modal, setModal] = useState<Modal>(null), [message, setMessage] = useState(""), [busy, setBusy] = useState("");
  const alive = useRef(true), inFlight = useRef(false);
  const generations = useRef(new Map<string, { request_key: string; expected_asset_updated_at: string }>());
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const change = (values: Record<string, string | number | null>) => router.push(adminListHref(pathname, search.toString(), values));
  const state = resource.data?.work.id === workId ? resource.data : null;
  const edition = state?.editions.find(value => value.id === state.selected_edition_id), current = state?.current_reader_file;
  const workbench = safeAdminHref(state?.edition?.workbench_url || "", "");
  const canEdit = Boolean(state?.capabilities.can_edit), canPublish = Boolean(state?.capabilities.can_publish);
  const returnTo = `${pathname}${search.size ? `?${search}` : ""}`;
  const selectEdition = (id: string) => { setModal(null); setMessage(""); change({ edition: id, page: 1, impact_page: 1, history_page: 1 }); };
  async function action(key: string, callback: () => Promise<unknown>) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(key); setMessage("");
    try { await callback(); if (alive.current) resource.reload(); }
    catch (reason) { if (alive.current) setMessage(reason instanceof Error ? reason.message : "操作尚未完成，请重试。"); }
    finally { inFlight.current = false; if (alive.current) setBusy(""); }
  }
  async function generate(file: WorkFile) {
    const input = generations.current.get(file.id) || { request_key: createRequestKey(), expected_asset_updated_at: file.updated_at };
    generations.current.set(file.id, input);
    try {
      const receipt = await withPrivateOwner(ownerId, () => generateWorkFileReader(file.generate_reader_url, input));
      if (receipt.request_key !== input.request_key || receipt.work_id !== workId || receipt.edition_id !== state?.selected_edition_id || !receipt.accepted) throw new Error("尚未确认阅读副本生成请求，保留原请求再次核对。");
      generations.current.delete(file.id);
      if (alive.current) setMessage(receipt.detail);
    } catch (reason) {
      if (reason instanceof ApiRequestError && reason.status >= 400 && reason.status < 500 && ![408, 429].includes(reason.status)) generations.current.delete(file.id);
      throw reason;
    }
  }
  function fileActions(file: WorkFile) {
    return <div className={styles.rowActions}>{file.preview_url ? <button onClick={() => setModal({ kind: "preview", file })}>预览</button> : null}<button disabled={!file.download_url || Boolean(busy)} onClick={() => void action(`download:${file.id}`, () => downloadWorkFile(ownerId, file.download_url, file.filename || "馆藏文件"))}><Download size={13} />下载</button>{file.generate_reader_url && canEdit ? <button disabled={Boolean(busy)} onClick={() => void action(`generate:${file.id}`, () => generate(file))}>{busy === `generate:${file.id}` ? "正在提交…" : "生成阅读副本"}</button> : null}{file.public_preparation.can_prepare ? <button onClick={() => setModal({ kind: "prepare_public", file })}>准备公开阅读文件</button> : null}{file.can_adopt ? <button onClick={() => setModal({ kind: "adopt", file })}>采用为阅读文件</button> : null}</div>;
  }
  return <main className={styles.workspace}>
    <Link className={styles.back} href="/admin/library/works?view=editions"><ArrowLeft size={14} />返回版本与文件</Link>
    <header className={styles.heading}><div><p className={styles.eyebrow}>馆藏管理 / 版本与文件</p><h1>版本与文件管理</h1><p>管理同一作品的出版版本、阅读文件与引用影响。</p></div><div className={styles.toolbar}><button disabled={!state} onClick={resource.reload}><RefreshCw size={14} />刷新</button><button className={styles.primary} disabled={!canEdit} onClick={() => setModal({ kind: "edition" })}><Plus size={16} />新增出版版本</button></div></header>
    {resource.error ? <p role="alert" className={styles.error}>{resource.error}<button onClick={resource.reload}>重新读取</button></p> : null}{message ? <p role="status" className={styles.notice}>{message}</p> : null}
    {!state ? <p className={styles.empty} role="status">{resource.loading ? "正在读取作品、出版版本及文件记录…" : resource.error ? "当前作品暂不可读取。" : "未取得当前作品记录。"}</p> : <>
      <div className={styles.layout}><div className={styles.mainColumn}>
        <section className={styles.bookSummary} aria-label="当前作品"><div className={styles.cover}>{state.work.cover_url ? <Image unoptimized width={74} height={105} src={normalizePublicResourceUrl(state.work.cover_url)} alt={`${state.work.title}封面`} /> : <BookOpen size={30} aria-label="暂无封面" />}</div><div><small>作品</small><h2>{state.work.title || "未命名作品"}</h2><p>{state.work.authors.join(" / ") || "责任者尚未确认"}</p><p className={styles.muted}>{state.work.original_publication_year ? `${state.work.original_publication_year} 年 · ` : ""}{state.editions.length} 个出版版本</p></div><div className={styles.summaryActions}>{workbench ? <Link href={`${workbench.split("#")[0]}#work`}>编辑作品信息<ArrowUpRight size={14} /></Link> : null}<span>更新于 {workFileDate(state.work.updated_at)}</span></div></section>
        <label className={styles.mobileSelect}>当前出版版本<select value={state.selected_edition_id || ""} onChange={event => selectEdition(event.target.value)}><option value="" disabled>选择出版版本</option>{state.editions.map(row => <option key={row.id} value={row.id}>{row.label || row.version_label || "未命名版本"}{row.is_primary ? " · 主版本" : ""}</option>)}</select></label>
        <nav className={styles.tabs} aria-label="版本管理视图">{Object.entries(tabs).map(([key, label]) => <button key={key} aria-current={tab === key ? "page" : undefined} onClick={() => change({ tab: key })}>{label}</button>)}</nav>
        {tab === "versions" ? <section className={styles.panel} aria-labelledby="edition-list-title"><header className={styles.panelHeading}><div><h2 id="edition-list-title">出版版本</h2><p>选中一个版本，查看右侧文件与维护入口。</p></div><span>{state.editions.length} 个版本</span></header><div className={styles.tableScroll}><table className={styles.versionTable}><thead><tr><th>版本</th><th>出版信息</th><th>文件</th><th>状态</th><th>操作</th></tr></thead><tbody>{state.editions.map(row => <tr key={row.id} data-selected={state.selected_edition_id === row.id}><td><button className={styles.selectVersion} aria-pressed={state.selected_edition_id === row.id} onClick={() => selectEdition(row.id)}>{row.version_label || row.label || "出版版本"}</button>{row.is_primary ? <span className={styles.badge}>主版本</span> : null}</td><td><span>{row.publisher || "出版机构待补"}</span><small>{row.publication_year || "年份待补"} · {row.language || "语言待补"}</small></td><td><span>{row.original_count} 份原件</span><small>{row.reader_count} 份阅读文件</small></td><td><span className={styles.badge}>{stateNames[row.state] || row.state}</span></td><td><button onClick={() => { setModal(null); setMessage(""); change({ edition: row.id, tab: "files", page: 1, impact_page: 1, history_page: 1 }); }}>管理文件</button></td></tr>)}</tbody></table></div>{!state.editions.length ? <div className={styles.empty}><BookOpen size={26} /><p>这个作品还没有出版版本。</p><button disabled={!canEdit} onClick={() => setModal({ kind: "edition" })}>建立第一个出版版本</button></div> : null}<p className={styles.panelFoot}>主版本用于作品列表展示，各版本文件及历史分别保留。新增版本先保存为草稿。</p></section> : null}
        {tab === "files" ? <section className={styles.panel} aria-labelledby="file-history-title"><header className={styles.panelHeading}><div><h2 id="file-history-title">文件与历史</h2><p>{edition?.label || "请先选择出版版本"}</p></div><button disabled={!canEdit || !state.edition} onClick={() => setModal({ kind: "upload", action: "supplement" })}><Upload size={14} />补充文件</button></header><div className={styles.fileList}>{state.files.results.map(file => <article key={file.id} className={styles.fileRow}><FileText size={22} /><div><h3>{file.filename || fileKindLabel(file.kind)}</h3><p>{fileKindLabel(file.kind)} · 第 {file.version} 份 · {workFileBytes(file.byte_size)}{file.page_count > 0 ? ` · ${file.page_count} 页` : ""}</p><small>{workFileDate(file.created_at)}{file.created_by ? ` · ${file.created_by}` : ""}</small><div className={styles.badges}>{file.id === state.edition?.current_reader_asset_id ? <span className={styles.badge}>当前阅读</span> : null}{file.is_public_reader ? <span className={styles.badge}>已公开</span> : null}<span>{fileProcessingStatusLabel(file.status)}</span><span>{pdfValidationPresentation(file.validation_status).label}</span></div>{file.public_preparation.required ? <p className={styles.muted}>{file.public_preparation.detail}</p> : null}{fileActions(file)}</div></article>)}</div>{!state.files.results.length ? <p className={styles.empty}>当前版本没有文件记录。可补充原件，书目记录继续保留。</p> : null}<Pager label="文件历史分页" page={state.files.page} size={state.files.page_size} count={state.files.count} change={value => change({ page: value })} /></section> : null}
        {tab === "rights" ? <section className={styles.panel}><header className={styles.panelHeading}><div><h2>版权与授权</h2><p>当前阅读文件的实际权利记录。</p></div></header><dl className={styles.rights}><dt>访问状态</dt><dd>{accessNames[state.edition?.rights.access_status || ""] || state.edition?.rights.access_status || "尚未确认"}</dd><dt>授权说明</dt><dd>{state.edition?.rights.note || "尚未填写授权说明。请核对文件来源与授权后填写说明。"}</dd><dt>对应文件</dt><dd>{current?.filename || (state.edition?.rights.source_asset_id ? "当前版本保留的原件" : "当前版本尚无文件")}</dd></dl>{state.edition?.rights.can_edit ? <div className={styles.panelLink}><button onClick={() => setModal({ kind: "rights" })}>编辑版权与授权说明</button></div> : null}</section> : null}
        {tab === "publication" ? <section className={styles.panel}><header className={styles.panelHeading}><div><h2>发布记录</h2><p>发布快照包含书目与文件。切换阅读文件请使用文件列表中的采用操作。</p></div>{workbench ? <Link href={`${workbench.split("#")[0]}#publication`}>查看完整发布工作台</Link> : null}</header><ol className={styles.history}>{state.history.results.map(row => <li key={row.id}><History size={17} /><div><strong>第 {row.revision} 次修订 · {row.title || state.work.title}</strong><p>{stateNames[row.status] || row.status}{row.is_current ? " · 当前发布记录" : ""}</p><small>{workFileDate(row.activated_at)}</small></div></li>)}</ol>{!state.history.results.length ? <p className={styles.empty}>此出版版本尚无发布记录。</p> : null}<Pager label="发布历史分页" page={state.history.page} size={state.history.page_size} count={state.history.count} change={value => change({ history_page: value })} /></section> : null}
        {state.tasks.length ? <section className={styles.panel} aria-label="文件处理请求"><header className={styles.panelHeading}><div><h2>文件处理请求</h2><p>共 {state.task_count} 项请求，显示最近 {state.tasks.length} 项。</p></div><Link href="/admin/processing">全部处理任务</Link></header><ul className={styles.taskList}>{state.tasks.map(task => <li key={task.id}><div><strong>{task.source_filename || "文件处理请求"}</strong><span>{stateNames[task.status] || task.status} · {task.generate_reader ? "原件与阅读副本" : "仅保存原件"}</span>{task.is_active ? <progress max={100} value={task.progress} aria-label="服务端处理进度" /> : null}{task.error_message ? <p className={styles.error}>{task.error_message}</p> : null}</div><div className={styles.rowActions}>{task.retry_url || task.resume_url ? <button disabled={Boolean(busy) || !canEdit} onClick={() => void action(task.id, () => withPrivateOwner(ownerId, () => resumeFileTask(task.resume_url || task.retry_url)))}>{busy === task.id ? "正在提交…" : task.resume_url ? "继续处理" : "重试原任务"}</button> : null}{safeAdminHref(task.processing_href, "") ? <Link href={safeAdminHref(task.processing_href, "")}>处理详情</Link> : null}</div></li>)}</ul></section> : null}
      </div><aside className={styles.sidebar} aria-label="所选版本的文件与影响">
        <section className={styles.panel}><header className={styles.panelHeading}><div><small>所选出版版本</small><h2>{edition?.version_label || edition?.label || "尚无版本"}</h2><p>{edition?.publisher || "出版机构待补"}{edition?.publication_year ? ` · ${edition.publication_year}` : ""}</p></div>{edition?.is_primary ? <span className={styles.badge}>主版本</span> : null}</header><div className={styles.currentFile}><h3>当前阅读文件</h3>{current ? <><FileText size={30} /><strong>{current.filename || "阅读文件"}</strong><p>{current.page_count} 页 · {workFileBytes(current.byte_size)}</p><span className={styles.badge}>{current.is_public_reader ? "公开阅读中" : "当前未公开文件"}</span>{current.public_preparation.required ? <p>{current.public_preparation.detail}</p> : null}{fileActions(current)}</> : <p>还没有采用阅读文件。上传并处理原件后，可在文件历史中预览和采用。</p>}<div className={styles.fileButtons}><button disabled={!canEdit || !state.edition} onClick={() => setModal({ kind: "upload", action: "supplement" })}><Plus size={14} />补充文件</button><button disabled={!canEdit || !current} onClick={() => setModal({ kind: "upload", action: "replace" })}>替换文件</button></div>{current ? <div className={styles.maintenanceLinks}><Link href={`/admin/library/assets/${encodeURIComponent(current.id)}/ocr`}>OCR 与文字质量<ArrowUpRight size={13} /></Link><Link href={`/admin/library/assets/${encodeURIComponent(current.id)}/outline`}>目录与跳转校准<ArrowUpRight size={13} /></Link><Link href={`/admin/library/assets/${encodeURIComponent(current.id)}/page-mapping`}>页码映射与校准<ArrowUpRight size={13} /></Link></div> : null}</div>{state.edition ? <div className={styles.primaryControl}><PrimaryEditionControl key={state.edition.id} editionId={state.edition.id} credential={getServerSessionCredential()} canPublish={canPublish} disabled={Boolean(busy || modal)} returnTo={returnTo} onChanged={async () => resource.reload()} /></div> : null}</section>
        <section className={styles.panel}><header className={styles.panelHeading}><div><h2>文件引用与影响</h2><p>当前版本的真实关联记录</p></div></header><dl className={styles.impactCounts}><div><dt>馆藏来源</dt><dd>{state.impact.summary.catalog_evidence}</dd></div><div><dt>读者批注</dt><dd>{state.impact.summary.reader_annotations}</dd></div><div><dt>读者书签</dt><dd>{state.impact.summary.reader_bookmarks}</dd></div><div><dt>阅读进度</dt><dd>{state.impact.summary.reader_progress}</dd></div></dl><p className={styles.privacyNotice}>{state.impact.notice}</p><ul className={styles.impactRows}>{state.impact.results.map(row => <li key={row.id}><small>{kindNames[row.kind] || row.kind}</small><strong>{row.title || "馆藏来源"}</strong><span>{row.printed_page_label ? `印刷页 ${row.printed_page_label}` : row.file_page_index !== null ? `PDF 页 ${row.file_page_index}` : "未定位到单页"} · {stateNames[row.status] || row.status}</span>{safeAdminHref(row.href, "") ? <Link href={safeAdminHref(row.href, "")}>查看馆藏关联</Link> : null}</li>)}</ul>{!state.impact.results.length ? <p className={styles.privacyNotice}>当前页没有可展示的馆藏来源记录。</p> : null}<Pager label="馆藏影响分页" page={state.impact.page} size={state.impact.page_size} count={state.impact.count} change={value => change({ impact_page: value })} /><button className={styles.export} disabled={!state.impact.export_url || Boolean(busy)} onClick={() => void action("export", () => downloadWorkFile(ownerId, state.impact.export_url, "文件引用影响.csv"))}><Download size={14} />导出可见引用影响</button></section>
      </aside></div>
      {modal?.kind === "edition" ? <NewWorkEditionDialog state={state} ownerId={ownerId} onClose={() => setModal(null)} onRefresh={resource.reload} onCreated={id => { selectEdition(id); resource.reload(); }} /> : null}
      {modal?.kind === "upload" && state.edition ? <UploadWorkFileDialog key={`${state.edition.id}:${modal.action}`} state={state} ownerId={ownerId} action={modal.action} onClose={() => { setModal(null); change({ tab: "files" }); }} onRefresh={resource.reload} onAccepted={() => { resource.reload(); }} /> : null}
      {modal?.kind === "preview" ? <WorkFilePreview key={modal.file.id} file={modal.file} ownerId={ownerId} onClose={() => setModal(null)} /> : null}
      {modal?.kind === "prepare_public" && state.edition ? <WorkFilePublicPreparation key={`${state.edition.id}:${modal.file.id}`} editionId={state.edition.id} file={modal.file} ownerId={ownerId} onClose={() => setModal(null)} onChanged={resource.reload} /> : null}
      {modal?.kind === "rights" && state.edition ? <WorkFileRightsDialog state={state} ownerId={ownerId} onClose={() => setModal(null)} onRefresh={resource.reload} onSaved={() => { setModal(null); setMessage("版权说明已保存，访问策略保持原样。"); resource.reload(); }} /> : null}
      {modal?.kind === "adopt" && state.edition ? <AdoptWorkFileDialog key={`${state.edition.id}:${modal.file.id}`} editionId={state.edition.id} file={modal.file} ownerId={ownerId} onClose={() => setModal(null)} onChanged={resource.reload} /> : null}
    </>}
  </main>;
}
