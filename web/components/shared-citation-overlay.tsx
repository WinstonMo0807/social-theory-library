"use client";

import { LoadingState } from "@/components/ui/loading-state";
import { DefaultCover } from "@/components/default-cover";
import { useEvidenceLanguage } from "./evidence-language";
import { MediaPlacement } from "@/components/media-placement";

import { createRequestKey } from "../lib/request-key";
import Link from "next/link";
import Image from "next/image";
import { Check, Copy, Info, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { ApiRequestError, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { readAllPages } from "@/lib/api/read-all-pages";
import { booklistRequest, type BooklistDirectory, type BooklistSummary, type BooklistResult, type BooklistWorkspace, type CitationBooklistInput, type CitationBooklistResult } from "@/lib/api/booklists.client";
import { changeResearchSelection, createResearchProject, readResearchRecord, type ProjectData, type ResearchRecord } from "@/lib/api/research.client";
import { researchEvidenceKey, researchEvidenceReference } from "@/lib/api/research-evidence";
import { citationFormats, citationText, previewSharedCitation, type CitationFormat, type SharedCitationInput, type SharedCitationPreview } from "@/lib/api/shared-citation.client";
import { localMaterialEvent, readLocalCitationMaterials, saveLocalCitationMaterial, writeLocalCitationMaterials, type LocalCitationMaterial } from "@/lib/local-citation-materials";
import { bootstrapSession } from "@/lib/session";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { SourceText } from "./source-text";
import { CitationText } from "./citation-text";
import { Dialog } from "./ui/dialog";
import styles from "./shared-citation-overlay.module.css";

type Props = SharedCitationInput & { open: boolean; onClose: () => void };

export function SharedCitationButton({ children = "引用与选材", className, ...input }: SharedCitationInput & { children?: ReactNode; className?: string }) {
  const { t } = useEvidenceLanguage();
  const [open, setOpen] = useState(false);
  return <><button type="button" className={className} onClick={() => setOpen(true)}><Copy size={14} />{typeof children === "string" ? t(children) : children}</button>{open ? <SharedCitationOverlay {...input} open onClose={() => setOpen(false)} /> : null}</>;
}

export function SharedCitationOverlay({ open, onClose, ...input }: Props) {
  const { t } = useEvidenceLanguage();
  const [epoch, setEpoch] = useState(0);
  const [locked, setLocked] = useState(false);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  // Keep the modal visible when its source inspector hides at a mobile breakpoint.
  if (typeof document === "undefined") return null;
  return createPortal(<Dialog open={open} onRequestClose={() => { if (!locked) onClose(); }} className={styles.dialog} aria-label={t("引用与选材")}>
    <Workspace key={`${JSON.stringify(input)}:${epoch}`} input={input} onClose={onClose} onLocked={setLocked} />
  </Dialog>, document.body);
}

function Workspace({ input, onClose, onLocked }: { input: SharedCitationInput; onClose: () => void; onLocked: (value: boolean) => void }) {
  const { t } = useEvidenceLanguage();
  const { state: session, retry: retrySession } = useSessionBootstrap();
  const [preview, setPreview] = useState<SharedCitationPreview | null>(null);
  const [sourceError, setSourceError] = useState("");
  const [sourceLoading, setSourceLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [validationTick, setValidationTick] = useState(0);
  const [projects, setProjects] = useState<ResearchRecord<ProjectData>[]>([]);
  const [projectId, setProjectId] = useState(input.initialProjectId || "");
  const [projectQuery, setProjectQuery] = useState("");
  const [projectError, setProjectError] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [note, setNote] = useState("");
  const [target, setTarget] = useState<"research" | "booklist">("research");
  const [lists, setLists] = useState<BooklistDirectory | null>(null);
  const [listId, setListId] = useState("");
  const [listQuery, setListQuery] = useState("");
  const [listPage, setListPage] = useState(1);
  const [listError, setListError] = useState("");
  const [loadedListKey, setLoadedListKey] = useState("");
  const [saveExcerpt, setSaveExcerpt] = useState(true);
  const [editingQuote, setEditingQuote] = useState(false);
  const [editedQuote, setEditedQuote] = useState("");
  const [bookRecovery, setBookRecovery] = useState<{ listId: string; requestId: string } | null>(null);
  const [recoveryReviewed, setRecoveryReviewed] = useState(false);
  const [bookRetryReady, setBookRetryReady] = useState(false);
  const [savedList, setSavedList] = useState<string | null>(null);
  const [format, setFormat] = useState<CitationFormat>("gbt7714-2025");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [undo, setUndo] = useState<{ projectId?: string; booklistId?: string; token?: string; id: string; action: "remove" | "undo"; local?: LocalCitationMaterial; position?: number } | null>(null);
  const [localRows, setLocalRows] = useState<LocalCitationMaterial[]>([]);
  const [basketOpen, setBasketOpen] = useState(false);
  const [basketPage, setBasketPage] = useState(0);
  const [basketPreview, setBasketPreview] = useState<Record<string, SharedCitationPreview | null>>({});
  const [selectedLocal, setSelectedLocal] = useState<string[]>([]);
  const alive = useRef(true);
  const busyRef = useRef(false);
  const validatedInput = useRef<SharedCitationInput | null>(null);
  const quoteBase = useRef<SharedCitationInput | null>(null);
  const pendingBook = useRef<{ listId: string; data: CitationBooklistInput } | null>(null);
  const failedOperation = useRef<(() => Promise<void>) | null>(null);
  const request = useRef({ fingerprint: "", id: "" });
  const ownerId = session.status === "authenticated" ? session.user?.id : undefined;
  const owner = useRef(ownerId);
  useEffect(() => { owner.current = ownerId; }, [ownerId]);
  const activeProject = projects.find(row => row.id === projectId);
  const listKey = `${ownerId}:${listPage}:${listQuery}:${attempt}`;
  const listLoading = target === "booklist" && loadedListKey !== listKey;
  const activeList = !listLoading ? lists?.results.find(row => row.id === listId) : undefined;
  const hasReference = Boolean(preview?.reference);
  const busy = pending;
  useEffect(() => { onLocked(busy || unknown); }, [busy, unknown, onLocked]);
  const stableInput = JSON.stringify(input);

  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController();
    let sequence = 0;
    const revalidate = () => {
      if (document.visibilityState !== "visible" || busyRef.current) return;
      const current = ++sequence;
      setPreview(null); setSourceLoading(true); setSourceError("");
      setBasketPreview({}); setValidationTick(value => value + 1);
      void previewSharedCitation(validatedInput.current || JSON.parse(stableInput), controller.signal).then(value => {
        if (!controller.signal.aborted && current === sequence) {
          setPreview(value);
          if (value.reference) validatedInput.current = { reference: researchEvidenceReference(value.reference) };
          if (!quoteBase.current) quoteBase.current = validatedInput.current;
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
    void readAllPages<ResearchRecord<ProjectData>>("/reading/research-projects/", credential, controller.signal, String(ownerId))
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
    if (!ownerId || target !== "booklist") return;
    const controller = new AbortController();
    void booklistRequest<BooklistDirectory>(String(ownerId), `/reading/lists/directory/?${new URLSearchParams({ page: String(listPage), q: listQuery })}`, { signal: controller.signal })
      .then(async rows => {
        const current = await bootstrapSession();
        if (controller.signal.aborted) return;
        if (current.status !== "authenticated" || current.user?.id !== ownerId || rows.owner_id !== String(ownerId)) { retrySession(); return; }
        setLists(rows); setListError("");
      }).catch((reason: unknown) => { if (!controller.signal.aborted) setListError(reason instanceof Error ? reason.message : "书单读取失败。"); })
      .finally(() => { if (!controller.signal.aborted) setLoadedListKey(listKey); });
    return () => controller.abort();
  }, [ownerId, target, listPage, listQuery, attempt, listKey, retrySession]);
  useEffect(() => {
    if (!ownerId) return;
    const restore = () => {
      try {
        const value = JSON.parse(sessionStorage.getItem(`stl:citation-booklist:${ownerId}`) || "null");
        if (value && /^[0-9a-f-]{36}$/.test(value.listId) && /^[0-9a-f-]{36}$/.test(value.requestId)) setBookRecovery({ listId: value.listId, requestId: value.requestId });
      } catch { /* A failed local receipt read never hides server records. */ }
    };
    restore(); window.addEventListener("storage", restore);
    return () => window.removeEventListener("storage", restore);
  }, [ownerId]);
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
    if (request.current.fingerprint !== fingerprint) request.current = { fingerprint, id: createRequestKey() };
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
    } catch (reason) { if (alive.current) { setPreview(null); setSourceError(reason instanceof Error ? reason.message : "来源暂不可用。"); } throw reason; }
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
  function rememberBook(value: { listId: string; requestId: string } | null) {
    setBookRecovery(value);
    try {
      const key = `stl:citation-booklist:${ownerId}`;
      if (value) sessionStorage.setItem(key, JSON.stringify(value)); else sessionStorage.removeItem(key);
    } catch { /* The source and note are never written to browser storage. */ }
  }
  function finishBook(saved: CitationBooklistResult) {
    pendingBook.current = null; setBookRetryReady(false); rememberBook(null); setUnknown(false);
    request.current = { fingerprint: "", id: "" };
    setSavedList(saved.exists ? saved.list_id : null);
    setUndo(saved.undo_token && saved.exists && !saved.undone ? { booklistId: saved.list_id, token: saved.undo_token, id: saved.request_id, action: "remove" } : null);
    setNotice(saved.undone ? "这次加入已撤销，原请求不会再次保存。" : !saved.exists ? "已查到原保存结果，但书单后来已删除；独立阅读记录请在笔记中管理。" : `书目已加入本人书单${saved.note_ids.length ? `，${saved.note_ids.length} 条摘录已保存到本人的阅读记录` : ""}。`);
    setAttempt(value => value + 1);
  }
  async function recoverBook() {
    if (!bookRecovery) return;
    await assertOwner();
    const saved = await booklistRequest<CitationBooklistResult>(String(ownerId), `/reading/lists/${bookRecovery.listId}/citation/?request_id=${bookRecovery.requestId}`);
    await assertOwner(); finishBook(saved);
  }
  async function addBook() {
    await assertOwner();
    let value: SharedCitationPreview | undefined;
    if (!pendingBook.current) {
      if (bookRecovery) throw new Error("请先查询上次保存结果，避免重复创建摘录。");
      if (!activeList) throw new Error("请选择当前页中的本人书单。");
      value = await fresh();
      const data = { expected_version: activeList.version, edition_id: value.source.edition_id,
        reference: value.reference ? researchEvidenceReference(value.reference) : undefined, save_excerpt: saveExcerpt, note };
      const requestId = nonce(JSON.stringify({ listId, ...data }));
      pendingBook.current = { listId, data: { ...data, request_id: requestId } };
      setBookRetryReady(true);
      rememberBook({ listId, requestId });
    }
    const intent = pendingBook.current;
    let saved: CitationBooklistResult;
    try {
      saved = await booklistRequest<CitationBooklistResult>(String(ownerId), `/reading/lists/${intent.listId}/citation/`, { method: "POST", body: JSON.stringify(intent.data) });
    } catch (reason) {
      if (reason instanceof ApiRequestError && reason.status >= 400 && reason.status < 500) {
        pendingBook.current = null; setBookRetryReady(false); rememberBook(null); request.current = { fingerprint: "", id: "" };
        setAttempt(value => value + 1);
      }
      throw reason;
    }
    await assertOwner(); finishBook(saved);
  }
  async function editQuote() {
    if (!quoteBase.current || !editedQuote.trim()) throw new Error("请保留能在原文中唯一定位的文字。");
    const value = await previewSharedCitation({ ...quoteBase.current, selectedText: editedQuote });
    if (!alive.current) return;
    if (!value.reference) throw new Error("来源没有可保存的选文。");
    validatedInput.current = { reference: researchEvidenceReference(value.reference) };
    setPreview(value); setEditingQuote(false); setUndo(null);
    setNotice("已按原文核对选文范围，之后复制和保存均使用这段原文。");
  }
  async function add() {
    if (target === "booklist" && ownerId) return addBook();
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
  }
  async function undoLast() {
    if (!undo) return;
    if (undo.booklistId && undo.token) {
      await assertOwner();
      const saved = await booklistRequest<CitationBooklistResult>(String(ownerId), `/reading/lists/${undo.booklistId}/undo-citation/`, { method: "POST", body: JSON.stringify({ token: undo.token }) });
      await assertOwner(); finishBook(saved); return;
    } else if (undo.local) {
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
    if (target === "booklist") {
      const id = nonce(`create-booklist:${newTitle.trim()}`);
      const saved = await booklistRequest<BooklistResult>(String(ownerId), "/reading/lists/command/", { method: "POST",
        body: JSON.stringify({ action: "create", list_id: id, request_id: id, expected_version: "0", title: newTitle.trim() }) });
      await assertOwner();
      if (!saved.exists) throw new Error("原请求创建的书单已经删除，请查看书单列表。");
      const workspace = await booklistRequest<BooklistWorkspace>(String(ownerId), `/reading/lists/${saved.id}/workspace/`);
      await assertOwner();
      const row: BooklistSummary = workspace.list;
      setLists({ owner_id: String(ownerId), count: 1, page: 1, total_pages: 1, results: [row] });
      setListId(row.id); setCreating(false); setNewTitle(""); setNotice("书单已创建，点击加入后保存书目与选定摘录。"); return;
    }
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
  const source = preview?.source;
  return <div className={styles.workspace}>
    <header className={styles.heading}><h2>{t("引用与选材")}</h2><button aria-label={t("关闭引用浮层")} disabled={busy || unknown} onClick={onClose}><X size={18} /></button></header>
    <div className={styles.body}>
      {sourceLoading ? <LoadingState>{t("正在生成引用…")}</LoadingState> : sourceError ? <div className={styles.error} role="alert"><strong>{t("来源暂不可用")}</strong><p>{t(sourceError)}</p><button onClick={() => setAttempt(value => value + 1)}><RefreshCw size={14} />{t("重新核对来源")}</button><Link href="/explore/original">{t("查找其他版本")}</Link></div> : null}
      {preview?.reference?.quote ? <section><h3><span>1</span>{t("所选原文")}<button className={styles.editQuote} disabled={busy || unknown || Boolean(preview.reference.anchors)} onClick={() => { setEditingQuote(true); setEditedQuote(preview.reference!.quote || ""); }}>{t("编辑")}</button></h3>
        {editingQuote ? <div className={styles.quoteEditor}><label>{t("调整选文范围")}<textarea maxLength={20000} value={editedQuote} disabled={busy || unknown} onChange={event => setEditedQuote(event.target.value)} /></label><p className={styles.hint}>{t("请保留原文文字。系统将核对来源中的唯一位置。")}</p><div className={styles.actions}><button disabled={busy || unknown} onClick={() => setEditingQuote(false)}>{t("取消")}</button><button disabled={busy || unknown || !editedQuote.trim()} onClick={() => void run(editQuote)}>{t("核对并应用")}</button></div></div> : <blockquote><SourceText text={preview.reference.quote} /></blockquote>}
        {preview.reference.anchors ? <p className={styles.hint}>{t("跨页引文按完整来源保存；调整文字时请回到原文逐页选择。")}</p> : null}
      </section> : null}
      {source ? <section><h3><span>2</span>{t("来源信息")}</h3><div className={styles.source}>{source.cover_url ? <MediaPlacement uses={source.cover_media?.display_uses} fallback={<DefaultCover className={styles.noCover} title={source.title} />}><Image unoptimized width={68} height={96} src={source.cover_url} alt={t("{title}封面", { title: source.title })} /></MediaPlacement> : <DefaultCover className={styles.noCover} title={source.title} />}<div><strong>{source.title}</strong><p>{source.authors.join("、")}</p><p>{[source.publisher, source.publication_year].filter(Boolean).join(" · ")}</p>{source.pdf_page ? <p>{source.printed_label ? `${t("书页 {page}", { page: source.printed_label })} · ` : ""}{t("PDF 第 {page} 页", { page: source.pdf_page })}</p> : <p>{t("书目引用，不包含具体页码。")}</p>}<Link href={source.reader_url || source.work_url}>{t("查看详情")}</Link></div></div></section> : null}
      {preview ? <section className={styles.citationDisplay} aria-label={t("引用格式")}>
        <h3>{t("引用格式")}</h3>
        <div className={styles.formats}>{citationFormats.filter(([format]) => format !== "csl" && (format !== "quote" || hasReference)).map(([value, label]) => <button type="button" key={value} aria-pressed={format === value} disabled={busy || unknown} onClick={() => setFormat(value)}>{t(label)}</button>)}</div>
        <CitationText className={styles.citationText} text={citationText(preview, format)} italicTitle={!["gbt7714-2025", "quote"].includes(format) ? ["journal_article", "chapter"].includes(source?.document_type || "") ? source?.container_title || "" : source?.document_type === "thesis" && format === "chicago" ? "" : source?.title || "" : ""} />
        {source?.citation_notes?.map(note => <p key={note} className={styles.hint}>{note}</p>)}
      </section> : null}
      <section><h3>{t("加入与保存")}</h3>
        {ownerId ? <>
          <div className={styles.targetTabs} aria-label={t("保存目标")}>{(["research", "booklist"] as const).map(kind => <button key={kind} aria-pressed={target === kind} disabled={busy || unknown || Boolean(bookRecovery)} onClick={() => { setTarget(kind); setCreating(false); setUndo(null); }}>{kind === "research" ? t("加入研究") : t("加入书单")}</button>)}</div>
          {target === "research" ? <>
            <label className={styles.listSearch}>{t("搜索我的研究")}<input type="search" value={projectQuery} disabled={busy || unknown} onChange={event => setProjectQuery(event.target.value)} /></label><div className={styles.target}><span>{t("我的研究（私人）")}</span><select data-stl-select aria-label={t("选择目标研究")} value={projectId} disabled={busy || unknown} onChange={event => { setProjectId(event.target.value); setUndo(null); }}><option value="">{t("请选择研究")}</option>{projects.filter(row => row.id === projectId || row.data.title.toLocaleLowerCase().includes(projectQuery.trim().toLocaleLowerCase())).map(row => <option key={row.id} value={row.id}>{row.data.title}</option>)}</select><button disabled={busy || unknown} onClick={() => setCreating(value => !value)}>{t("新建")}</button></div>
            {projectError ? <p className={styles.error} role="alert">{t(projectError)}<button onClick={() => setAttempt(value => value + 1)}>{t("重试研究列表")}</button></p> : null}
            {activeProject ? <p className={styles.hint}>{t("共 {count} 条选材", { count: activeProject.data.selections.length })}<Link href={`/account/research/${activeProject.id}`}>{t("查看已有选材")}</Link></p> : null}
          </> : <>
            <label className={styles.listSearch}>{t("查找书单")}<input type="search" value={listQuery} disabled={busy || unknown || Boolean(bookRecovery)} onChange={event => { setListQuery(event.target.value); setListPage(1); setListId(""); }} /></label>
            <div className={styles.target}><select data-stl-select aria-label={t("选择目标书单")} value={listId} disabled={busy || unknown || listLoading || Boolean(bookRecovery)} onChange={event => { setListId(event.target.value); setUndo(null); }}><option value="">{listLoading ? t("正在读取书单…") : t("请选择本人书单")}</option>{lists?.results.map(row => <option key={row.id} value={row.id}>{row.title}</option>)}</select><button disabled={busy || unknown || Boolean(bookRecovery)} onClick={() => setCreating(value => !value)}>{t("新建")}</button></div>
            {listError && !listLoading ? <p className={styles.error} role="alert">{t(listError)}<button onClick={() => setAttempt(value => value + 1)}>{t("重新读取")}</button></p> : null}
            {lists && lists.total_pages > 1 ? <nav className={styles.actions} aria-label={t("书单分页")}><button disabled={busy || unknown || listLoading || listPage <= 1 || Boolean(bookRecovery)} onClick={() => { setListPage(value => value - 1); setListId(""); }}>{t("上一页")}</button><span>{listPage}/{lists.total_pages}</span><button disabled={busy || unknown || listLoading || listPage >= lists.total_pages || Boolean(bookRecovery)} onClick={() => { setListPage(value => value + 1); setListId(""); }}>{t("下一页")}</button></nav> : null}
            {activeList ? <p className={styles.hint}>{t("{count} 部作品", { count: activeList.item_count })}<Link href={`/account/collections/${activeList.id}`}>{t("查看书单")}</Link></p> : null}
          </>}
          {creating ? <div className={styles.newProject}><label>{target === "booklist" ? t("书单名称") : t("研究名称")}<input maxLength={240} value={newTitle} disabled={busy || unknown} onChange={event => setNewTitle(event.target.value)} /></label><button disabled={busy || unknown || !newTitle.trim()} onClick={() => void run(create)}><Plus size={14} />{t(target === "booklist" ? "创建书单" : "创建研究")}</button></div> : null}
        </> : <div className={styles.info}><Info size={16} /><div><strong>{session.status === "loading" ? t("正在核对登录状态") : t("未登录，仅本机保存")}</strong><p>{t("可选择引用文字复制。登录后可将选材保存到本人的研究。")}</p>{session.status === "temporary_error" ? <button onClick={retrySession}>{t("重新验证登录")}</button> : <Link href={`/login?next=${encodeURIComponent(typeof window === "undefined" ? "/" : window.location.pathname + window.location.search)}`}>{t("登录后继续")}</Link>}</div></div>}
        <label className={styles.note}>{t("添加备注（可选）")}<textarea maxLength={200} value={note} disabled={busy || unknown || Boolean(bookRecovery)} onChange={event => setNote(event.target.value)} /><small>{note.length}/200</small></label>
        {target === "booklist" && ownerId ? <><label className={styles.saveSource}><input type="checkbox" checked={saveExcerpt} disabled={busy || unknown || Boolean(bookRecovery)} onChange={event => setSaveExcerpt(event.target.checked)} />{t("同时保存原文与来源信息")}</label><p className={styles.hint}>{t("勾选后，摘录与备注进入本人的阅读记录。未勾选时只加入书目；备注需清空后再保存。")}</p></> : <label className={styles.saveSource}><input type="checkbox" checked disabled readOnly/>{t("同时保存原文与来源信息")}</label>}
        {preview && !hasReference && !sourceLoading ? <p className={styles.hint}>{t("当前为书目引用。选择原文后才能保存摘录；也可取消保存原文，仅加入书单。")}</p> : null}
      </section>
      <div className={styles.actions}><button className={styles.primary} disabled={busy || unknown || editingQuote || !preview || session.status === "loading" || session.status === "temporary_error" || Boolean(bookRecovery) || (target === "booklist" && ownerId ? listLoading || !activeList || saveExcerpt && !hasReference || !saveExcerpt && Boolean(note) : !hasReference || Boolean(ownerId && !projectId))} onClick={() => void run(() => add())}>{pending ? t("处理中…") : ownerId ? t(target === "booklist" ? "加入书单" : "加入研究") : t("保存到本机")}</button></div>
      {bookRecovery ? <div className={styles.info}><div><strong>{t("有一项书单保存需要核对")}</strong><p>{t("已保留原请求标识，页面刷新后也可查询。没有查到操作结果时请先核对书单与阅读记录。")}</p><div className={styles.actions}><button disabled={busy} onClick={() => void run(recoverBook, true)}>{t("查询原结果")}</button>{bookRetryReady ? <button disabled={busy} onClick={() => void run(() => addBook(), true)}>{t("重试原保存")}</button> : null}<Link href={`/account/collections/${bookRecovery.listId}`}>{t("查看书单")}</Link><Link href="/account/notes">{t("查看阅读记录")}</Link></div>{!bookRetryReady ? <><label className={styles.saveSource}><input type="checkbox" checked={recoveryReviewed} onChange={event => setRecoveryReviewed(event.target.checked)} />{t("我已核对原结果，结束这次恢复")}</label><button disabled={busy || !recoveryReviewed} onClick={() => { rememberBook(null); setUnknown(false); setRecoveryReviewed(false); request.current = { fingerprint: "", id: "" }; }}>{t("结束恢复")}</button></> : null}</div></div> : null}
      {notice ? <div className={styles.success} role="status"><Check size={16} /><p>{t(notice)}</p>{undo ? <button disabled={busy || unknown} onClick={() => void run(undoLast)}>{t("撤销")}</button> : null}</div> : null}
      {savedList ? <p className={styles.hint}><Link href={`/account/collections/${savedList}`}>{t("查看已保存书单")}</Link><Link href="/account/notes">{t("查看我的摘录与笔记")}</Link></p> : null}
      {error ? <div className={styles.error} role="alert"><p>{t(error)}</p>{unknown ? <button disabled={pending} onClick={() => { if (failedOperation.current) void run(failedOperation.current, true); }}>{t("重试原操作")}</button> : null}{unknown ? <button onClick={onClose}>{t("关闭后到研究核对结果")}</button> : null}</div> : null}
      <section className={styles.basket}><button className={styles.basketHeading} aria-expanded={basketOpen} onClick={() => setBasketOpen(value => !value)}>{t("本机选材（{count}）", { count: localRows.length })}</button>{basketOpen ? <><p>{t("只保存来源位置与本人备注，原文会在打开时重新核对。")}</p>{localRows.slice(basketPage * 10, basketPage * 10 + 10).map((row, index) => <article key={row.id}><label><input type="checkbox" disabled={busy || unknown || !basketPreview[row.id]} checked={selectedLocal.includes(row.id)} onChange={event => setSelectedLocal(items => event.target.checked ? [...items, row.id] : items.filter(id => id !== row.id))} /><span><strong>{basketPreview[row.id]?.source.title || (row.id in basketPreview ? t("来源暂不可用") : t("正在核对来源…"))}</strong><small>{basketPreview[row.id]?.reference?.quote}</small>{row.note ? <em>{row.note}</em> : null}</span></label><button disabled={busy || unknown} aria-label={t("移除第 {count} 条本机选材", { count: basketPage * 10 + index + 1 })} onClick={() => { try { const rows = readLocalCitationMaterials(); const position = rows.findIndex(item => item.id === row.id); writeLocalCitationMaterials(rows.filter(item => item.id !== row.id)); setUndo({ id: row.id, action: "undo", local: row, position }); setNotice("已移除本机选材，可撤销恢复原位置。"); } catch (reason) { setError(reason instanceof Error ? reason.message : "本机保存失败。"); } }}><Trash2 size={14} /></button></article>)}{localRows.length > 10 ? <div className={styles.actions}><button disabled={basketPage === 0} onClick={() => setBasketPage(value => value - 1)}>{t("上一页")}</button><span>{basketPage + 1}/{Math.ceil(localRows.length / 10)}</span><button disabled={(basketPage + 1) * 10 >= localRows.length} onClick={() => setBasketPage(value => value + 1)}>{t("下一页")}</button></div> : null}{ownerId ? <button className={styles.primary} disabled={busy || unknown || !projectId || !selectedLocal.length} onClick={() => void run(transfer)}>{t("将已选 {count} 条转存到所选研究", { count: selectedLocal.length })}</button> : null}{!localRows.length ? <p>{t("尚无本机选材。")}</p> : null}</> : null}</section>
    </div>
  </div>;
}
