"use client";
import { useRouter } from "next/navigation";

import { confirmAction, confirmLinkNavigation } from "@/lib/ui-dialog";
import { BrandImage } from "../brand-image";

import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import { ArrowLeft, ArrowLeftRight, Check, ChevronRight, Globe2, LockKeyhole, Plus, Search, SlidersHorizontal, Trash2, X } from "lucide-react";
import type { Work } from "@/lib/data";
import type { SiteConfig } from "@/lib/site-config";
import { ApiRequestError, normalizePublicResourceUrl } from "@/lib/api";
import type { Paginated } from "@/lib/api/pagination";
import type { ResolvedEvidence } from "@/lib/api/research.client";
import {
  compactParallelReference, parallelRequest, referenceKey, sameParallelSegment,
  type ParallelAlignment, type ParallelCandidates, type ParallelData, type ParallelRecord,
  type ParallelSegment, type ParallelTerm, type ParallelVersion, type ParallelVersions,
} from "@/lib/api/parallel-reader.client";
import { usePublicSession } from "../public-session-provider";
import { MediaPlacement } from "../media-placement";
import { SiteHeader } from "../site-header";
import { Dialog } from "../ui/dialog";
import { ParallelColumn } from "./parallel-column";
import { useParallelResource } from "./use-parallel-resource";
import { useParallelSave } from "./use-parallel-save";
import styles from "./parallel-reader.module.css";
import { safeResearchReturn } from "@/lib/api/research-navigation";
import { parallelSourceMatches } from "@/lib/api/parallel-navigation";

type Props = { researchContext?: { project?: string; turn?: string; reference?: string; returnTo?: string }; assetId: string; initialPage: number; initialRevision?: string; initialFocus?: string; initialRight?: { assetId: string; revisionId: string }; taskId?: string; work?: Work; siteConfig?: SiteConfig };
type Selection = { reference: ResolvedEvidence; id: string };
type Calibration = {
  id: string; request_id?: string; status: string; scope: "bibliography" | "passages"; notice?: string;
  data: { basis: string; alignments: ParallelAlignment[] }; updated_at: string;
};
type PublicCalibrationPage = Omit<Paginated<Calibration>, "count"> & { count: number | null; notice?: string };
const labels = { confirmed: "已确认对应", no_match: "无对应段", addition: "增补内容" };
const location = (ref: ResolvedEvidence | null | undefined) => !ref ? "无对应段" : ref.source_status !== "available" ? "来源暂不可用" : `PDF 第 ${ref.pdf_page} 页${ref.printed_label ? ` · 书页 ${ref.printed_label}` : ""}`;

export function ParallelReader(props: Props) {
  const { state } = usePublicSession();
  return <ParallelWorkspace key={`${props.assetId}:${props.taskId || ""}:${props.initialRevision || ""}:${props.initialFocus || ""}:${props.initialRight?.assetId || ""}:${props.initialRight?.revisionId || ""}:${state.status === "authenticated" ? state.user?.id : "visitor"}`} {...props}
    ownerId={state.status === "authenticated" ? state.user?.id : undefined} />;
}

function ParallelWorkspace({ assetId, initialPage, initialRevision, initialFocus, initialRight, taskId, work, siteConfig, ownerId, researchContext }: Props & { ownerId?: number }) {
  const versions = useParallelResource<ParallelVersions>(`/catalog/parallel/versions/?asset_id=${encodeURIComponent(assetId)}`);
  const router = useRouter();
  const [leftId, setLeftId] = useState<string | null>(null);
  const [rightId, setRightId] = useState<string | null>(initialRight ? null : "");
  const [record, setRecord] = useState<ParallelRecord | null>(null);
  const left = versions.data?.versions.find(row => leftId === null ? row.asset_id === assetId :
    leftId.startsWith("unavailable:") ? row.asset_id === record?.data.left_asset_id : row.edition_id === leftId);
  const right = versions.data?.versions.find(row => rightId === null ? row.asset_id === initialRight?.assetId : rightId.startsWith("unavailable:") ? row.asset_id === record?.data.right_asset_id : row.edition_id === rightId);
  const initialLeftChanged = !record && leftId === null && Boolean(initialRevision) && !parallelSourceMatches(left, assetId, initialRevision!);
  const initialRightChanged = !record && rightId === null && Boolean(initialRight) && !parallelSourceMatches(right, initialRight!.assetId, initialRight!.revisionId);
  const initialSourceChanged = initialLeftChanged || initialRightChanged;
  const savedSourceUnavailable = Boolean(record && (record.source_available === false || !versions.loading && Boolean(versions.error) || versions.data && (
    left?.asset_id !== record.data.left_asset_id || right?.asset_id !== record.data.right_asset_id ||
    left?.document_revision_id !== record.data.left_document_revision_id || right?.document_revision_id !== record.data.right_document_revision_id)));
  const [leftPage, setLeftPage] = useState(initialPage);
  const [rightPage, setRightPage] = useState(1);
  const [leftSelection, setLeftSelection] = useState<Selection | null>(null);
  const [rightSelection, setRightSelection] = useState<Selection | null>(null);
  const [leftFocus, setLeftFocus] = useState(initialFocus || "");
  const [rightFocus, setRightFocus] = useState("");
  const [leftReady, setLeftReady] = useState(false);
  const [rightReady, setRightReady] = useState(false);
  const [alignments, setAlignments] = useState<ParallelAlignment[]>([]);
  const [terms, setTerms] = useState<ParallelTerm[]>([]);
  const [sync, setSync] = useState(true);
  const [dirty, setDirty] = useState(false);
  const [manual, setManual] = useState(false);
  const [mobileTab, setMobileTab] = useState("versions");
  const [manualTab, setManualTab] = useState("compare");
  const [narrow, setNarrow] = useState(false);
  const [notesExpanded, setNotesExpanded] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 760px)");
    const update = () => setNarrow(media.matches);
    update(); media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  const [decision, setDecision] = useState<ParallelAlignment["status"]>("confirmed");
  const [alignmentNote, setAlignmentNote] = useState("");
  const [editingAlignment, setEditingAlignment] = useState("");
  const [term, setTerm] = useState<ParallelTerm | null>(null);
  const [noteEdit, setNoteEdit] = useState<ParallelAlignment | null>(null);
  const [tasksOpen, setTasksOpen] = useState(false);
  const [tasksPage, setTasksPage] = useState(1);
  const [notice, setNotice] = useState("");
  const [gate, setGate] = useState(false);
  const [loadingTask, setLoadingTask] = useState(false);
  const [taskError, setTaskError] = useState("");
  const [candidates, setCandidates] = useState<{ key: string; data?: ParallelCandidates; error?: string; loading?: boolean } | null>(null);
  const candidateRequest = useRef<AbortController | null>(null);
  const lifetime = useRef<AbortController | null>(null);
  const selectedAsset = left?.asset_id || record?.data.left_asset_id || assetId;
  const savedTasks = useParallelResource<Paginated<ParallelRecord>>(ownerId && tasksOpen ? `/reading/parallel-tasks/?left_asset=${encodeURIComponent(selectedAsset)}&page=${tasksPage}` : "", ownerId);
  const [publicPage, setPublicPage] = useState(1);
  const publicNotes = useParallelResource<PublicCalibrationPage>(`/reading/parallel-calibrations/public/?left_asset=${encodeURIComponent(selectedAsset)}&page=${publicPage}`);
  const [notesTab, setNotesTab] = useState<"private" | "public">("private");
  const [submitOpen, setSubmitOpen] = useState(false);
  const [scope, setScope] = useState<"bibliography" | "passages">("bibliography");
  const [basis, setBasis] = useState("");
  const [submitState, setSubmitState] = useState({ pending: false, unknown: false, error: "" });
  const submission = useRef<{ requestId: string; body: string } | null>(null);
  const submitPending = useRef(false);
  const [selectedAlignment, setSelectedAlignment] = useState("");
  const save = useParallelSave(ownerId, result => {
    setRecord(result); setAlignments(result.data.alignments); setTerms(result.data.terms); setDirty(false);
    setNotice("已保存到我的对齐，仅自己可见。"); savedTasks.reload();
    const url = new URL(window.location.href); url.searchParams.set("alignment", result.id);
    window.history.replaceState(window.history.state, "", url);
  });
  const [initialTaskPending, setInitialTaskPending] = useState(Boolean(taskId && ownerId));
  const locked = save.pending || save.unknown || Boolean(save.conflictTaskId) || submitState.pending || submitState.unknown || loadingTask || initialTaskPending;
  const inputDirty = dirty || Boolean(term) || Boolean(noteEdit) || Boolean(alignmentNote.trim()) || Boolean(basis.trim());
  async function canLeave() {
    if (save.pending || submitState.pending) return false;
    return !(inputDirty || save.unknown || submitState.unknown) || (await confirmAction(save.unknown || submitState.unknown
      ? "保存结果尚未核对，离开会失去本页的查询入口。仍要离开吗？"
      : "有尚未保存的对齐或笔记，离开会丢失本次输入。仍要离开吗？"));
  }
  useEffect(() => {
    const controller = new AbortController(); lifetime.current = controller;
    return () => { controller.abort(); candidateRequest.current?.abort(); };
  }, []);
  useEffect(() => {
    if (!inputDirty && !save.unknown && !save.pending && !submitState.unknown && !submitState.pending) return;
    const prevent = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", prevent);
    return () => window.removeEventListener("beforeunload", prevent);
  }, [inputDirty, save.unknown, save.pending, submitState.unknown, submitState.pending]);

  function restore(result: ParallelRecord) {
    save.clearConflict();
    const data = result.data;
    const sourceLeft = versions.data?.versions.find(row => row.asset_id === data.left_asset_id);
    const sourceRight = versions.data?.versions.find(row => row.asset_id === data.right_asset_id);
    setLeftId(sourceLeft?.edition_id || `unavailable:${data.left_asset_id}`); setRightId(sourceRight?.edition_id || `unavailable:${data.right_asset_id}`);
    setLeftPage(data.positions.left_page); setRightPage(data.positions.right_page);
    const findPosition = (side: "left" | "right") => {
      const id = data.positions[`${side}_segment_id`];
      const ref = [...data.alignments, ...data.terms].map(row => row[side]).find(value => value &&
        value.source_status === "available" && (value.reference_id === id || value.evidence_span_id === id));
      return ref ? { reference: ref, id: ref.reference_id || ref.evidence_span_id || "" } : null;
    };
    setLeftSelection(findPosition("left")); setRightSelection(findPosition("right"));
    setLeftFocus(data.positions.left_segment_id || ""); setRightFocus(data.positions.right_segment_id || "");
    setRecord(result); setAlignments(data.alignments); setTerms(data.terms); setSync(data.sync_scroll);
    setDirty(false); setManual(false); setAlignmentNote(""); setTerm(null); setNoteEdit(null); setTaskError(""); setTasksOpen(false);
    setPublicPage(1); setTasksPage(1);
    setNotice(!sourceLeft || !sourceRight ? "私人对齐已读取，部分来源当前不可用。保留的笔记仍仅自己可见。" : "已恢复两个版本的阅读位置。");
    const url = new URL(window.location.href); url.searchParams.set("alignment", result.id); window.history.replaceState(window.history.state, "", url);
  }
  async function loadTask(id: string) {
    if (initialTaskPending || loadingTask || save.pending || save.unknown || submitState.pending || submitState.unknown) return;
    if (!ownerId) { setGate(true); return; }
    if (!(await canLeave())) return;
    setLoadingTask(true); setTaskError("");
    try {
      const result = await parallelRequest<ParallelRecord>(`/reading/parallel-tasks/${encodeURIComponent(id)}/`, { signal: lifetime.current?.signal }, ownerId);
      if (!lifetime.current?.signal.aborted) restore(result);
    } catch (reason) { if (!lifetime.current?.signal.aborted) setTaskError(reason instanceof Error ? reason.message : "读取私人对齐失败。"); }
    finally { if (!lifetime.current?.signal.aborted) setLoadingTask(false); }
  }
  const restoreInitial = useEffectEvent(restore);
  const initialTaskState = useRef<{ id: string; done: boolean } | null>(null);
  const versionsReady = !versions.loading;
  useEffect(() => {
    if (!taskId || !ownerId || !versionsReady || initialTaskState.current?.id === taskId && initialTaskState.current.done) return;
    const controller = new AbortController();
    initialTaskState.current = { id: taskId, done: false };
    void parallelRequest<ParallelRecord>(`/reading/parallel-tasks/${encodeURIComponent(taskId)}/`, { signal: controller.signal }, ownerId)
      .then(result => { if (!controller.signal.aborted) { initialTaskState.current = { id: taskId, done: true }; setInitialTaskPending(false); restoreInitial(result); } })
      .catch(reason => { if (!controller.signal.aborted) { initialTaskState.current = { id: taskId, done: true }; setInitialTaskPending(false); setTaskError(reason instanceof Error ? reason.message : "读取私人对齐失败。"); } });
    return () => controller.abort();
  }, [taskId, ownerId, versionsReady]);

  async function changeVersion(side: "left" | "right", id: string) {
    if (locked || !(await canLeave())) return;
    if (side === "left") { setLeftId(id); setLeftPage(1); setLeftSelection(null); setLeftFocus(""); }
    else { setRightId(id); setRightPage(1); setRightSelection(null); setRightFocus(""); }
    setAlignments([]); setTerms([]); setRecord(null); setDirty(false); setManual(false); setAlignmentNote(""); setEditingAlignment("");
    setBasis(""); setSelectedAlignment(""); setTerm(null); setNoteEdit(null); setPublicPage(1); setTasksPage(1);
    setNotice("已切换版本，接下来保存为新的私人对齐任务。原已保存任务保留。");
    const url = new URL(window.location.href); url.searchParams.delete("alignment"); window.history.replaceState(window.history.state, "", url);
  }
  function swap() {
    if (!left || !right || locked || initialSourceChanged) return;
    setLeftId(right.edition_id); setRightId(left.edition_id); setLeftPage(rightPage); setRightPage(leftPage);
    setLeftSelection(rightSelection); setRightSelection(leftSelection); setLeftFocus(rightFocus); setRightFocus(leftFocus);
    setAlignments(rows => rows.map(row => ({ ...row, left: row.right, right: row.left, status: row.status === "no_match" ? "addition" : row.status === "addition" ? "no_match" : row.status })));
    setTerms(rows => rows.map(row => ({ ...row, original: row.translation, translation: row.original, left: row.right, right: row.left })));
    setRecord(null); setDirty(true); setNotice("已交换左右版本。保存时会新建反向对齐任务，原任务保留。");
    setPublicPage(1); setTasksPage(1);
    const url = new URL(window.location.href); url.searchParams.delete("alignment"); window.history.replaceState(window.history.state, "", url);
  }
  function go(side: "left" | "right", page: number) {
    if (side === "left") { setLeftPage(page); setLeftSelection(null); setLeftFocus(""); }
    else { setRightPage(page); setRightSelection(null); setRightFocus(""); }
  }
  function locate(side: "left" | "right", ref: ResolvedEvidence | null) {
    if (!ref || ref.source_status !== "available" || !ref.pdf_page) return;
    const focus = ref.reference_id || ref.evidence_span_id || "";
    const selection = { reference: ref, id: focus };
    if (side === "left") { setLeftPage(ref.pdf_page); setLeftSelection(selection); setLeftFocus(focus); }
    else { setRightPage(ref.pdf_page); setRightSelection(selection); setRightFocus(focus); }
  }
  const scrollAnchor = useRef("");
  function synchronize(side: "left" | "right", segment: ParallelSegment) {
    if (!sync || manual || locked) return;
    const pair = alignments.find(row => row.status === "confirmed" && sameParallelSegment(row[side], segment.reference));
    if (!pair || scrollAnchor.current === pair.id) return;
    scrollAnchor.current = pair.id;
    locate(side === "left" ? "right" : "left", pair[side === "left" ? "right" : "left"]);
  }
  const currentLeft = leftReady && leftSelection && leftSelection.reference.asset_id === left?.asset_id && leftSelection.reference.pdf_page === leftPage &&
    leftSelection.reference.document_revision_id === left?.document_revision_id ? leftSelection : null;
  const currentRight = rightReady && rightSelection && rightSelection.reference.asset_id === right?.asset_id && rightSelection.reference.pdf_page === rightPage &&
    rightSelection.reference.document_revision_id === right?.document_revision_id ? rightSelection : null;
  const candidateKey = `${referenceKey(currentLeft?.reference)}:${right?.asset_id}:${right?.document_revision_id}`;
  const candidateState = candidates?.key === candidateKey ? candidates : null;
  async function findCandidates() {
    if (!currentLeft || !right?.asset_id || !right.document_revision_id || initialSourceChanged) return;
    candidateRequest.current?.abort();
    const controller = new AbortController(); candidateRequest.current = controller;
    setCandidates({ key: candidateKey, loading: true });
    try {
      const data = await parallelRequest<ParallelCandidates>("/catalog/parallel/candidates/", {
        method: "POST", signal: controller.signal, body: JSON.stringify({ left_reference: compactParallelReference(currentLeft.reference),
          target_asset_id: right.asset_id, target_document_revision_id: right.document_revision_id }),
      });
      if (!controller.signal.aborted) setCandidates({ key: candidateKey, data });
    } catch (reason) { if (!controller.signal.aborted) setCandidates({ key: candidateKey, error: reason instanceof Error ? reason.message : "候选读取失败，可继续手动定位。" }); }
  }
  function addAlignment() {
    if (!ownerId) { setGate(true); return; }
    const leftRef = decision === "addition" ? null : currentLeft?.reference || null;
    const rightRef = decision === "no_match" ? null : currentRight?.reference || null;
    if (decision !== "addition" && !leftRef || decision !== "no_match" && !rightRef || locked || initialSourceChanged) return;
    const row = { id: editingAlignment || createRequestKey(), left: leftRef, right: rightRef, status: decision, note: alignmentNote };
    const nextAlignments = [...alignments.filter(item => item.id !== row.id), row];
    setAlignments(nextAlignments); setSelectedAlignment(row.id);
    setDirty(true); setManual(false); setAlignmentNote(""); setEditingAlignment("");
    const data = dataToSave();
    if (data) save.save({ ...data, alignments: nextAlignments }, record);
  }
  function dataToSave(): ParallelData | null {
    if (initialSourceChanged) return null;
    const leftAsset = record?.data.left_asset_id || left?.asset_id, rightAsset = record?.data.right_asset_id || right?.asset_id;
    const leftRevision = record?.data.left_document_revision_id || left?.document_revision_id, rightRevision = record?.data.right_document_revision_id || right?.document_revision_id;
    if (!leftAsset || !rightAsset || !leftRevision || !rightRevision || leftAsset === rightAsset) return null;
    return { left_asset_id: leftAsset, right_asset_id: rightAsset,
      left_document_revision_id: record?.data.left_document_revision_id || leftRevision, right_document_revision_id: record?.data.right_document_revision_id || rightRevision,
      positions: savedSourceUnavailable && record ? record.data.positions : { left_page: leftPage, right_page: rightPage, left_segment_id: currentLeft?.reference.reference_id || currentLeft?.reference.evidence_span_id || (record?.data.positions.left_page === leftPage ? record.data.positions.left_segment_id : "") || "", right_segment_id: currentRight?.reference.reference_id || currentRight?.reference.evidence_span_id || (record?.data.positions.right_page === rightPage ? record.data.positions.right_segment_id : "") || "" },
      sync_scroll: sync, alignments, terms };
  }
  function saveTask() {
    if (!ownerId) { setGate(true); return; }
    if (manual) { setNotice("请先确认当前段落对齐，再保存整个任务。"); return; }
    const data = dataToSave(); if (data) save.save(data, record);
  }
  function editAlignment(row: ParallelAlignment) {
    if (savedSourceUnavailable) { setNoteEdit({ ...row }); return; }
    locate("left", row.left); locate("right", row.right); setDecision(row.status); setAlignmentNote(row.note);
    setEditingAlignment(row.id); setSelectedAlignment(row.id); setManual(true); setManualTab("compare");
  }
  async function submitPublic(recover = false) {
    if (!ownerId || !record || submitPending.current) return;
    if (!recover) {
      if (dirty || !basis.trim() || scope === "passages" && !selectedAlignment) return;
      submission.current = { requestId: createRequestKey(), body: "" };
      submission.current.body = JSON.stringify({ request_id: submission.current.requestId, task_id: record.id,
        expected_revision: record.revision, scope, basis: basis.trim(), ...(scope === "passages" ? { alignment_id: selectedAlignment } : {}) });
    }
    const operation = submission.current; if (!operation) return;
    submitPending.current = true; setSubmitState(previous => ({ ...previous, pending: true, error: "" }));
    try {
      let receipt: Calibration | null = null;
      if (recover) {
        try { receipt = await parallelRequest<Calibration>(`/reading/parallel-calibrations/by-request/?request_id=${operation.requestId}`, { signal: lifetime.current?.signal }, ownerId); }
        catch (error) { if (!(error instanceof ApiRequestError) || error.status !== 404) throw error; }
      }
      receipt ??= await parallelRequest<Calibration>("/reading/parallel-calibrations/", { method: "POST", body: operation.body, signal: lifetime.current?.signal }, ownerId);
      if (lifetime.current?.signal.aborted) return;
      if (!receipt?.id || receipt.request_id && receipt.request_id !== operation.requestId) throw new ApiRequestError("投稿操作结果未能核对，请保留输入并查询原请求。", 0);
      submission.current = null; setBasis(""); setSubmitOpen(false); setSubmitState({ pending: false, unknown: false, error: "" });
      setNotice(`公共校准已提交，等待审核。${receipt.notice || "私人笔记与术语未随提交公开。"}`);
    } catch (reason) {
      if (lifetime.current?.signal.aborted) return;
      const unknown = recover || !(reason instanceof ApiRequestError) || [0, 408, 429].includes(reason.status) || reason.status >= 500;
      if (!unknown) submission.current = null;
      setSubmitState({ pending: false, unknown, error: reason instanceof Error ? reason.message : "提交未完成，输入保留。" });
    } finally { submitPending.current = false; }
  }
  const versionSelector = (side: "left" | "right", current: ParallelVersion | undefined) => <label className="parallel-version-select"><span>{side === "left" ? "左侧版本" : "右侧版本"}</span><select data-stl-select value={current?.edition_id || ""} disabled={locked || loadingTask} onChange={event => changeVersion(side, event.target.value)}><option value="">选择版本</option>{versions.data?.versions.map(item => <option key={item.edition_id} value={item.edition_id} disabled={item.edition_id === (side === "left" ? right?.edition_id : left?.edition_id)}>{item.title} · {item.publication_year || "年份待补"} · {item.language || "语言待补"}{item.state === "metadata_only" ? "（暂无正文）" : ""}</option>)}</select><small>{current ? `${current.version_label || "版本信息待补"} · PDF ${side === "left" ? leftPage : rightPage} / ${current.total_pages || "—"} 页` : "选择同一作品已关联的出版版本"}</small></label>;
  const currentPairAvailable = Boolean(left?.asset_id && right?.asset_id && left.asset_id !== right.asset_id &&
    left.document_revision_id && right.document_revision_id && !savedSourceUnavailable && !initialSourceChanged);

  const singleReaderQuery = new URLSearchParams({ page: String(left?.asset_id ? leftPage : initialPage) });
  const singleReaderRevision = leftId === null ? initialRevision || left?.document_revision_id : left?.document_revision_id;
  if (singleReaderRevision) singleReaderQuery.set("revision", singleReaderRevision);
  if (leftFocus) singleReaderQuery.set("focus", leftFocus);
  const researchReturn = safeResearchReturn(researchContext?.returnTo || "");
  if (researchReturn) singleReaderQuery.set("return_to", researchReturn);
  if (!left?.asset_id || left.asset_id === assetId) {
    if (researchContext?.project) singleReaderQuery.set("research_project", researchContext.project);
    if (researchContext?.turn) singleReaderQuery.set("research_turn", researchContext.turn);
    if (researchContext?.reference) singleReaderQuery.set("reference", researchContext.reference);
  }

  return <div className={styles.root} data-manual={manual} data-tab={mobileTab} data-manual-tab={manualTab} onClickCapture={event => {
    const link = (event.target as HTMLElement).closest<HTMLAnchorElement>("a[href]");
    if (!event.defaultPrevented && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && link && !link.target && !link.getAttribute("href")?.startsWith("#") && (inputDirty || save.unknown || submitState.unknown || save.pending || submitState.pending)) void confirmLinkNavigation(event, link, canLeave, href => router.push(href));
  }}>
    <SiteHeader reader readerReference={manual ? "parallel-manual" : "parallel"} config={siteConfig} beforeLogout={canLeave} />
    <main className="parallel-main">
      <nav className="parallel-breadcrumb" aria-label="面包屑"><Link href="/home">首页</Link><ChevronRight size={12} /><Link href="/explore">书库检索</Link><ChevronRight size={12} /><span>{manual ? "手动对齐与私人保存" : "原文与译本并读"}</span></nav>
      <header className="parallel-heading"><div><h1>{manual ? "手动对齐与私人保存" : "原文与译本并读"}</h1></div>{manual ? <div className="parallel-task-heading"><div><small>当前对齐任务（私人）</small><strong>{work?.title || left?.title || "文献对照"}</strong><span>{work?.author || left?.authors.join(" · ")}</span></div><div className="parallel-task-state"><small>保存状态</small><strong>{save.pending ? "正在保存…" : save.unknown ? "保存结果待核对" : record && !dirty ? "已保存至我的对齐" : "尚有未保存内容"}</strong><span><LockKeyhole size={12} />仅自己可见</span></div><button type="button" disabled={!record || dirty || locked} onClick={() => setSubmitOpen(true)}><Globe2 size={20} /><span>提交为公共校准<small>需补充说明与范围</small></span></button></div> : <><div className="parallel-book">{work?.coverImage ? <MediaPlacement uses={work.coverDisplayUses}><img src={normalizePublicResourceUrl(work.coverImage)} width={56} height={78} alt={`${work.title}封面`} /></MediaPlacement> : null}<div><strong>{work?.title || left?.title || "文献对照"}</strong><small>{work?.author || left?.authors.join(" · ")}</small><small>{work?.originalTitle || left?.original_title}</small></div></div><Link className="button secondary" href={`/reader/${encodeURIComponent(left?.asset_id || assetId)}?${singleReaderQuery}`}><ArrowLeft size={15} />返回单文献阅读</Link></>}</header>
      {notice ? <p className="parallel-notice" role="status"><Check size={15} />{notice}<button type="button" aria-label="关闭提示" onClick={() => setNotice("")}><X size={14} /></button></p> : null}
      {versions.loading ? <p role="status">正在读取可用版本…</p> : versions.error ? <p role="alert">{versions.error}<button type="button" onClick={versions.reload}>重新读取版本</button></p> : null}
      {versions.data?.truncated ? <p className="parallel-notice">当前显示部分已关联版本。可从文献详情选择另一个版本进入。</p> : null}
      {taskError ? <p className="parallel-notice" role="alert">{taskError}<button type="button" onClick={() => void loadTask(record?.id || taskId || "")}>重新读取私人任务</button></p> : null}
      {initialTaskPending || loadingTask ? <p className="parallel-notice" role="status">正在恢复私人对齐和两侧原文位置…</p> : null}
      {taskId && !ownerId ? <p className="parallel-notice">登录本人账户后可恢复私人对齐。<button type="button" onClick={() => setGate(true)}>登录</button></p> : null}
      {initialSourceChanged && !versions.loading && !versions.error ? <p className="parallel-notice" role="alert">链接所指的文件修订已经变化或不可访问。尚未读取替换版本的正文；请明确选择当前版本后重新定位，原研究引用不会修改。<button type="button" disabled={locked} onClick={() => { if (initialLeftChanged) changeVersion("left", left?.edition_id || ""); else changeVersion("right", right?.edition_id || ""); }}>使用当前{initialLeftChanged ? "左侧" : "右侧"}版本重新定位</button></p> : null}
      {savedSourceUnavailable ? <p className="parallel-notice">{record?.notice || "已保存的来源发生变化。可以编辑已有私人笔记，新增对齐须重新选择当前版本。"}<button type="button" disabled={locked} onClick={() => changeVersion("right", right?.edition_id || "")}>开始新的并读</button></p> : null}
      <nav className="parallel-mobile-tabs" aria-label={manual ? "对齐内容" : "并读内容"}>{(manual ? [["compare", "对照"], ["candidates", "候选"], ["notes", "笔记"]] : [["versions", "版本选择"], ["reading", "阅读方式"], ["notes", "对齐与笔记"]]).map(([value, label]) => <button type="button" key={value} aria-pressed={(manual ? manualTab : mobileTab) === value} onClick={() => manual ? setManualTab(value) : setMobileTab(value)}>{label}</button>)}</nav>
      <section className="parallel-version-bar" aria-label="选择版本并定位章节"><h2>选择版本并定位章节</h2>{versionSelector("left", left)}<button className="parallel-swap" type="button" aria-label="交换左右版本" disabled={!left || !right || locked} onClick={swap}><ArrowLeftRight size={21} /></button>{versionSelector("right", right)}<div className="parallel-reading-mode"><span>阅读方式</span><div><button type="button" disabled={locked} aria-pressed={sync} onClick={() => { setSync(true); setDirty(true); }}>同步滚动</button><button type="button" disabled={locked} aria-pressed={!sync} onClick={() => { setSync(false); setDirty(true); }}>独立滚动</button></div><small>同步跟随已确认的对应段。</small></div></section>
      <div className="parallel-columns"><ParallelColumn key={`left:${left?.asset_id}:${left?.document_revision_id}`} side="left" versionControl={manual ? versionSelector("left", left) : undefined} version={initialLeftChanged ? undefined : left} page={leftPage} segmentId={currentLeft?.id || ""} focusId={leftFocus} selectedReference={leftSelection?.reference} onReady={setLeftReady} onPage={page => go("left", page)} onSelect={segment => setLeftSelection({ id: segment.id, reference: segment.reference })} onScrollSegment={segment => synchronize("left", segment)} /><span className="parallel-between" aria-hidden="true"><ArrowLeftRight size={19} /></span><ParallelColumn key={`right:${right?.asset_id}:${right?.document_revision_id}`} side="right" versionControl={manual ? versionSelector("right", right) : undefined} version={initialRightChanged ? undefined : right} page={rightPage} segmentId={currentRight?.id || ""} focusId={rightFocus} selectedReference={rightSelection?.reference} onReady={setRightReady} onPage={page => go("right", page)} onSelect={segment => setRightSelection({ id: segment.id, reference: segment.reference })} onScrollSegment={segment => synchronize("right", segment)} /></div>
      {manual ? <div className="parallel-manual-bottom"><section className="parallel-candidates"><div className="parallel-section-heading"><h2>候选对齐{candidateState?.data ? `（${candidateState.data.candidates.length}）` : ""}</h2><button type="button" disabled={!currentLeft || !right?.asset_id || candidateState?.loading} onClick={() => void findCandidates()}><Search size={14} />查找候选</button></div>{candidateState?.loading ? <p role="status">正在查找所选版本中的候选段落…<button type="button" onClick={() => { candidateRequest.current?.abort(); setCandidates({ key: candidateKey, error: "已停止查找，可以继续手动定位。" }); }}>停止查找</button></p> : null}{candidateState?.error ? <p role="alert">{candidateState.error}</p> : null}{candidateState?.data?.notice ? <p>{candidateState.data.notice}</p> : null}<div className="parallel-candidate-cards">{candidateState?.data?.candidates.map((candidate, index) => <button type="button" key={referenceKey(candidate.reference)} aria-pressed={decision === "confirmed" && referenceKey(currentRight?.reference) === referenceKey(candidate.reference)} onClick={() => { locate("right", candidate.reference); setDecision("confirmed"); }}><b>{index + 1}</b><span><strong>{candidate.label}</strong><small>{location(candidate.reference)} · 待确认</small><q>{candidate.text}</q>{candidate.text_truncated ? <small>候选仅显示部分正文，请定位后核对完整原文。</small> : null}</span></button>)}<button type="button" aria-pressed={decision === "no_match"} onClick={() => setDecision("no_match")}><span><strong>无对应段</strong><small>明确记录左侧段落无对应译文</small></span></button><button type="button" aria-pressed={decision === "addition"} onClick={() => setDecision("addition")}><span><strong>增补内容</strong><small>明确记录右侧独有的段落</small></span></button></div><p className="parallel-source-notice">候选仅供核对。没有返回候选，不代表原文没有对应段。</p></section><section className="parallel-manual-summary"><h2>当前选择</h2><p>左：{decision === "addition" ? "无对应段" : location(currentLeft?.reference)}</p><p>右：{decision === "no_match" ? "无对应段" : location(currentRight?.reference)}</p><label>添加笔记（可选）<textarea rows={3} maxLength={4000} value={alignmentNote} onChange={event => setAlignmentNote(event.target.value)} /></label><div className="parallel-inline-actions"><button type="button" onClick={async () => { if (!alignmentNote || (await confirmAction("放弃这次尚未确认的对齐笔记？"))) { setManual(false); setAlignmentNote(""); setEditingAlignment(""); } }}>取消</button><button className="button" type="button" disabled={locked || !currentPairAvailable || decision !== "addition" && !currentLeft || decision !== "no_match" && !currentRight} onClick={addAlignment}>保存到我的对齐</button></div></section></div> : <div className="parallel-bottom"><section className="parallel-alignment-list"><div className="parallel-section-heading"><h2>段落对齐与定位</h2><button type="button" disabled={!currentPairAvailable || locked} onClick={() => { setManual(true); setDecision("confirmed"); setManualTab("compare"); setEditingAlignment(""); setAlignmentNote(""); }}><SlidersHorizontal size={14} />手动调整对齐</button></div>{alignments.length ? <div className="parallel-table-scroll"><table><thead><tr><th>原文定位</th><th>译文定位</th><th>状态</th><th><span className="sr-only">操作</span></th></tr></thead><tbody>{alignments.map(row => <tr key={row.id} className={selectedAlignment === row.id ? "is-selected" : ""}><td><button type="button" onClick={() => { locate("left", row.left); locate("right", row.right); setSelectedAlignment(row.id); }}>{location(row.left)}</button></td><td>{location(row.right)}</td><td>{labels[row.status]}</td><td><button type="button" disabled={locked} onClick={() => editAlignment(row)}>调整</button><button type="button" disabled={locked} aria-label="删除这条私人对齐" onClick={async () => { if ((await confirmAction("从当前私人任务移除这条对齐？保存后生效。"))) { setAlignments(items => items.filter(item => item.id !== row.id)); setDirty(true); } }}><Trash2 size={13} /></button></td></tr>)}</tbody></table></div> : <p className="parallel-empty">还没有已确认的段落对齐。选择左右版本后，可手动定位并确认对应关系。</p>}</section><details data-disclosure="collection" className="parallel-notes" open={!narrow || mobileTab === "notes" || notesExpanded} onToggle={event => { if (narrow && mobileTab !== "notes") setNotesExpanded(event.currentTarget.open); }}><summary>术语差异与笔记（{terms.length}）</summary><div className="parallel-section-heading"><h2>术语差异与笔记</h2><button type="button" disabled={locked || !currentPairAvailable} onClick={() => { if (!ownerId) setGate(true); else setTerm({ id: createRequestKey(), original: "", translation: "", note: "", left: currentLeft?.reference, right: currentRight?.reference }); }}><Plus size={15} />新增术语笔记</button></div><div className="parallel-note-tabs"><button type="button" aria-pressed={notesTab === "private"} onClick={() => setNotesTab("private")}>我的笔记（{terms.length}）</button><button type="button" aria-pressed={notesTab === "public"} onClick={() => setNotesTab("public")}>公共校准</button></div>{notesTab === "private" ? terms.length ? <div className="parallel-table-scroll"><table><thead><tr><th>术语（原文）</th><th>译文</th><th>备注与出处</th><th><span className="sr-only">操作</span></th></tr></thead><tbody>{terms.map(row => <tr key={row.id}><td>{row.original}</td><td>{row.translation}</td><td>{row.note}<small>{row.left ? location(row.left) : ""}{row.right ? ` / ${location(row.right)}` : ""}</small></td><td><button type="button" disabled={locked} onClick={() => setTerm({ ...row })}>编辑</button><button type="button" disabled={locked} aria-label="删除术语笔记" onClick={async () => { if ((await confirmAction("从当前私人任务移除这条术语笔记？保存后生效。"))) { setTerms(items => items.filter(item => item.id !== row.id)); setDirty(true); } }}><Trash2 size={13} /></button></td></tr>)}</tbody></table></div> : <p className="parallel-empty">术语笔记仅自己可见，可保留两侧原文位置。</p> : publicNotes.loading ? <p role="status">正在读取公开校准…</p> : publicNotes.error ? <p role="alert">{publicNotes.error}<button type="button" onClick={publicNotes.reload}>重试</button></p> : publicNotes.data?.results.length ? <ul className="parallel-public-notes">{publicNotes.data.results.map(row => <li key={row.id}><small>公开 · {row.scope === "bibliography" ? "书目校准" : "段落校准"}</small><p>{row.data.basis}</p>{row.scope === "passages" ? row.data.alignments.map(item => <div key={item.id}>{item.left?.source_status === "available" ? <blockquote>{item.left.quote}</blockquote> : null}{item.right?.source_status === "available" ? <blockquote>{item.right.quote}</blockquote> : null}</div>) : null}</li>)}</ul> : <p className="parallel-empty">当前没有可展示的公开校准。</p>}{notesTab === "public" ? <><p className="parallel-source-notice">{publicNotes.data?.notice}</p><div className="parallel-inline-actions"><button type="button" disabled={publicPage === 1 || publicNotes.loading} onClick={() => setPublicPage(value => value - 1)}>上一页校准</button><button type="button" disabled={!publicNotes.data?.next || publicNotes.loading} onClick={() => setPublicPage(value => value + 1)}>下一页校准</button></div></> : null}</details></div>}
      <footer className="parallel-save-bar" hidden={manual}><div><LockKeyhole size={15} /><span>{record ? `已保存私人任务 · 修订 ${record.revision}${dirty ? " · 有未保存修改" : ""}` : "私人对齐与笔记（默认）"}</span><button type="button" disabled={locked} onClick={() => ownerId ? setTasksOpen(true) : setGate(true)}>我的对齐</button></div><div><button type="button" disabled={!record || dirty || locked} onClick={() => setSubmitOpen(true)}><Globe2 size={15} />提交公共校准</button><button className="button" type="button" disabled={(!currentPairAvailable && !record) || locked || manual} onClick={saveTask}>{save.pending ? "正在保存…" : "保存到我的对齐"}</button></div></footer>
      {save.error ? <p className="parallel-notice" role="alert">{save.error}{save.unknown ? <button type="button" disabled={save.pending} onClick={save.retry}>核对原保存结果</button> : save.conflict && (record?.id || save.conflictTaskId) ? <button type="button" onClick={() => void loadTask(record?.id || save.conflictTaskId)}>读取最新任务</button> : null}</p> : null}
      <footer className="parallel-brand-footer"><BrandImage config={siteConfig ?? undefined} /></footer>
    </main>
    <Dialog className="parallel-dialog" open={Boolean(noteEdit)} onRequestClose={async () => { if (!noteEdit || (await confirmAction("放弃这次对齐笔记编辑？"))) setNoteEdit(null); }} aria-labelledby="parallel-note-heading">{noteEdit ? <form onSubmit={event => { event.preventDefault(); setAlignments(rows => rows.map(row => row.id === noteEdit.id ? { ...row, note: noteEdit.note } : row)); setNoteEdit(null); setDirty(true); }}><header><h2 id="parallel-note-heading">编辑私人对齐笔记</h2><button type="button" aria-label="关闭对齐笔记" onClick={async () => { if ((await confirmAction("放弃这次对齐笔记编辑？"))) setNoteEdit(null); }}><X size={18} /></button></header><p>来源目前不可用。已有对应关系与原文位置保留，可以继续修改自己的笔记。</p><label>对齐笔记<textarea autoFocus rows={6} maxLength={8000} value={noteEdit.note} onChange={event => setNoteEdit({ ...noteEdit, note: event.target.value })} /></label><button className="button" type="submit">保留到当前任务</button></form> : null}</Dialog>
    <Dialog className="parallel-dialog" open={Boolean(term)} onRequestClose={async () => { if (!term || (await confirmAction("放弃这次术语编辑？"))) setTerm(null); }} aria-labelledby="parallel-term-heading">{term ? <form onSubmit={event => { event.preventDefault(); setTerms(rows => [...rows.filter(row => row.id !== term.id), term]); setTerm(null); setDirty(true); }}><header><h2 id="parallel-term-heading">术语差异与笔记</h2><button type="button" aria-label="关闭术语编辑" onClick={async () => { if ((await confirmAction("放弃这次术语编辑？"))) setTerm(null); }}><X size={18} /></button></header><label>原文术语<input autoFocus required maxLength={200} value={term.original} onChange={event => setTerm({ ...term, original: event.target.value })} /></label><label>译文<input required maxLength={200} value={term.translation} onChange={event => setTerm({ ...term, translation: event.target.value })} /></label><label>备注与出处<textarea rows={5} maxLength={4000} value={term.note} onChange={event => setTerm({ ...term, note: event.target.value })} /></label><p><LockKeyhole size={13} />仅自己可见。当前选中的两侧原文位置一并保留。</p><button className="button" type="submit">保留到当前任务</button></form> : null}</Dialog>
    <Dialog className="parallel-dialog" open={tasksOpen} onRequestClose={() => setTasksOpen(false)} aria-labelledby="parallel-tasks-heading"><header><h2 id="parallel-tasks-heading">我的对齐</h2><button type="button" aria-label="关闭我的对齐" onClick={() => setTasksOpen(false)}><X size={18} /></button></header>{savedTasks.loading ? <p role="status">正在读取本人任务…</p> : savedTasks.error ? <p role="alert">{savedTasks.error}<button type="button" onClick={savedTasks.reload}>重试</button></p> : savedTasks.data?.results.length ? <ul className="parallel-task-list">{savedTasks.data.results.map(item => <li key={item.id}><button type="button" disabled={locked} onClick={() => void loadTask(item.id)}><strong>{item.data.alignments.length} 条对齐 · {item.data.terms.length} 条术语笔记</strong><small>左 PDF {item.data.positions.left_page} 页 / 右 PDF {item.data.positions.right_page} 页 · 修订 {item.revision}</small></button></li>)}</ul> : <p>还没有这本文献的私人对齐任务。</p>}<div className="parallel-inline-actions"><button type="button" disabled={tasksPage === 1} onClick={() => setTasksPage(value => value - 1)}>上一页</button><button type="button" disabled={!savedTasks.data?.next} onClick={() => setTasksPage(value => value + 1)}>下一页</button></div><Link href="/account?section=privacy">在隐私与资料中导出或删除</Link></Dialog>
    <Dialog className="parallel-dialog" open={submitOpen} onRequestClose={() => { if (!submitState.pending && !submitState.unknown) setSubmitOpen(false); }} aria-labelledby="parallel-submit-heading"><form onSubmit={event => { event.preventDefault(); void submitPublic(); }}><header><h2 id="parallel-submit-heading">提交为公共校准</h2><button type="button" aria-label="关闭公共校准" disabled={submitState.pending || submitState.unknown} onClick={() => setSubmitOpen(false)}><X size={18} /></button></header><p>公共校准是独立投稿。审核采用后才展示，不会公开你的私人笔记。</p><fieldset disabled={submitState.pending || submitState.unknown}><legend>公开范围</legend><label><input type="radio" name="parallel-scope" checked={scope === "bibliography"} onChange={() => setScope("bibliography")} />仅书目级，不显示具体段落</label><label><input type="radio" name="parallel-scope" checked={scope === "passages"} onChange={() => setScope("passages")} />显示所选段落，需说明依据</label>{scope === "passages" ? <label>选择已保存的对齐<select data-stl-select required value={selectedAlignment} onChange={event => setSelectedAlignment(event.target.value)}><option value="">选择对齐</option>{alignments.map(row => <option key={row.id} value={row.id}>{location(row.left)} ↔ {location(row.right)} · {labels[row.status]}</option>)}</select></label> : null}<label>校准依据<textarea required maxLength={4000} rows={5} value={basis} onChange={event => setBasis(event.target.value)} placeholder="说明版本、页码和判断依据；不要包含私人笔记或个人资料。" /></label><button className="button" type="submit" disabled={!basis.trim() || scope === "passages" && !selectedAlignment}>确认提交审核</button></fieldset>{submitState.error ? <p role="alert">{submitState.error}</p> : null}{submitState.unknown ? <button type="button" disabled={submitState.pending} onClick={() => void submitPublic(true)}>核对原提交结果</button> : null}</form></Dialog>
    <Dialog className="parallel-dialog" open={gate} onRequestClose={() => setGate(false)} aria-labelledby="parallel-login-heading"><header><h2 id="parallel-login-heading">登录后保存私人对齐</h2><button type="button" aria-label="关闭登录提示" onClick={() => setGate(false)}><X size={18} /></button></header><p>阅读与版本比较对访客开放。对齐和术语笔记保存在本人账户，仅自己可见。</p><Link className="button" href={`/login?next=${encodeURIComponent(`/reader/${assetId}?mode=parallel${taskId ? `&alignment=${taskId}` : ""}`)}`}>登录并返回</Link></Dialog>
  </div>;
}
