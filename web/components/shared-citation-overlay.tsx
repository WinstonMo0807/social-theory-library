"use client";

import Link from "next/link";
import { Check, Copy, Download, Info, LoaderCircle, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiRequestError, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { readAllPages } from "@/lib/api/read-all-pages";
import { changeResearchSelection, createResearchProject, readResearchRecord, type ProjectData, type ResearchRecord } from "@/lib/api/research.client";
import { researchEvidenceKey, researchEvidenceReference } from "@/lib/api/research-evidence";
import { citationDownload, citationFormats, citationText, previewSharedCitation, type CitationFormat, type SharedCitationInput, type SharedCitationPreview } from "@/lib/api/shared-citation.client";
import { localMaterialEvent, readLocalCitationMaterials, saveLocalCitationMaterial, writeLocalCitationMaterials, type LocalCitationMaterial } from "@/lib/local-citation-materials";
import { bootstrapSession } from "@/lib/session";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { Dialog } from "./ui/dialog";
import styles from "./shared-citation-overlay.module.css";

type Props = SharedCitationInput & { open: boolean; onClose: () => void };
type ExportRow = { format: CitationFormat; state: "pending" | "running" | "completed" | "failed"; text?: string; error?: string };

export function SharedCitationButton({ children = "引用、选材与导出", className, ...input }: SharedCitationInput & { children?: ReactNode; className?: string }) {
  const [open, setOpen] = useState(false);
  return <><button type="button" className={className} onClick={() => setOpen(true)}><Copy size={14} />{children}</button>{open ? <SharedCitationOverlay {...input} open onClose={() => setOpen(false)} /> : null}</>;
}

export function SharedCitationOverlay({ open, onClose, ...input }: Props) {
  const [epoch, setEpoch] = useState(0);
  const [locked, setLocked] = useState(false);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  return <Dialog open={open} onRequestClose={() => { if (!locked) onClose(); }} className={styles.dialog} aria-label="引用、选材与导出">
    <Workspace key={`${JSON.stringify(input)}:${epoch}`} input={input} onClose={onClose} onLocked={setLocked} />
  </Dialog>;
}

function Workspace({ input, onClose, onLocked }: { input: SharedCitationInput; onClose: () => void; onLocked: (value: boolean) => void }) {
  const { state: session, retry: retrySession } = useSessionBootstrap();
  const [preview, setPreview] = useState<SharedCitationPreview | null>(null);
  const [sourceError, setSourceError] = useState("");
  const [sourceLoading, setSourceLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [validationTick, setValidationTick] = useState(0);
  const [projects, setProjects] = useState<ResearchRecord<ProjectData>[]>([]);
  const [projectId, setProjectId] = useState("");
  const [projectError, setProjectError] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [note, setNote] = useState("");
  const [formats, setFormats] = useState<CitationFormat[]>(["quote"]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [manualCopy, setManualCopy] = useState("");
  const [pending, setPending] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [undo, setUndo] = useState<{ projectId?: string; id: string; action: "remove" | "undo"; local?: LocalCitationMaterial; position?: number } | null>(null);
  const [localRows, setLocalRows] = useState<LocalCitationMaterial[]>([]);
  const [basketOpen, setBasketOpen] = useState(false);
  const [basketPage, setBasketPage] = useState(0);
  const [basketPreview, setBasketPreview] = useState<Record<string, SharedCitationPreview | null>>({});
  const [selectedLocal, setSelectedLocal] = useState<string[]>([]);
  const [exportRows, setExportRows] = useState<ExportRow[] | null>(null);
  const [exporting, setExporting] = useState(false);
  const alive = useRef(true);
  const busyRef = useRef(false);
  const validatedInput = useRef<SharedCitationInput | null>(null);
  const exportAbort = useRef<AbortController | null>(null);
  const failedOperation = useRef<(() => Promise<void>) | null>(null);
  const request = useRef({ fingerprint: "", id: "" });
  const ownerId = session.status === "authenticated" ? session.user?.id : undefined;
  const owner = useRef(ownerId);
  useEffect(() => { owner.current = ownerId; }, [ownerId]);
  const activeProject = projects.find(row => row.id === projectId);
  const hasReference = Boolean(preview?.reference);
  const busy = pending || exporting;
  useEffect(() => { onLocked(busy || unknown); }, [busy, unknown, onLocked]);
  const stableInput = JSON.stringify(input);

  useEffect(() => { alive.current = true; return () => { alive.current = false; exportAbort.current?.abort(); }; }, []);
  useEffect(() => {
    const controller = new AbortController();
    let sequence = 0;
    const revalidate = () => {
      if (document.visibilityState !== "visible" || busyRef.current) return;
      const current = ++sequence;
      setPreview(null); setSourceLoading(true); setSourceError(""); setManualCopy(""); setExportRows(null);
      setBasketPreview({}); setValidationTick(value => value + 1);
      void previewSharedCitation(validatedInput.current || JSON.parse(stableInput), controller.signal).then(value => {
        if (!controller.signal.aborted && current === sequence) {
          setPreview(value);
          if (value.reference) validatedInput.current = { reference: researchEvidenceReference(value.reference) };
        }
      }).catch((reason: unknown) => { if (!controller.signal.aborted && current === sequence) setSourceError(reason instanceof Error ? reason.message : "来源暂不可用。"); })
        .finally(() => { if (!controller.signal.aborted && current === sequence) setSourceLoading(false); });
    };
    revalidate(); window.addEventListener("focus", revalidate); document.addEventListener("visibilitychange", revalidate);
    return () => { controller.abort(); window.removeEventListener("focus", revalidate); document.removeEventListener("visibilitychange", revalidate); };
  }, [stableInput, attempt]);
  useEffect(() => {
    const load = () => { try { setLocalRows(readLocalCitationMaterials()); } catch (reason) { setError(reason instanceof Error ? reason.message : "本机选材读取失败。"); } };
    load(); window.addEventListener(localMaterialEvent, load); window.addEventListener("storage", load);
    return () => { window.removeEventListener(localMaterialEvent, load); window.removeEventListener("storage", load); };
  }, []);
  useEffect(() => {
    if (!ownerId) return;
    const controller = new AbortController();
    const credential = getServerSessionCredential();
    if (!credential) return;
    void readAllPages<ResearchRecord<ProjectData>>("/reading/research-projects/", credential, controller.signal)
      .then(async rows => {
        const current = await bootstrapSession();
        if (controller.signal.aborted) return;
        if (current.status !== "authenticated" || current.user?.id !== ownerId) { setProjects([]); setProjectId(""); retrySession(); return; }
        setProjects(rows.filter(row => !row.archived)); setProjectError("");
      })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setProjectError(reason instanceof Error ? reason.message : "研究列表读取失败。"); });
    return () => controller.abort();
  }, [ownerId, attempt, retrySession]);
  useEffect(() => {
    if (!basketOpen) return;
    const controller = new AbortController();
    const rows = localRows.slice(basketPage * 10, basketPage * 10 + 10);
    for (const row of rows) void previewSharedCitation({ reference: row.reference }, controller.signal)
      .then(value => { if (!controller.signal.aborted) setBasketPreview(current => ({ ...current, [row.id]: value })); })
      .catch(() => { if (!controller.signal.aborted) setBasketPreview(current => ({ ...current, [row.id]: null })); });
    return () => controller.abort();
  }, [basketOpen, basketPage, localRows, attempt, validationTick]);

  function nonce(fingerprint: string) {
    if (request.current.fingerprint !== fingerprint) request.current = { fingerprint, id: crypto.randomUUID() };
    return request.current.id;
  }
  async function assertOwner() {
    const expected = ownerId;
    const current = await bootstrapSession();
    if (!alive.current || !expected || owner.current !== expected || current.status !== "authenticated" || current.user?.id !== expected) {
      if (alive.current) { setProjects([]); setProjectId(""); setUndo(null); retrySession(); }
      throw new Error("登录状态已改变，请重新选择本人研究。");
    }
  }
  async function fresh(signal?: AbortSignal) {
    try {
      const value = await previewSharedCitation(validatedInput.current || input, signal);
      if (!alive.current) throw new Error("操作已关闭。");
      if (value.reference) validatedInput.current = { reference: researchEvidenceReference(value.reference) };
      setPreview(value); setSourceError(""); return value;
    } catch (reason) { if (alive.current) { setPreview(null); setManualCopy(""); setSourceError(reason instanceof Error ? reason.message : "来源暂不可用。"); } throw reason; }
  }
  async function run(operation: () => Promise<void>, retry = false) {
    if (busyRef.current || unknown && !retry) return;
    busyRef.current = true;
    setPending(true); setError(""); setNotice("");
    try { await operation(); if (alive.current) { setUnknown(false); request.current = { fingerprint: "", id: "" }; } }
    catch (reason) {
      if (alive.current) {
        const uncertain = !(reason instanceof ApiRequestError) || reason.status === 0 || reason.status >= 500;
        setUnknown(uncertain && Boolean(request.current.id));
        failedOperation.current = uncertain && request.current.id ? operation : null;
        setError(`${reason instanceof Error ? reason.message : "操作未完成。"}${uncertain && request.current.id ? " 原请求已保留，请保持目标与输入并重试。" : ""}`);
      }
    } finally { busyRef.current = false; if (alive.current) setPending(false); }
  }
  async function copy(prepared?: SharedCitationPreview) {
    const value = prepared || await fresh();
    const text = formats.map(format => citationText(value, format)).join("\n\n");
    try { await navigator.clipboard.writeText(text); if (alive.current) { setManualCopy(""); setNotice("引用已复制。"); } }
    catch { if (alive.current) { setManualCopy(text); setNotice("浏览器未允许复制，可在下方选择引用文字手动复制。"); } }
  }
  async function add(copyAfter = false) {
    const value = await fresh();
    const reference = value.reference;
    if (!reference) throw new Error("请先在原文中选择材料。");
    if (!ownerId) {
      const saved = saveLocalCitationMaterial(reference, note);
      setNotice(saved.duplicate ? "本机选材中已有这段原文，未重复添加。" : "已保存在本机。登录后可明确选择研究再转存。");
      if (!saved.duplicate) setUndo({ id: saved.row.id, action: "remove", local: saved.row });
    } else {
      if (!projectId) throw new Error("请选择要加入的研究。");
      await assertOwner();
      const current = await readResearchRecord<ProjectData>("research-projects", projectId);
      await assertOwner();
      const exists = current.data.selections.some(row => researchEvidenceKey(row) === reference.reference_id);
      const data = { action: "add" as const, references: [researchEvidenceReference(reference)], note };
      const saved = await changeResearchSelection(projectId, { ...data, expected_owner_id: ownerId, expected_revision: current.revision, request_id: nonce(JSON.stringify({ projectId, ...data })) });
      await assertOwner();
      setProjects(rows => rows.map(row => row.id === saved.id ? saved : row));
      setNotice(exists ? "该研究已包含这段原文，未重复添加；可以查看已有选材。" : "已加入所选研究。原文与来源修订已核对。");
      if (!exists) setUndo({ projectId, id: reference.reference_id!, action: "remove" });
    }
    if (copyAfter) { await copy(value); }
  }
  async function undoLast() {
    if (!undo) return;
    if (undo.local) {
      const rows = readLocalCitationMaterials();
      if (undo.action === "remove") writeLocalCitationMaterials(rows.filter(row => row.id !== undo.id));
      else if (!rows.some(row => row.id === undo.id)) { rows.splice(Math.min(undo.position || 0, rows.length), 0, undo.local); writeLocalCitationMaterials(rows); }
    } else if (undo.projectId) {
      await assertOwner(); const current = await readResearchRecord<ProjectData>("research-projects", undo.projectId);
      const saved = await changeResearchSelection(undo.projectId, { expected_owner_id: ownerId, expected_revision: current.revision, action: undo.action,
        reference_id: undo.id, request_id: nonce(JSON.stringify(undo)) });
      await assertOwner(); setProjects(rows => rows.map(row => row.id === saved.id ? saved : row));
    }
    setNotice(undo.action === "remove" ? "已撤销本次加入。" : "已恢复选材及原顺序。"); setUndo(null);
  }
  async function create() {
    await assertOwner();
    const saved = await createResearchProject({ expected_owner_id: ownerId, title: newTitle.trim(), request_id: nonce(`create:${newTitle.trim()}`), scope: { kind: "library" } });
    await assertOwner(); setProjects(rows => [saved, ...rows.filter(row => row.id !== saved.id)]); setProjectId(saved.id); setCreating(false); setNewTitle(""); setNotice("研究已创建。点击加入后才会保存这段材料。");
  }
  async function transfer() {
    if (!projectId || !selectedLocal.length) return;
    await assertOwner();
    // Re-read every chosen identity from the public authority; local notes never
    // become quotations, and no source body survives withdrawal in storage.
    const rows = localRows.filter(row => selectedLocal.includes(row.id));
    const verified = await Promise.all(rows.map(row => previewSharedCitation({ reference: row.reference })));
    await assertOwner();
    const current = await readResearchRecord<ProjectData>("research-projects", projectId);
    const refs = verified.map(row => researchEvidenceReference(row.reference!));
    const notes = Object.fromEntries(rows.map((row, index) => [verified[index].reference!.reference_id!, row.note]));
    const saved = await changeResearchSelection(projectId, { expected_owner_id: ownerId, expected_revision: current.revision, action: "add", references: refs, notes,
      request_id: nonce(JSON.stringify({ transfer: projectId, references: refs, notes })) });
    await assertOwner(); setProjects(items => items.map(row => row.id === saved.id ? saved : row));
    setNotice(`已向所选研究转存 ${rows.length} 条材料；重复项自动去重，本机记录继续保留。`); setSelectedLocal([]);
  }
  async function exportFormats(retryOnly = false) {
    if (busyRef.current || unknown || !formats.length) return;
    busyRef.current = true;
    const jobs: ExportRow[] = retryOnly && exportRows ? exportRows.map(row => row.state === "failed" ? { format: row.format, state: "pending" } : row)
      : formats.map(format => ({ format, state: "pending" }));
    setExporting(true); setError(""); setExportRows([...jobs]);
    const controller = new AbortController(); exportAbort.current = controller;
    for (const row of jobs) {
      if (!alive.current || row.state === "completed") continue;
      if (controller.signal.aborted) { row.state = "failed"; row.error = "已取消，可单独重试。"; setExportRows([...jobs]); continue; }
      row.state = "running"; setExportRows([...jobs]);
      try { const value = await fresh(controller.signal); row.text = citationText(value, row.format); row.state = "completed"; }
      catch (reason) { row.state = "failed"; row.error = controller.signal.aborted ? "已取消，可单独重试。" : reason instanceof Error ? reason.message : "导出失败。"; }
      if (alive.current) setExportRows([...jobs]);
    }
    busyRef.current = false;
    if (alive.current) { setExporting(false); if (controller.signal.aborted) setNotice("导出已取消，完成的格式仍然保留。"); }
  }
  async function downloadCompleted() {
    const current = await fresh();
    const completed = (exportRows || []).filter(row => row.state === "completed");
    if (!completed.length) return;
    citationDownload(completed.map(row => `【${citationFormats.find(format => format[0] === row.format)?.[1]}】\n${citationText(current, row.format)}`).join("\n\n"));
    setNotice(`已准备 ${completed.length} 种格式的合并文本下载。`);
  }
  const source = preview?.source;
  return <div className={styles.workspace}>
    <header className={styles.heading}><h2>引用、选材与导出</h2><button aria-label="关闭引用浮层" disabled={busy || unknown} onClick={onClose}><X size={18} /></button></header>
    <div className={styles.body}>
      {sourceLoading ? <div className={styles.state} role="status"><LoaderCircle size={24} /><strong>正在生成引用…</strong><p>请稍候，暂时禁用复制，以免复制上一页内容。</p></div> : sourceError ? <div className={styles.error} role="alert"><strong>来源暂不可用</strong><p>{sourceError}</p><button onClick={() => setAttempt(value => value + 1)}><RefreshCw size={14} />重新核对来源</button><Link href="/explore/original">查找其他版本</Link></div> : null}
      {preview?.reference?.quote ? <section><h3><span>1</span>所选原文</h3><blockquote>{preview.reference.quote}</blockquote></section> : null}
      {source ? <section><h3><span>2</span>来源信息</h3><div className={styles.source}>{source.cover_url ? <img src={source.cover_url} alt={`${source.title}封面`} /> : <div className={styles.noCover}>暂无封面</div>}<div><strong>{source.title}</strong><p>{source.authors.join("、")}</p><p>{[source.publisher, source.publication_year].filter(Boolean).join(" · ")}</p>{source.pdf_page ? <p>{source.printed_label ? `书页 ${source.printed_label} · ` : ""}PDF 第 {source.pdf_page} 页</p> : <p>书目引用，不包含具体页码。</p>}<Link href={source.reader_url || source.work_url}>查看详情</Link></div></div></section> : null}
      <section><h3><span>3</span>添加到</h3>{ownerId ? <><div className={styles.target}><span>我的研究</span><select aria-label="选择目标研究" value={projectId} disabled={busy || unknown} onChange={event => { setProjectId(event.target.value); setUndo(null); }}><option value="">请选择研究</option>{projects.map(row => <option key={row.id} value={row.id}>{row.data.title}</option>)}</select><button disabled={busy || unknown} onClick={() => setCreating(value => !value)}>新建</button></div>{creating ? <div className={styles.newProject}><label>研究名称<input maxLength={240} value={newTitle} disabled={busy || unknown} onChange={event => setNewTitle(event.target.value)} /></label><button disabled={busy || !newTitle.trim()} onClick={() => void run(create)}><Plus size={14} />{unknown ? "重试创建" : "创建研究"}</button></div> : null}{projectError ? <p className={styles.error} role="alert">{projectError}<button onClick={() => setAttempt(value => value + 1)}>重试研究列表</button></p> : null}{activeProject ? <p className={styles.hint}>共 {activeProject.data.selections.length} 条选材 <Link href={`/account/research/${activeProject.id}`}>查看已有选材</Link></p> : null}</> : <div className={styles.info}><Info size={16} /><div><strong>{session.status === "loading" ? "正在核对登录状态" : "未登录，仅本机保存"}</strong><p>可复制和导出公开引用。登录后需明确选择研究，再转存本机选材。</p>{session.status === "temporary_error" ? <button onClick={retrySession}>重新验证登录</button> : <Link href={`/login?next=${encodeURIComponent(typeof window === "undefined" ? "/" : window.location.pathname + window.location.search)}`}>登录后继续</Link>}</div></div>}
        <label className={styles.note}>添加备注（可选）<textarea maxLength={200} value={note} disabled={busy || unknown} onChange={event => setNote(event.target.value)} /><small>{note.length}/200</small></label>
        {!hasReference && !sourceLoading ? <p className={styles.hint}>在 Reader 中选中文字后，可将原文加入研究。</p> : null}
      </section>
      <section><h3><span>4</span>导出格式</h3><div className={styles.formats}>{citationFormats.map(([format, label]) => <label key={format}><input type="checkbox" checked={formats.includes(format)} disabled={busy || unknown} onChange={event => setFormats(rows => event.target.checked ? [...rows, format] : rows.filter(row => row !== format))} />{label}</label>)}</div></section>
      <div className={styles.actions}><button className={styles.primary} disabled={busy || unknown || !preview || !hasReference || !formats.length || session.status === "loading" || Boolean(ownerId && !projectId)} onClick={() => void run(() => add(true))}>{pending ? "处理中…" : unknown ? "重试本次加入" : ownerId ? "加入并复制引用" : "本机保存并复制"}</button><button disabled={busy || unknown || !preview || !formats.length} onClick={() => void run(() => copy())}><Copy size={14} />复制引用</button><button disabled={busy || unknown || !preview || !formats.length} onClick={() => void exportFormats()}><Download size={14} />导出</button></div>
      {notice ? <div className={styles.success} role="status"><Check size={16} /><p>{notice}</p>{undo ? <button disabled={busy || unknown} onClick={() => void run(undoLast)}>撤销</button> : null}</div> : null}
      {error ? <div className={styles.error} role="alert"><p>{error}</p>{unknown ? <button disabled={pending} onClick={() => { if (failedOperation.current) void run(failedOperation.current, true); }}>重试原操作</button> : null}{unknown ? <button onClick={onClose}>关闭后到研究核对结果</button> : null}</div> : null}
      {manualCopy ? <label className={styles.manual}>手动复制引用<textarea readOnly value={manualCopy} onFocus={event => event.currentTarget.select()} /></label> : null}
      {exportRows ? <section className={styles.export}><h3>导出进度（{exportRows.filter(row => row.state === "completed").length}/{exportRows.length}）</h3><progress max={exportRows.length} value={exportRows.filter(row => row.state === "completed" || row.state === "failed").length} />{exportRows.map(row => <div key={row.format}><strong>{citationFormats.find(format => format[0] === row.format)?.[1]}</strong><span>{row.state === "completed" ? "已完成" : row.state === "failed" ? "导出失败" : row.state === "running" ? "正在准备…" : "等待中"}</span>{row.error ? <small>{row.error}</small> : null}</div>)}<p>已完成的格式会保留，失败项可单独重试。</p><div className={styles.actions}>{exporting ? <button onClick={() => exportAbort.current?.abort()}>取消导出</button> : null}<button disabled={busy || unknown || !exportRows.some(row => row.state === "completed")} onClick={() => void run(downloadCompleted)}>下载已完成格式</button><button disabled={busy || unknown || !exportRows.some(row => row.state === "failed")} onClick={() => void exportFormats(true)}>重试失败项</button></div></section> : null}
      <section className={styles.basket}><button className={styles.basketHeading} aria-expanded={basketOpen} onClick={() => setBasketOpen(value => !value)}>本机选材（{localRows.length}）</button>{basketOpen ? <><p>只保存来源位置与本人备注，原文会在打开时重新核对。</p>{localRows.slice(basketPage * 10, basketPage * 10 + 10).map((row, index) => <article key={row.id}><label><input type="checkbox" disabled={busy || unknown || !basketPreview[row.id]} checked={selectedLocal.includes(row.id)} onChange={event => setSelectedLocal(items => event.target.checked ? [...items, row.id] : items.filter(id => id !== row.id))} /><span><strong>{basketPreview[row.id]?.source.title || (row.id in basketPreview ? "来源暂不可用" : "正在核对来源…")}</strong><small>{basketPreview[row.id]?.reference?.quote}</small>{row.note ? <em>{row.note}</em> : null}</span></label><button disabled={busy || unknown} aria-label={`移除第 ${basketPage * 10 + index + 1} 条本机选材`} onClick={() => { try { const rows = readLocalCitationMaterials(); const position = rows.findIndex(item => item.id === row.id); writeLocalCitationMaterials(rows.filter(item => item.id !== row.id)); setUndo({ id: row.id, action: "undo", local: row, position }); setNotice("已移除本机选材，可撤销恢复原位置。"); } catch (reason) { setError(reason instanceof Error ? reason.message : "本机保存失败。"); } }}><Trash2 size={14} /></button></article>)}{localRows.length > 10 ? <div className={styles.actions}><button disabled={basketPage === 0} onClick={() => setBasketPage(value => value - 1)}>上一页</button><span>{basketPage + 1}/{Math.ceil(localRows.length / 10)}</span><button disabled={(basketPage + 1) * 10 >= localRows.length} onClick={() => setBasketPage(value => value + 1)}>下一页</button></div> : null}{ownerId ? <button className={styles.primary} disabled={busy || unknown || !projectId || !selectedLocal.length} onClick={() => void run(transfer)}>将已选 {selectedLocal.length} 条转存到所选研究</button> : null}{!localRows.length ? <p>尚无本机选材。</p> : null}</> : null}</section>
    </div>
  </div>;
}
