"use client";

import { createRequestKey } from "../lib/request-key";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { UploadBatchView, type UploadDisplayRow } from "@/components/admin/workflow/upload-batch-view";
import { ArrowRight, FileText, LoaderCircle, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiRequest as rawRequest, apiUpload as rawUpload, getServerSessionCredential, subscribeToSessionChanges, type UploadProgress } from "@/lib/api";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { UploadProcessingControls } from "@/components/admin/workflow/upload-processing-controls";
import { useUploadReservation, type BatchSummary } from "@/components/admin/workflow/use-upload-reservation";
import { useActionGuard } from "@/lib/use-action-guard";
import type { CatalogPublication } from "@/lib/api/admin-collections";
import { UploadPublicationResult } from "@/components/admin/workflow/upload-publication-result";
import { RecycleControl } from "@/components/admin/recycle-control";
import { ProcessingError } from "@/components/admin/processing-error";
import {
  formatUploadBytes,
  UploadRateMeter,
} from "@/lib/upload-metrics";
import {
  loadR2StagingSessions,
  r2MultipartUploadManager,
  retryR2Import,
  type R2StagingSession,
  type R2UploadSnapshot,
} from "@/lib/r2-multipart-upload";
import {
  INGESTION_TERMINAL_STATUSES, activeUploadStage, uploadNeedsRefresh, uploadSnapshotTime, type UploadStageState,
  r2BrowserUploadComplete,
  r2StagingOwnsPrimaryStatus,
  r2StagingStatusLabel,
  r2StagingWaitingAction,
} from "@/lib/ingestion-staging-status";

type UploadResponse = {
  accepted: string[];
  rejected: { filename: string; reason: string }[];
  batch: { id: string; status: string };
};
type RecentBatch = {id:string;label:string;status:string;expected_count:number;completed_count:number;failed_count:number;created_at:string;items:IngestionItem[];access_policy:AccessPolicy;ocr_strategy:OcrStrategy;duplicate_policy:DuplicatePolicy;external_enrichment_enabled:boolean;ai_suggestions_enabled:boolean};

type QueuedFile = {
  file: File;
  token: string;
  status: "waiting" | "uploading" | "accepted" | "failed" | "paused";
  itemId?: string;
  fingerprint?: string;
  message: string;
  progress: number;
  uploadedBytes: number;
  speedBps: number;
  averageSpeedBps: number;
  etaSeconds: number | null;
  sessionId?: string;
  resumeBatchId?: string;
  chunkSize: number;
};

type MetadataImportState = {
  filename: string;
  status: "importing" | "imported" | "failed";
  message: string;
};

type MetadataImportResponse = {
  format: string;
  filename: string;
  reused_source: boolean;
  stats: {
    created?: number;
    updated?: number;
    superseded?: number;
  };
};

type MetadataPairing = {
  status: "matched" | "missing" | "ambiguous";
  file?: File;
  message: string;
};

type ItemUploadResponse = {
  accepted: boolean;
  item: {
    id: string;
    status: string;
    error_message: string;
  };
};

type ChunkUploadResponse = {
  accepted: boolean;
  complete: boolean;
  received_chunks?: number;
  total_chunks?: number;
  received_indices?: number[];
  source_filename?: string;
  total_size?: number;
  chunk_size?: number;
  max_chunk_size?: number;
  item?: ItemUploadResponse["item"];
};

type IngestionCandidate = {
  field_name: string;
  source: string;
  confidence: number;
};

type IngestionItem = UploadStageState & {
  id: string;
  source_filename: string;
  byte_size?: number;
  status: string;
  stage_progress: number;
  error_code: string;
  error_message: string;
  dispatch_status: string;
  dispatch_task_id: string;
  dispatch_attempts: number;
  recognized_metadata: Record<string, unknown>;
  preflight_summary: {
    page_count?: number;
    text_profile?: "born_digital" | "scanned" | "mixed";
    detected_ocr_pages?: number;
    scheduled_ocr_pages?: number;
    ocr_strategy?: OcrStrategy;
    ocr_decision?: "required" | "not_required" | "forced" | "skipped";
    ocr_reason_counts?: Record<string, number>;
    ocr_detection_version?: string;
    exact_duplicate?: boolean;
  };
  edition: string | null;
  metadata_candidates: IngestionCandidate[];
  review_data: null | {
    title: string;
    document_type: string;
    language: string;
    authors: string[];
    publication_year: number | null;
    publisher: string;
    publication_place: string;
    publication_state: string;
    publication?: CatalogPublication;
    review_progress: number;
    ocr_status: string;
    semantic_index_status: string;
  };
  can_manage_publication: boolean;
  is_stalled: boolean;
  suggested_action: string;
  staging: R2StagingSession | null;
  updated_at: string;
};

type AccessPolicy = "public" | "registered" | "restricted";
type OcrStrategy = "auto" | "force" | "skip";
type DuplicatePolicy = "review" | "block_exact" | "allow";

const RESUME_STORAGE_KEY = "stl-upload-resume-v2";
const METADATA_FILE_EXTENSIONS = new Set(["ris", "bib", "bibtex", "json", "yaml", "yml"]);

const ingestionStatusLabels: Record<string, string> = {
  received: "已接收，等待识别",
  validating: "正在校验 PDF",
  deduplicating: "正在核对重复馆藏",
  metadata: "正在识别书目信息",
  extracting: "正在提取逐页文本",
  ocr: "正在判断或执行 OCR",
  linking: "正在生成分类候选",
  indexing: "正在建立检索数据",
  preparing_public_asset: "正在准备阅读文件",
  syncing_cloud: "正在同步公开副本",
  needs_review: "候选已就绪，等待复核",
  ready: "复核已保存，可进入发布台",
  failed: "处理失败，需要检查",
  published: "发布决定已保存",
  withdrawn: "已经下架",
};

const candidateFieldLabels: Record<string, string> = {
  title: "题名",
  authors: "作者",
  publisher: "出版者",
  publication_place: "出版地",
  disciplines: "学科",
  subdisciplines: "子学科",
  theory_schools: "理论流派",
  topics: "主题",
};

const textProfileLabels: Record<string, string> = {
  born_digital: "原生 PDF",
  scanned: "扫描 PDF",
  mixed: "混合 PDF",
};

const ocrReasonLabels: Record<string, string> = {
  scanned_page: "扫描图像",
  missing_tounicode: "文字编码无法映射",
  insufficient_text: "文字层不足",
};

function ocrPreflightLabel(summary: IngestionItem["preflight_summary"]) {
  if (summary.ocr_decision === "required") return `需要 OCR · 自动安排 ${summary.scheduled_ocr_pages ?? 0} 页`;
  if (summary.ocr_decision === "forced") return `已强制 OCR · 安排 ${summary.scheduled_ocr_pages ?? 0} 页`;
  if (summary.ocr_decision === "skipped") return `检测到 ${summary.detected_ocr_pages ?? 0} 页需要 OCR，但本批策略已跳过`;
  if (summary.ocr_decision === "not_required") return "无需 OCR · 已有可用文字层";
  if (summary.scheduled_ocr_pages !== undefined) return `${summary.scheduled_ocr_pages} 页进入 OCR 安排`;
  return "等待服务端预检";
}

function ocrPreflightDetail(summary: IngestionItem["preflight_summary"]) {
  const reasons = Object.entries(summary.ocr_reason_counts || {})
    .filter(([, count]) => count > 0)
    .map(([reason, count]) => `${ocrReasonLabels[reason] || reason} ${count} 页`);
  if (reasons.length) return `判定依据：${reasons.join("、")}。结果来自服务端逐页 PDF 预检。`;
  if (summary.text_profile === "born_digital") return "文字层可直接用于全文提取，后续仍需等待索引任务。";
  return "结果来自服务端逐页 PDF 预检，上传卡片会随处理进度更新。";
}

function displayMetadataValue(value: unknown) {
  if (Array.isArray(value)) return value.map(String).join("、");
  if (value === null || value === undefined || value === "") return "待识别";
  return String(value);
}

function fileFingerprint(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

type ResumeSession = {requestId?:string;batchId:string;token:string;updatedAt:number;chunkSize:number};
// Persist only an owner-scoped content digest and opaque resume identifiers.
// The previous unscoped store is deliberately not imported into any account.
function loadResumeSessions(owner:string):Record<string,ResumeSession> {
  try {const parsed=JSON.parse(localStorage.getItem(`${RESUME_STORAGE_KEY}:${owner}`)||"{}");
    return Object.fromEntries(Object.entries(parsed).filter((entry):entry is [string,ResumeSession]=>{
      const value=entry[1] as ResumeSession;return /^[a-f0-9]{64}$/.test(entry[0])&&value&&typeof value.batchId==="string"&&typeof value.token==="string"&&Number.isFinite(value.chunkSize)&&value.chunkSize>0&&value.updatedAt>Date.now()-30*86400000;
    }));
  } catch{return {};}
}
function persistResume(owner:string,fingerprint:string|undefined,session:Omit<ResumeSession,"updatedAt">|null) {
  if(!fingerprint)return;
  try{const sessions=loadResumeSessions(owner);if(session)sessions[fingerprint]={...session,updatedAt:Date.now()};else delete sessions[fingerprint];localStorage.setItem(`${RESUME_STORAGE_KEY}:${owner}`,JSON.stringify(sessions));}catch{/* Upload remains resumable in this page if browser storage is unavailable. */}
}
function reconcileReservation(owner:string,requestId:string,batchId:string|null){
  const sessions=loadResumeSessions(owner);
  for(const [fingerprint,session] of Object.entries(sessions))if(session.requestId===requestId){if(batchId)persistResume(owner,fingerprint,{batchId,token:session.token,chunkSize:session.chunkSize});else persistResume(owner,fingerprint,null);}
}
async function contentFingerprint(owner:string,file:File) {
  if(!globalThis.crypto?.subtle)return undefined;
  const bytes=await file.arrayBuffer(),digest=await crypto.subtle.digest("SHA-256",bytes);
  const scoped=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(`${owner}:${file.name}:${Array.from(new Uint8Array(digest),value=>value.toString(16).padStart(2,"0")).join("")}`));
  return Array.from(new Uint8Array(scoped),value=>value.toString(16).padStart(2,"0")).join("");
}

function uploadToken() {
  return createRequestKey();
}

function chunkByteLength(totalBytes: number, chunkSize: number, chunkIndex: number) {
  const start = chunkIndex * chunkSize;
  return Math.max(0, Math.min(chunkSize, totalBytes - start));
}


function normalizedFileStem(filename: string, kind: "pdf" | "metadata") {
  let value = filename.normalize("NFKC").trim().toLocaleLowerCase();
  value = value.replace(kind === "pdf" ? /\.pdf$/i : /\.(ris|bib|bibtex|json|ya?ml)$/i, "");
  if (kind === "metadata") {
    value = value.replace(/\.(metadata|sidecar|csl|zotero)$/i, "");
  }
  return value.trim();
}

function isMetadataFile(file: File) {
  const extension = file.name.split(".").pop()?.toLocaleLowerCase() || "";
  return METADATA_FILE_EXTENSIONS.has(extension);
}

function metadataIdentity(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function buildMetadataPairings(pdfFiles: QueuedFile[], metadataFiles: File[]) {
  const pdfCounts = new Map<string, number>();
  const metadataByStem = new Map<string, File[]>();
  for (const item of pdfFiles) {
    const stem = normalizedFileStem(item.file.name, "pdf");
    pdfCounts.set(stem, (pdfCounts.get(stem) || 0) + 1);
  }
  for (const file of metadataFiles) {
    const stem = normalizedFileStem(file.name, "metadata");
    metadataByStem.set(stem, [...(metadataByStem.get(stem) || []), file]);
  }
  return Object.fromEntries(pdfFiles.map((item) => {
    const stem = normalizedFileStem(item.file.name, "pdf");
    const candidates = metadataByStem.get(stem) || [];
    let pairing: MetadataPairing;
    if (!candidates.length) {
      pairing = { status: "missing", message: "未提供配套元数据，将使用 PDF 中的本地识别结果" };
    } else if (candidates.length > 1 || (pdfCounts.get(stem) || 0) > 1) {
      pairing = {
        status: "ambiguous",
        message: "同名 PDF 或元数据文件不唯一，请改为一一对应的文件名",
      };
    } else {
      pairing = {
        status: "matched",
        file: candidates[0],
        message: `将导入 ${candidates[0].name}`,
      };
    }
    return [item.token, pairing];
  })) as Record<string, MetadataPairing>;
}

type UploadWorkspace = {owner_id:string;transport:"local"|"r2";max_files:number;max_file_bytes:number;chunk_bytes:number;recent:BatchSummary[];batch:RecentBatch|null;version:string};
export function AdminUpload() {
  const user=useAdminSession(),batchId=useSearchParams().get("batch")||"",[epoch,setEpoch]=useState(0);
  useEffect(()=>subscribeToSessionChanges(()=>setEpoch(value=>value+1)),[]);
  return user?<AdminUploadBody key={`${user.id}:${epoch}:${batchId}`} owner={String(user.id)} batchId={batchId}/>:<p>正在核对上传账户…</p>;
}
function AdminUploadBody({owner,batchId}:{owner:string;batchId:string}) {
  const user=useAdminSession();
  const transfer = useRef<AbortController|null>(null), paused=useRef(new Set<string>()), selecting=useRef(false), reservedTokens=useRef<string[]>([]);
  const [activeBatchId,setActiveBatchId]=useState(batchId),[preparing,setPreparing]=useState(false),[invalidFiles,setInvalidFiles]=useState<{id:string;filename:string;size:number;message:string}[]>([]);
  const reservation=useUploadReservation(owner);
  const loadWorkspace=useCallback((url:string,signal:AbortSignal)=>rawRequest<UploadWorkspace>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const workspace=usePersistentWorkspace<UploadWorkspace>(`/ingestion/upload-workspace/${activeBatchId?`?batch=${encodeURIComponent(activeBatchId)}`:""}`,owner,data=>data.batch?.items.some(uploadNeedsRefresh)?3000:null,loadWorkspace);
  const apiRequest=useCallback(async <T,>(path:string,options:RequestInit={},_credential?:string|null) => {
    void _credential;
    const signal=AbortSignal.any([...(transfer.current?[transfer.current.signal]:[]),...(options.signal?[options.signal]:[]),AbortSignal.timeout(60000)]);
    return withPrivateOwner(owner,()=>rawRequest<T>(path,{...options,signal,cache:"no-store",headers:{...options.headers,"X-Editor-Owner":owner}},getServerSessionCredential(),false),signal);
  },[owner]);
  async function apiUpload<T>(path:string,body:FormData,_credential?:string|null,onProgress?:(progress:UploadProgress)=>void) {
    void _credential;
    const signal=AbortSignal.any([...(transfer.current?[transfer.current.signal]:[]),AbortSignal.timeout(15*60*1000)]);
    return withPrivateOwner(owner,()=>rawUpload<T>(path,body,getServerSessionCredential(),onProgress,false,{signal,timeoutMs:15*60*1000}),signal);
  }
  async function waitForResume(item:QueuedFile) {
    transfer.current?.signal.throwIfAborted();
    while(paused.current.has(item.token)){updateFile(item.token,{status:"paused",message:"上传已暂停，已确认分段保留"});await new Promise<void>(resolve=>setTimeout(resolve,200));transfer.current?.signal.throwIfAborted();}
  }
  function pauseFile(item:QueuedFile,pause=true){if(pause)paused.current.add(item.token);else paused.current.delete(item.token);if(workspace.data?.transport==="r2")r2MultipartUploadManager.pause(uploadSnapshots.find(row=>row.taskId===item.token||Boolean(item.sessionId)&&row.sessionId===item.sessionId)?.taskId||item.token,pause);updateFile(item.token,{status:pause?"paused":"uploading",message:pause?"完成当前分段后暂停":"继续上传"});}

  const { startAction, finishAction } = useActionGuard();
  const [files, setFiles] = useState<QueuedFile[]>([]);
  const [previewToken, setPreviewToken] = useState("");
  const [previewUrl, setPreviewUrl] = useState("");
  const previewFile = previewToken?files.find(item => item.token === previewToken):files[0];
  const detailItemId=files.find(item=>item.token===previewToken)?.itemId||files.find(item=>item.token===previewToken)?.sessionId||previewToken;
  const previewPdf = previewFile?.file;
  useEffect(() => {
    const url = previewPdf ? URL.createObjectURL(previewPdf) : "";
    const timer = window.setTimeout(() => setPreviewUrl(url), 0);
    return () => { window.clearTimeout(timer); if (url) URL.revokeObjectURL(url); };
  }, [previewPdf]);
  const [metadataFiles, setMetadataFiles] = useState<File[]>([]);
  const [metadataImportStates, setMetadataImportStates] = useState<Record<string, MetadataImportState>>({});
  const [labelDraft,setBatchLabel]=useState<string|null>(null);
  const batchLabel=labelDraft??workspace.data?.batch?.label??"";
  const [accessDraft, setAccessPolicy] = useState<AccessPolicy>("public");
  const [ocrDraft, setOcrStrategy] = useState<OcrStrategy>("auto");
  const [duplicateDraft, setDuplicatePolicy] = useState<DuplicatePolicy>("review");
  const accessPolicy=workspace.data?.batch?.access_policy??accessDraft,ocrStrategy=workspace.data?.batch?.ocr_strategy??ocrDraft,duplicatePolicy=workspace.data?.batch?.duplicate_policy??duplicateDraft;
  const externalEnrichmentEnabled = workspace.data?.batch?.external_enrichment_enabled??false;
  const aiSuggestionsEnabled = workspace.data?.batch?.ai_suggestions_enabled??false;
  const [pending, setPending] = useState(false);
  const [retryingRows,setRetryingRows]=useState(false);
  const retryLoop=useRef(false),retryAlive=useRef(true);
  useEffect(()=>{retryAlive.current=true;return()=>{retryAlive.current=false;};},[]);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const recentBatches = {retry:workspace.reload};
  const [error, setError] = useState("");
  const [ingestionLive, setIngestionItems] = useState<IngestionItem[]>([]);
  const ingestionItems = [...ingestionLive.map(item=>{
    const latest=workspace.data?.batch?.items.find(row=>row.id===item.id);
    // Task progress can advance without changing the upload item timestamp.
    return latest&&uploadSnapshotTime(latest)>=uploadSnapshotTime(item)?{...item,...latest}:item;
  }),...(workspace.data?.batch?.items||[]).filter(item=>!ingestionLive.some(row=>row.id===item.id))];
  const [ingestionError, setIngestionError] = useState("");
  const [retryingItem, setRetryingItem] = useState("");
  const [stagingSessions, setStagingSessions] = useState<R2StagingSession[]>([]);
  const [uploadSnapshots, setUploadSnapshots] = useState<R2UploadSnapshot[]>([]);
  const [stagingError, setStagingError] = useState("");
  const [stagingAction, setStagingAction] = useState("");
  const metadataPairings = useMemo(
    () => buildMetadataPairings(files, metadataFiles),
    [files, metadataFiles],
  );
  const pairedMetadataIdentities = useMemo(
    () => new Set(
      Object.values(metadataPairings)
        .filter((pairing) => pairing.status === "matched" && pairing.file)
        .map((pairing) => metadataIdentity(pairing.file as File)),
    ),
    [metadataPairings],
  );

  const configuredTransport=workspace.data?.transport;
  const refreshStagingSessions = useCallback(async () => {
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      if(configuredTransport!=="r2")return;
      const sessions = await loadR2StagingSessions(owner);
      setStagingSessions(sessions);
      r2MultipartUploadManager.hydrateSessions(sessions);
      setStagingError("");
    } catch (reason) {
      setStagingError(reason instanceof Error ? reason.message : "暂时无法读取上传会话。");
    }
  }, [owner,configuredTransport]);

  useEffect(() => {r2MultipartUploadManager.bindOwner(owner);return r2MultipartUploadManager.subscribe((snapshots) => {
    setUploadSnapshots(snapshots);
    setFiles((current) => current.map((item) => {
      const snapshot = snapshots.find(value=>value.taskId===item.token||Boolean(item.sessionId)&&value.sessionId===item.sessionId);
      if (!snapshot) return item;
      return {
        ...item,
        sessionId: snapshot.sessionId || item.sessionId,
        status: snapshot.status === "uploaded"
          ? "accepted"
          : snapshot.status === "failed" || snapshot.status === "aborted"
            ? "failed"
            : snapshot.status === "paused" ? "paused" : "uploading",
        message: snapshot.message,
        progress: snapshot.progress,
        uploadedBytes: snapshot.uploadedBytes,
        speedBps: snapshot.currentSpeedBps,
        averageSpeedBps: snapshot.averageSpeedBps,
        etaSeconds: snapshot.etaSeconds,
      };
    }));
  });}, [owner]);

  useEffect(() => {
    const initial = setTimeout(() => void refreshStagingSessions(), 0);
    const timer = setInterval(() => { if (!document.hidden) void refreshStagingSessions(); }, 10_000);
    return () => {
      clearTimeout(initial);
      clearInterval(timer);
    };
  }, [refreshStagingSessions]);

  useEffect(() => {
    const accepted = result?.accepted ?? [];
    if (!accepted.length) return;
    const token = getServerSessionCredential();
    if (!token) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function refresh() {
      if (document.hidden) { timer = setTimeout(refresh, 10_000); return; }
      try {
        const snapshots = await Promise.all(
          accepted.map((itemId) => apiRequest<IngestionItem>(
            `/ingestion/items/${itemId}/`,
            {},
            token,
          )),
        );
        if (!active) return;
        setIngestionItems(snapshots);
        setIngestionError("");
        if (snapshots.some(uploadNeedsRefresh)) {
          timer = setTimeout(refresh, 2500);
        }
      } catch (reason) {
        if (!active) return;
        setIngestionError(reason instanceof Error ? reason.message : "暂时无法刷新识别状态。");
        timer = setTimeout(refresh, 5000);
      }
    }

    void refresh();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [result,apiRequest]);

  async function addFiles(list: FileList | null) {
    if(!list||reservation.recovery||selecting.current||pending)return;
    if(!workspace.data){setError("请先读取当前上传能力后再选择文件。");return;}
    const incoming=Array.from(list),metadata=incoming.filter(isMetadataFile);
    setMetadataFiles(current=>{const known=new Set(current.map(metadataIdentity));return current.concat(metadata.filter(file=>!known.has(metadataIdentity(file)))).slice(0,100);});
    const rejected=incoming.filter(file=>!isMetadataFile(file)&&(!file.name.toLowerCase().endsWith(".pdf")||file.size<5||file.size>workspace.data!.max_file_bytes));
    setInvalidFiles(current=>current.concat(rejected.map(file=>({id:uploadToken(),filename:file.name,size:file.size,message:!file.name.toLowerCase().endsWith(".pdf")?"格式不支持，请选择 PDF 文件。":file.size<5?"文件为空或不完整，请重新导出 PDF。":"文件超过本页单个文件大小上限，请重新选择。"}))));
    const known=new Set(files.map(item=>fileFingerprint(item.file))),valid=incoming.filter(file=>!isMetadataFile(file)&&!rejected.includes(file)&&!known.has(fileFingerprint(file)));
    if(files.length+valid.length>workspace.data.max_files){setError("当前列表最多50个PDF，请减少本次选择。已选文件保留。");return;}
    selecting.current=true;setPreparing(true);setError("");
    const controller=new AbortController(),unsubscribe=subscribeToSessionChanges(()=>controller.abort());
    try{
      const additions:QueuedFile[]=[],sessions=loadResumeSessions(owner);
      for(const file of valid){
        controller.signal.throwIfAborted();
        const fingerprint=await contentFingerprint(owner,file);controller.signal.throwIfAborted();
        const local=fingerprint?sessions[fingerprint]:undefined;
        // R2 sessions are matched by the content-derived token, never by filename alone.
        const token=local?.token||`${uploadToken().slice(0,16)}-${fingerprint?.slice(0,32)||uploadToken()}`;
        const resume=stagingSessions.find(session=>session.staging_status==="uploading"&&session.source_filename===file.name&&session.file_size===file.size&&session.client_token===token);
        additions.push({file,token,status:"waiting",fingerprint,message:local||resume?"已匹配当前账户恢复记录，开始时核对服务端分段。":"",progress:0,uploadedBytes:0,speedBps:0,averageSpeedBps:0,etaSeconds:null,sessionId:resume?.upload_session_id,resumeBatchId:local?.batchId,chunkSize:local?.chunkSize||workspace.data.chunk_bytes});
      }
      controller.signal.throwIfAborted();setFiles(current=>{const seen=new Set(current.map(item=>fileFingerprint(item.file)));return current.concat(additions.filter(item=>!seen.has(fileFingerprint(item.file))));});
    }catch(reason){if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"无法准备文件，请重新选择。");}finally{unsubscribe();selecting.current=false;setPreparing(false);}
  }
  function saveResumeSession(item:QueuedFile,session:Omit<ResumeSession,"updatedAt">|null){persistResume(owner,item.fingerprint,session);}
  async function renameBatch(){if(!workspace.data?.batch)return;const result=await reservation.send({action:"rename",batch_id:workspace.data.batch.id,expected_version:workspace.data.version,label:batchLabel});if(result){setBatchLabel(result.label);workspace.reload();}}
  async function recoverReservation(cancel=false){const receipt=await reservation.lookup(cancel);if(receipt)reconcileReservation(owner,receipt.request_id,receipt.state==="applied"?receipt.batch?.id||null:null);if(receipt?.batch){const batch=receipt.batch;setFiles(rows=>rows.map(row=>{if(!reservedTokens.current.includes(row.token))return row;saveResumeSession(row,{batchId:batch.id,token:row.token,chunkSize:row.chunkSize});return {...row,resumeBatchId:batch.id};}));setActiveBatchId(batch.id);workspace.reload();}if(receipt)reservedTokens.current=[];}

  function updateFile(token: string, patch: Partial<QueuedFile>) {
    setFiles((current) => current.map(
      (item) => item.token === token ? { ...item, ...patch } : item,
    ));
  }

  async function retryIngestionItem(itemId: string) {
    const token = getServerSessionCredential();
    const actionKey = `retry-ingestion:${itemId}`;
    if (!token || !startAction(actionKey)) return false;
    setRetryingItem(itemId);
    setIngestionError("");
    try {
      await apiRequest(
        `/ingestion/items/${itemId}/retry/`,
        { method: "POST" },
        token,
      );
      const snapshot = await apiRequest<IngestionItem>(
        `/ingestion/items/${itemId}/`,
        {},
        token,
      );
      setIngestionItems((current) => current.map((item) => item.id === itemId ? snapshot : item));
      return true;
    } catch (reason) {
      setIngestionError(reason instanceof Error ? reason.message : "重新处理失败。");
      return false;
    } finally {
      setRetryingItem("");
      finishAction(actionKey);
    }
  }

  async function abortStagingSession(sessionId: string) {
    const actionKey = `abort-staging:${sessionId}`;
    if (!startAction(actionKey)) return;
    setStagingAction(sessionId);
    setStagingError("");
    try {
      await r2MultipartUploadManager.abort(sessionId,owner);
      for(const item of files.filter(row=>row.sessionId===sessionId)){saveResumeSession(item,null);updateFile(item.token,{token:uploadToken(),sessionId:undefined,resumeBatchId:undefined,status:"waiting",message:"原上传已取消。再次上传将申请新的文件位。",progress:0,uploadedBytes:0});}
      await refreshStagingSessions();
    } catch (reason) {
      setStagingError(reason instanceof Error ? reason.message : "取消上传失败。");
    } finally {
      setStagingAction("");
      finishAction(actionKey);
    }
  }

  async function retryStagingImport(sessionId: string) {
    const actionKey = `retry-staging:${sessionId}`;
    if (!startAction(actionKey)) return;
    setStagingAction(sessionId);
    setStagingError("");
    try {
      await withPrivateOwner(owner,()=>retryR2Import(sessionId));
      await refreshStagingSessions();
    } catch (reason) {
      setStagingError(reason instanceof Error ? reason.message : "重新入库失败。");
    } finally {
      setStagingAction("");
      finishAction(actionKey);
    }
  }

  async function upload(onlyToken?: string) {
    const token = getServerSessionCredential();
    if (!token) {
      setError("请先用管理员账户登录。");
      return false;
    }
    const waiting = files.filter((item) => onlyToken ? item.token === onlyToken && item.status === "failed" : item.status === "waiting");
    if (preparing||!workspace.data||reservation.recovery||!reservation.ready||!waiting.length || !startAction("upload")) return false;
    const controller=new AbortController();transfer.current=controller;const unsubscribe=subscribeToSessionChanges(()=>controller.abort());
    setPending(true);
    setError("");
    setIngestionError("");
    try {
      const shouldUseChunkUpload = (item: QueuedFile) => item.file.size >= 5;
      const freshItems = waiting.filter((item) => !item.sessionId&&!item.resumeBatchId);
      reservedTokens.current=freshItems.map(item=>item.token);
      const freshBatch = freshItems.length ? await reservation.send({action:"reserve",...(workspace.data.batch?{batch_id:workspace.data.batch.id,expected_version:workspace.data.version}:{}),policy:{expected_count:freshItems.length,label:batchLabel.trim(),access_policy:accessPolicy,ocr_strategy:ocrStrategy,duplicate_policy:duplicatePolicy,external_enrichment_enabled:externalEnrichmentEnabled,ai_suggestions_enabled:aiSuggestionsEnabled}},(requestId,batchId)=>{for(const item of freshItems)saveResumeSession(item,{requestId:batchId?undefined:requestId,batchId:batchId||"",token:item.token,chunkSize:item.chunkSize});}) : null;
      if(freshItems.length&&!freshBatch)throw Error("批次尚未确认，请先查回原请求。");
      if(freshBatch){for(const item of freshItems){saveResumeSession(item,{batchId:freshBatch.id,token:item.token,chunkSize:item.chunkSize});updateFile(item.token,{resumeBatchId:freshBatch.id});}setActiveBatchId(freshBatch.id);reservedTokens.current=[];}
      const resumedSession = stagingSessions.find(
        (session) => session.upload_session_id === waiting[0].sessionId,
      );
      const displayBatch = freshBatch || {
        id: resumedSession?.batch_id || waiting[0].resumeBatchId || "",
        status: "resuming",
      };
      const accepted: string[] = [...(result?.accepted ?? [])];
      const rejected: { filename: string; reason: string }[] = [];
      let cursor = 0;
      const uploadMetadataPairings = buildMetadataPairings(files, metadataFiles);

      async function importMatchedMetadata(itemId: string, item: QueuedFile) {
        const pairing = uploadMetadataPairings[item.token];
        if (!pairing || pairing.status !== "matched" || !pairing.file) {
          return pairing?.status === "ambiguous"
            ? "上传完成；配套元数据文件名有冲突，尚未导入"
            : "上传完成，已进入处理队列";
        }
        setMetadataImportStates((current) => ({
          ...current,
          [item.token]: {
            filename: pairing.file?.name || "",
            status: "importing",
            message: "正在导入配套元数据",
          },
        }));
        const body = new FormData();
        body.append("file", pairing.file);
        try {
          const response = await apiUpload<MetadataImportResponse>(
            `/ingestion/items/${itemId}/metadata-import/`,
            body,
            token,
          );
          const created = response.stats.created || 0;
          const message = response.reused_source
            ? `配套元数据已核对，复用 ${response.format} 来源记录`
            : `配套元数据已生成 ${created} 个待审候选`;
          setMetadataImportStates((current) => ({
            ...current,
            [item.token]: {
              filename: pairing.file?.name || "",
              status: "imported",
              message,
            },
          }));
          return `上传完成；${message}`;
        } catch (reason) {
          const message = reason instanceof Error ? reason.message : "配套元数据导入失败";
          setMetadataImportStates((current) => ({
            ...current,
            [item.token]: {
              filename: pairing.file?.name || "",
              status: "failed",
              message,
            },
          }));
          return `PDF 已上传；配套元数据未导入：${message}`;
        }
      }

      // Use the configured service; both transports share the existing intake pipeline.
      if (workspace.data.transport === "r2" || waiting.some(item=>item.sessionId)) {
        async function sendR2File(item: QueuedFile) {
          updateFile(item.token, {
            status: "uploading",
            message: item.sessionId ? "正在恢复 R2 multipart upload" : "正在建立 R2 multipart upload",
            progress: 0,
            uploadedBytes: 0,
            speedBps: 0,
            averageSpeedBps: 0,
            etaSeconds: null,
          });
          try {
            await waitForResume(item);
            const existing = item.sessionId
              ? stagingSessions.find((session) => session.upload_session_id === item.sessionId)
              : undefined;
            if (!existing && !freshBatch && !item.resumeBatchId) {
              throw new Error("没有可用的上传批次，请重新选择 PDF。")
            }
            const session = existing
              ? await r2MultipartUploadManager.resume(item.file, existing, owner)
              : await r2MultipartUploadManager.start(item.file, item.resumeBatchId||freshBatch!.id, item.token, owner);
            if(!accepted.includes(session.upload_session_id))accepted.push(session.upload_session_id);
            setResult({accepted:[...accepted],rejected:[...rejected],batch:displayBatch});
            const metadataMessage = await importMatchedMetadata(session.upload_session_id, item);
            updateFile(item.token, {
              sessionId: session.upload_session_id,
              itemId: session.upload_session_id,
              status: "accepted",
              message: metadataMessage.includes("元数据")
                ? `浏览器上传完成，正在导入书库存储；${metadataMessage.replace(/^上传完成[；，]?/, "")}`
                : "浏览器上传完成，正在导入书库存储",
              progress: 100,
              uploadedBytes: item.file.size,
              speedBps: 0,
              etaSeconds: 0,
            });
          } catch (reason) {
            const message = reason instanceof Error ? reason.message : "上传中断";
            rejected.push({ filename: item.file.name, reason: message });
            updateFile(item.token, { status: "failed", message, speedBps: 0, etaSeconds: null });
          }
        }

        async function r2Worker() {
          while (cursor < waiting.length) {
          controller.signal.throwIfAborted();
            const item = waiting[cursor];
            cursor += 1;
            await sendR2File(item);
          }
        }

        await Promise.all(
          Array.from({ length: Math.min(2, waiting.length) }, () => r2Worker()),
        );
        setResult({ accepted, rejected, batch: displayBatch });
        await refreshStagingSessions();
        return accepted.length > 0 && rejected.length === 0;
      }

      async function sendChunks(item: QueuedFile, targetBatchId: string) {
        let chunkSize = item.chunkSize;
        let totalChunks = Math.ceil(item.file.size / chunkSize);
        let finalResponse: ChunkUploadResponse | null = null;
        const saved: ChunkUploadResponse = await apiRequest<ChunkUploadResponse>(
          `/ingestion/batches/${targetBatchId}/chunks/?client_token=${encodeURIComponent(item.token)}`,
          {},
          token,
        );
        if (saved.complete && saved.item) {
          return {
            accepted: saved.item.status !== "failed",
            item: saved.item,
          } satisfies ItemUploadResponse;
        }
        if (saved.chunk_size && saved.chunk_size !== chunkSize) {
          chunkSize = saved.chunk_size;
          totalChunks = Math.ceil(item.file.size / chunkSize);
          updateFile(item.token, { chunkSize });
        }
        if (saved.max_chunk_size && chunkSize > saved.max_chunk_size) {
          throw new Error("服务器允许的上传分段小于当前恢复记录，请保留页面并联系管理员升级 API。");
        }
        if (
          (saved.source_filename && saved.source_filename !== item.file.name)
          || (saved.total_size && saved.total_size !== item.file.size)
          || (saved.total_chunks && saved.total_chunks !== totalChunks)
        ) {
          throw new Error("服务器上的恢复记录属于另一个 PDF，请移除文件后重新选择。");
        }
        const received = new Set(
          (saved.received_indices || []).filter((index) => index >= 0 && index < totalChunks),
        );
        if (received.size === totalChunks && totalChunks > 0) {
          // Re-send the final idempotent chunk when the browser lost the
          // assembly response after every chunk reached the server.
          received.delete(totalChunks - 1);
        }
        let completedBytes = Array.from(received).reduce(
          (total, index) => total + chunkByteLength(item.file.size, chunkSize, index),
          0,
        );
        const resumedBytes = Math.min(item.file.size, completedBytes);
        const meter = new UploadRateMeter(item.file.size, resumedBytes, performance.now());
        if (received.size) {
          const resumedProgress = Math.min(99, Math.round((resumedBytes / item.file.size) * 100));
          updateFile(item.token, {
            uploadedBytes: resumedBytes,
            progress: resumedProgress,
            message: `已恢复 ${received.size}/${totalChunks} 个分段`,
          });
        }
        for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex += 1) {
          if (received.has(chunkIndex)) continue;
          await waitForResume(item);
          const start = chunkIndex * chunkSize;
          const end = Math.min(item.file.size, start + chunkSize);
          const chunk = item.file.slice(start, end, "application/octet-stream");
          let response: ChunkUploadResponse | null = null;
          let lastError: unknown = null;
          for (let chunkAttempt = 0; chunkAttempt < 3; chunkAttempt += 1) {
            let previousLoaded = 0;
            const body = new FormData();
            body.append("chunk", chunk, `${chunkIndex}.part`);
            body.append("client_token", item.token);
            body.append("source_filename", item.file.name);
            body.append("chunk_index", String(chunkIndex));
            body.append("total_chunks", String(totalChunks));
            body.append("total_size", String(item.file.size));
            body.append("chunk_size", String(chunkSize));
            try {
              response = await apiUpload<ChunkUploadResponse>(
                `/ingestion/batches/${targetBatchId}/chunks/`,
                body,
                token,
                ({ loaded, total }) => {
                  const now = performance.now();
                  const networkBytes = Math.max(0, loaded - previousLoaded);
                  previousLoaded = Math.max(previousLoaded, loaded);
                  const metrics = meter.sample(completedBytes + loaded, networkBytes, now);
                  const progress = Math.min(99, Math.round((metrics.logicalBytes / item.file.size) * 100));
                  const finalBodySent = chunkIndex === totalChunks - 1 && total > 0 && loaded >= total;
                  const retryLabel = chunkAttempt > 0 ? `，第 ${chunkAttempt + 1} 次尝试` : "";
                  updateFile(item.token, {
                    uploadedBytes: metrics.logicalBytes,
                    progress,
                    speedBps: metrics.currentSpeedBps,
                    averageSpeedBps: metrics.averageSpeedBps,
                    etaSeconds: metrics.etaSeconds,
                    message: finalBodySent
                      ? "文件已上传，服务器正在合并和校验"
                      : `正在上传分段 ${chunkIndex + 1}/${totalChunks}${retryLabel}`,
                  });
                },
              );
              break;
            } catch (reason) {
              controller.signal.throwIfAborted();
              lastError = reason;
            }
          }
          if (!response) throw lastError instanceof Error ? lastError : new Error("文件分段上传失败。");
          completedBytes = Math.min(item.file.size, completedBytes + chunk.size);
          const metrics = meter.sample(completedBytes, 0, performance.now());
          updateFile(item.token, {
            uploadedBytes: metrics.logicalBytes,
            progress: Math.min(99, Math.round((metrics.logicalBytes / item.file.size) * 100)),
            speedBps: metrics.currentSpeedBps,
            averageSpeedBps: metrics.averageSpeedBps,
            etaSeconds: metrics.etaSeconds,
            message: response.complete
              ? "服务器已完成合并和校验"
              : `已完成分段 ${chunkIndex + 1}/${totalChunks}`,
          });
          finalResponse = response;
          saveResumeSession(item, {
            batchId: targetBatchId,
            token: item.token,
            chunkSize,
          });
        }
        if (!finalResponse?.complete || !finalResponse.item) {
          throw new Error("文件分段已经发送，但服务器尚未完成合并，请重试。");
        }
        return {
          accepted: finalResponse.accepted,
          item: finalResponse.item,
        } satisfies ItemUploadResponse;
      }

      async function sendFile(item: QueuedFile) {
        updateFile(item.token, {
          status: "uploading",
          message: "正在连接",
          progress: 0,
          uploadedBytes: 0,
          speedBps: 0,
          averageSpeedBps: 0,
          etaSeconds: null,
        });
        let lastReason = "上传中断";
        for (let attempt = 0; attempt < 3; attempt += 1) {
          await waitForResume(item);
          const body = new FormData();
          body.append("file", item.file);
          body.append("client_token", item.token);
          const startedAt = performance.now();
          const meter = new UploadRateMeter(item.file.size, 0, startedAt);
          let previousLoaded = 0;
          try {
            const useChunks = shouldUseChunkUpload(item);
            const targetBatchId = useChunks && item.resumeBatchId
              ? item.resumeBatchId
              : freshBatch?.id;
            if (!targetBatchId) throw new Error("没有可用的上传批次，请重新选择文件。");
            if (useChunks) {
              saveResumeSession(item, {
                batchId: targetBatchId,
                token: item.token,
                    chunkSize: item.chunkSize,
              });
            }
            const response = useChunks
              ? await sendChunks(item, targetBatchId)
              : await apiUpload<ItemUploadResponse>(
                `/ingestion/batches/${targetBatchId}/items/`,
                body,
                token,
                ({ loaded, total }) => {
                  const now = performance.now();
                  const networkBytes = Math.max(0, loaded - previousLoaded);
                  previousLoaded = Math.max(previousLoaded, loaded);
                  const logicalBytes = Math.min(item.file.size, loaded);
                  const metrics = meter.sample(logicalBytes, networkBytes, now);
                  const progress = total ? Math.min(99, Math.round((metrics.logicalBytes / item.file.size) * 100)) : 0;
                  updateFile(item.token, {
                    uploadedBytes: metrics.logicalBytes,
                    progress,
                    speedBps: metrics.currentSpeedBps,
                    averageSpeedBps: metrics.averageSpeedBps,
                    etaSeconds: metrics.etaSeconds,
                    message: total > 0 && loaded >= total
                      ? "文件已上传，服务器正在校验"
                      : attempt > 0
                        ? `正在重试完整上传，第 ${attempt + 1} 次尝试`
                        : "正在上传",
                  });
                },
              );
            if (response.accepted) {
              saveResumeSession(item, null);
              if(!accepted.includes(response.item.id))accepted.push(response.item.id);
              updateFile(item.token,{itemId:response.item.id});
              setResult({accepted:[...accepted],rejected:[...rejected],batch:displayBatch});
              const completionMessage = await importMatchedMetadata(response.item.id, item);
              updateFile(item.token, {
                status: "accepted",
                message: completionMessage,
                progress: 100,
                uploadedBytes: item.file.size,
                etaSeconds: 0,
              });
            } else {
              const reason = response.item.error_message || "文件未通过校验";
              rejected.push({ filename: item.file.name, reason });
              updateFile(item.token, { status: "failed", message: reason });
            }
            return;
          } catch (reason) {
            controller.signal.throwIfAborted();
            lastReason = reason instanceof Error ? reason.message : "上传中断";
          }
        }

        try {
          const failureBatchId = shouldUseChunkUpload(item) && item.resumeBatchId
            ? item.resumeBatchId
            : freshBatch?.id;
          if (!failureBatchId) throw new Error(lastReason);
          const recovered = await apiRequest<{
            item: { id: string; status: string; error_message: string };
          }>(
            `/ingestion/batches/${failureBatchId}/failures/`,
            {
              method: "POST",
              body: JSON.stringify({
                client_token: item.token,
                source_filename: item.file.name,
                reason: lastReason,
              }),
            },
            token,
          );
          if (recovered.item.status !== "failed") {
            accepted.push(recovered.item.id);
            updateFile(item.token, { status: "accepted", message: "服务器已接收" });
            return;
          }
          lastReason = recovered.item.error_message || lastReason;
        } catch {
          // The local row still records the failure even if the final report is unreachable.
        }
        rejected.push({ filename: item.file.name, reason: lastReason });
        updateFile(item.token, { status: "failed", message: lastReason });
      }

      async function worker() {
        while (cursor < waiting.length) {
          controller.signal.throwIfAborted();
          const item = waiting[cursor];
          cursor += 1;
          await sendFile(item);
        }
      }

      await Promise.all(
        Array.from(
          { length: Math.min(2, waiting.length) },
          () => worker(),
        ),
      );
      setResult({ accepted, rejected, batch: displayBatch });
      return accepted.length > 0 && rejected.length === 0;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "上传失败。");
      return false;
    } finally {
      unsubscribe();transfer.current=null;workspace.reload();
      setPending(false);
      finishAction("upload");
    }
  }

  const displayRows:UploadDisplayRow[] = files.map(item=>{
    const source=ingestionItems.find(row=>row.id===(item.itemId||item.sessionId)),kind=String(source?.review_data?.document_type||source?.recognized_metadata.document_type||"");
    const processing=activeUploadStage(source);
    const category:UploadDisplayRow["category"]=processing?.status==="paused"?"paused":processing?"active":source?.preflight_summary?.exact_duplicate?"duplicate":source?.status==="failed"||item.status==="failed"?"failed":item.status==="paused"?"paused":item.status==="uploading"?"active":source&&!INGESTION_TERMINAL_STATUSES.has(source.status)?"active":item.status==="accepted"?"done":"waiting";
    return {id:item.token,filename:item.file.name,size:item.file.size,profile:textProfileLabels[source?.preflight_summary?.text_profile||""],kind:({book:"图书",journal_article:"期刊论文",journal_issue:"整期期刊",thesis:"学位论文",report:"研究报告"} as Record<string,string>)[kind]||kind,progress:item.progress,stageProgress:processing?.progress??source?.stage_progress,canPreview:true,transferState:["waiting","uploading","paused"].includes(item.status)?item.status as "waiting"|"uploading"|"paused":undefined,retryTarget:item.status==="failed"?{kind:"upload",id:item.token}:source?.status==="failed"?{kind:"ingestion",id:source.id}:undefined,category,status:processing?.status==="paused"?"后台处理已暂停":processing?"后台处理中":source?ingestionStatusLabels[source.status]||source.status:item.status==="paused"?"传输已暂停":item.status==="accepted"?"上传完成 · 等待识别":item.status==="uploading"?"上传中":item.status==="failed"?"上传失败":"等待上传",detail:source?.error_message||item.message,primaryAction:["uploading","paused"].includes(item.status)?<button type="button" onClick={()=>pauseFile(item,item.status!=="paused")}>{item.status==="paused"?"继续":"暂停"}</button>:item.status==="failed"?<button disabled={pending||Boolean(reservation.recovery)} onClick={()=>void upload(item.token)}>重试</button>:source?.status==="failed"?<button disabled={Boolean(retryingItem)} onClick={()=>void retryIngestionItem(source.id)}>重试</button>:source?<Link href={`/admin/intake/${source.id}`}>查看</Link>:undefined,select:()=>setPreviewToken(item.token),actions:<>{["uploading","paused"].includes(item.status)?<button type="button" onClick={()=>pauseFile(item,item.status!=="paused")}>{item.status==="paused"?"继续":"暂停"}</button>:null}{item.status==="failed"?<button disabled={pending||Boolean(reservation.recovery)} onClick={()=>void upload(item.token)}>重试</button>:null}{source?<><Link href={`/admin/intake/${source.id}`}>{source.preflight_summary?.exact_duplicate?"核对重复与版本":"前往编目"}</Link>{source.status==="failed"?<button disabled={Boolean(retryingItem)} onClick={()=>void retryIngestionItem(source.id)}>重试处理</button>:null}</>:null}<button disabled={pending} onClick={()=>setFiles(rows=>rows.filter(row=>row.token!==item.token))}>移除列表项</button></>};
  });
  for(const item of ingestionItems)if(!files.some(row=>row.itemId===item.id||row.sessionId===item.id)){const processing=activeUploadStage(item);displayRows.push({id:item.id,filename:item.source_filename,size:item.byte_size||0,profile:textProfileLabels[item.preflight_summary?.text_profile||""],kind:String(item.review_data?.document_type||item.recognized_metadata.document_type||""),progress:100,stageProgress:processing?.progress??item.stage_progress,retryTarget:item.status==="failed"?{kind:"ingestion",id:item.id}:undefined,select:()=>setPreviewToken(item.id),category:processing?.status==="paused"?"paused":processing?"active":item.preflight_summary?.exact_duplicate?"duplicate":item.status==="failed"?"failed":INGESTION_TERMINAL_STATUSES.has(item.status)?"done":"active",status:processing?.status==="paused"?"后台处理已暂停":processing?"后台处理中":ingestionStatusLabels[item.status]||item.status,detail:item.error_message||"文件已接收，识别状态来自后台任务。",primaryAction:item.status==="failed"?<button disabled={Boolean(retryingItem)} onClick={()=>void retryIngestionItem(item.id)}>重试</button>:<Link href={`/admin/intake/${item.id}`}>查看</Link>,actions:<><Link href={`/admin/intake/${item.id}`}>查看并编目</Link>{item.status==="failed"?<button disabled={Boolean(retryingItem)} onClick={()=>void retryIngestionItem(item.id)}>重试处理</button>:null}</>});}
  for(const item of invalidFiles)displayRows.push({id:item.id,filename:item.filename,size:item.size,profile:"未上传",kind:"",progress:0,status:"无法上传",category:"failed",detail:item.message,select:()=>setPreviewToken(item.id),primaryAction:<button onClick={()=>setInvalidFiles(rows=>rows.filter(row=>row.id!==item.id))}>移除</button>,actions:<button onClick={()=>setInvalidFiles(rows=>rows.filter(row=>row.id!==item.id))}>移除列表项</button>});
  async function retryDisplayRows(ids?:string[]){
    if(retryLoop.current||pending||preparing||reservation.recovery)return;
    const plan=displayRows.filter(row=>row.retryTarget&&(!ids||ids.includes(row.id)));
    if(!plan.length)return;
    retryLoop.current=true;setRetryingRows(true);
    try{for(const row of plan){if(!retryAlive.current)break;const target=row.retryTarget!;const completed=target.kind==="upload"?await upload(target.id):await retryIngestionItem(target.id);if(!completed)break;}}
    finally{retryLoop.current=false;if(retryAlive.current)setRetryingRows(false);}
  }
  return <UploadBatchView batchFirst={Boolean(activeBatchId)} processingHref={workspace.data?.batch&&hasAdminCapability(user,"can_view_system_status")?`/admin/processing?batch_id=${workspace.data.batch.id}`:undefined} rows={displayRows} label={batchLabel} onLabel={setBatchLabel} saveLabel={workspace.data?.batch?()=>void renameBatch():undefined} addFiles={list=>void addFiles(list)} locked={preparing||retryingRows||!workspace.data||!reservation.ready||Boolean(reservation.recovery)||reservation.busy} pending={pending} canStart={files.some(row=>row.status==="waiting")} start={()=>void upload()} pauseAll={ids=>files.filter(row=>(!ids||ids.includes(row.token))&&["waiting","uploading"].includes(row.status)).forEach(row=>pauseFile(row))} resumeAll={ids=>files.filter(row=>(!ids||ids.includes(row.token))&&row.status==="paused").forEach(row=>pauseFile(row,false))} retryAll={ids=>void retryDisplayRows(ids)} clear={()=>{setActiveBatchId("");setBatchLabel(null);paused.current.clear();setInvalidFiles([]);setFiles([]);setMetadataFiles([]);setResult(null);setIngestionItems([]);}} maxFiles={workspace.data?.max_files} maxBytes={workspace.data?.max_file_bytes} title={activeBatchId?"批次详情与上传恢复":"批量收件与上传"}
    policy={<div className="upload-policy-panel admin-panel">
        <h3 id="upload-policy-title">本批处理方式与访问权限</h3>
        <header>
          <div>
            <p>这些选项只作用于本次新建批次，之后仍可在审校和发布阶段调整馆藏内容。</p>
          </div>
        </header>
        <div className="upload-policy-grid">
          <label className="upload-policy-field upload-policy-label">
            <span>批次标签</span>
            <input
              type="text"
              value={batchLabel}
              maxLength={240}
              disabled={pending||Boolean(workspace.data?.batch)}
              placeholder="例如 2026 秋季中文社会理论"
              onChange={(event) => setBatchLabel(event.target.value)}
            />
            <small>可选。用于稍后查找和筛选这一批文件。</small>
          </label>
          <label className="upload-policy-field">
            <span>访问权限</span>
            <select
              value={accessPolicy}
              disabled={pending||Boolean(workspace.data?.batch)}
              onChange={(event) => setAccessPolicy(event.target.value as AccessPolicy)}
            >
              <option value="public">公开访问</option>
              <option value="registered">登录读者</option>
              <option value="restricted">受限访问</option>
            </select>
            <small>仅设定文件的初始访问范围，不会跳过管理员发布确认。</small>
          </label>
          <label className="upload-policy-field">
            <span>OCR 策略</span>
            <select
              value={ocrStrategy}
              disabled={pending||Boolean(workspace.data?.batch)}
              onChange={(event) => setOcrStrategy(event.target.value as OcrStrategy)}
            >
              <option value="auto">自动检测（推荐）</option>
              <option value="force">强制 OCR</option>
              <option value="skip">跳过 OCR</option>
            </select>
            <small>自动检测会保留可靠原生文字，仅将扫描页排入 OCR，节省 NAS 资源。</small>
          </label>
          <label className="upload-policy-field">
            <span>重复检测</span>
            <select
              value={duplicatePolicy}
              disabled={pending||Boolean(workspace.data?.batch)}
              onChange={(event) => setDuplicatePolicy(event.target.value as DuplicatePolicy)}
            >
              <option value="review">发现重复时人工确认</option>
              <option value="block_exact">阻止完全重复文件</option>
              <option value="allow">复用已有文件并继续</option>
            </select>
            <small>推荐人工确认，以区分完全重复文件和同一作品的不同版本。</small>
          </label>
          <p className="upload-local-only">上传只解析本地文件与馆内资料。需要外部书目时，在馆藏工作页明确点击“查找免费来源”。</p>
        </div>
        {files.some((item) => item.sessionId) ? (
          <p className="upload-resume-policy-note" role="status">
            已发现服务端 R2 上传会话。重新选择同一 PDF 后只上传未完成 part；原批次策略不会被改写。
          </p>
        ) : null}
      </div>}
    preview={<aside className="upload-v307-preview admin-panel" aria-label="当前上传预览"><header><h2>上传预览</h2></header>{previewFile ? <><div className="upload-v307-file-preview">{previewUrl ? <iframe src={`${previewUrl}#toolbar=0&navpanes=0`} title={`${previewFile.file.name} 本地 PDF 预览`} /> : <FileText size={48} />}</div><strong>{previewFile.file.name}</strong><dl><div><dt>文件类型</dt><dd>PDF</dd></div><div><dt>文件大小</dt><dd>{formatUploadBytes(previewFile.file.size)}</dd></div><div><dt>上传状态</dt><dd>{previewFile.message || "等待上传"}</dd></div></dl><p>文件上传并校验后，进入馆藏工作页完善书目、关联作者和发布。</p></> : <p className="admin-list-state">选择 PDF 后，可以在这里核对本地文件。</p>}</aside>}
    feedback={<>{preparing?<p role="status">正在核对文件内容，准备当前账户的恢复记录…</p>:null}{error?<p className="form-message error" role="alert">{error}</p>:null}{workspace.error?<p role="alert">{workspace.error}<button onClick={workspace.reload}>重新读取上传能力</button></p>:null}{reservation.error?<p role="alert">{reservation.error}</p>:null}{reservation.recovery?<section role="status"><p>批次请求尚未确认，当前选择保留，请查回原结果。</p><button disabled={reservation.busy} onClick={()=>void recoverReservation()}>查回批次</button><button disabled={reservation.busy} onClick={()=>void recoverReservation(true)}>停止未执行请求</button></section>:null}{ingestionError?<p role="alert">{ingestionError}</p>:null}{stagingError?<p role="alert">{stagingError}</p>:null}</>}
    metadata={<><p>可附同名 RIS、BibTeX、JSON、YAML 元数据，导入后仅生成待审候选。</p>{metadataFiles.map(file=><p key={metadataIdentity(file)}>{file.name}{pairedMetadataIdentities.has(metadataIdentity(file))?" · 已匹配":" · 暂未匹配PDF"}</p>)}{Object.entries(metadataImportStates).map(([id,state])=><p key={id}>{state.filename} · {state.message}</p>)}</>}
    details={<><p>实际服务端预检、OCR安排和书目候选如下。上传完成不等于已发布。</p><div>            {ingestionItems.filter(item=>item.id===detailItemId).map((item) => {
              const metadata = item.review_data ?? item.recognized_metadata;
              const title = item.review_data?.title || displayMetadataValue(item.recognized_metadata.title);
              const candidateCounts = item.metadata_candidates.reduce<Record<string, number>>((counts, candidate) => {
                counts[candidate.field_name] = (counts[candidate.field_name] || 0) + 1;
                return counts;
              }, {});
              const stagingStatus = item.staging?.staging_status || "";
              const stagingOwnsStatus = r2StagingOwnsPrimaryStatus(stagingStatus);
              const canRetryImport = stagingStatus === "import_failed" && Boolean(item.staging?.can_retry_import);
              const canRetry = !stagingOwnsStatus && (item.status === "failed" || item.is_stalled);
              const primaryStatus = stagingOwnsStatus
                ? r2StagingStatusLabel(stagingStatus)
                : ingestionStatusLabels[item.status] ?? item.status;
              const visibleErrorCode = stagingOwnsStatus ? item.staging?.error_code : item.error_code;
              const visibleErrorMessage = stagingOwnsStatus ? item.staging?.error_message : item.error_message;
              return (
                <article className={`ingestion-card status-${stagingOwnsStatus ? stagingStatus : item.status}`} key={item.id}>
                  <header>
                    <div><FileText size={18} /><span><strong>{title}</strong><small>{item.source_filename}</small></span></div>
                    <b>{primaryStatus}</b>
                  </header>
                  {stagingOwnsStatus ? (
                    <p className="ingestion-item-note">
                      {r2BrowserUploadComplete(stagingStatus)
                        ? "浏览器到 R2 的上传已完成。正式书库存储导入完成后，系统才会开始 PDF 校验和书目识别。"
                        : r2StagingStatusLabel(stagingStatus)}
                    </p>
                  ) : (
                    <div className="ingestion-card-progress">
                      <span><i style={{ width: `${Math.max(2, item.stage_progress)}%` }} /></span>
                      <b>{item.stage_progress}%</b>
                    </div>
                  )}
                  <dl>
                    <UploadPublicationResult editionId={item.edition} publication={item.review_data?.publication} />
                    <div><dt>文献类型</dt><dd>{displayMetadataValue(item.review_data?.document_type ?? metadata.document_type)}</dd></div>
                    <div><dt>作者</dt><dd>{displayMetadataValue(item.review_data?.authors ?? metadata.authors)}</dd></div>
                    <div><dt>出版信息</dt><dd>{[
                      item.review_data?.publication_place ?? metadata.publication_place,
                      item.review_data?.publisher ?? metadata.publisher,
                      item.review_data?.publication_year ?? metadata.publication_year,
                    ].filter(Boolean).map(String).join(" · ") || "待识别"}</dd></div>
                    <div><dt>后台派发</dt><dd>{stagingOwnsStatus ? "等待 R2 正式导入" : <>{item.dispatch_status}{item.dispatch_attempts > 1 ? ` · ${item.dispatch_attempts} 次记录` : ""}</>}</dd></div>
                    <div><dt>文件预检</dt><dd>{[
                      item.preflight_summary?.page_count ? `${item.preflight_summary.page_count} 页` : "",
                      textProfileLabels[item.preflight_summary?.text_profile || ""] || "",
                      item.preflight_summary?.exact_duplicate ? "发现完全重复文件" : "",
                    ].filter(Boolean).join(" · ") || "等待解析"}</dd></div>
                    <div><dt>OCR 安排</dt><dd>{item.preflight_summary?.scheduled_ocr_pages !== undefined
                      ? `${item.preflight_summary.scheduled_ocr_pages} 页${item.preflight_summary.detected_ocr_pages !== undefined ? `（检测到 ${item.preflight_summary.detected_ocr_pages} 页）` : ""}`
                      : "等待检测"}</dd></div>
                  </dl>
                  <div className="upload-ocr-preflight" role="status">
                    <strong>OCR 预判</strong>
                    <span>{ocrPreflightLabel(item.preflight_summary)}</span>
                    <small>{ocrPreflightDetail(item.preflight_summary)}</small>
                  </div>
                  <div className="ingestion-candidate-summary">
                    {Object.entries(candidateFieldLabels).map(([field, label]) => (
                      <span className={candidateCounts[field] ? "available" : ""} key={field}>{label}<b>{candidateCounts[field] || 0}</b></span>
                    ))}
                  </div>
                  {visibleErrorMessage ? <ProcessingError code={visibleErrorCode || ""} message={visibleErrorMessage} /> : null}
                  {!item.edition && !visibleErrorMessage && !stagingOwnsStatus ? <p className="ingestion-item-note">文件已安全保存。书目记录建立后，可直接进入候选复核；等待期间无需重复点击。</p> : null}
                  <footer>
                    <UploadProcessingControls owner={owner} itemId={item.id}/>
                    <RecycleControl kind="upload" id={item.id} name={item.source_filename} onDeleted={() => { setIngestionItems((current) => current.filter((row) => row.id !== item.id)); setResult((current) => current ? { ...current, accepted: current.accepted.filter((id) => id !== item.id) } : current); recentBatches.retry(); }} />
                    {canRetryImport ? <button className="button secondary" type="button" disabled={stagingAction === item.id} onClick={() => void retryStagingImport(item.id)}>{stagingAction === item.id ? <LoaderCircle className="spin" size={14} /> : <RefreshCw size={14} />}重新导入</button> : null}
                    {canRetry ? <button className="button secondary" type="button" disabled={retryingItem === item.id} onClick={() => void retryIngestionItem(item.id)}>{retryingItem === item.id ? <LoaderCircle className="spin" size={14} /> : <RefreshCw size={14} />}重新处理</button> : null}
                    {item.edition ? <Link className="button secondary" href={`/admin/intake/${item.id}#bibliography`}>继续馆藏工作 <ArrowRight size={14} /></Link> : <span className="ingestion-waiting-action">{r2StagingWaitingAction(stagingStatus)}</span>}
                    {item.edition && item.can_manage_publication ? <Link className="button" href={`/admin/intake/${item.id}#publication`}>进入发布检查 <ArrowRight size={14} /></Link> : null}
                  </footer>
                </article>
              );
            })}
          </div>{!ingestionItems.some(item=>item.id===detailItemId)?<p>当前文件尚未进入识别，上传完成后可在批次或收件详情查看。</p>:null}{stagingSessions.length?<details><summary>持续上传与恢复记录</summary>{stagingSessions.map(session=><p key={session.upload_session_id}>{session.source_filename} · {r2StagingStatusLabel(session.staging_status)}{session.can_abort?<button disabled={Boolean(stagingAction)} onClick={()=>void abortStagingSession(session.upload_session_id)}>取消上传</button>:null}{session.can_retry_import?<button disabled={Boolean(stagingAction)} onClick={()=>void retryStagingImport(session.upload_session_id)}>重新入库</button>:null}</p>)}</details>:null}</>}
    recent={<section className="upload-recent-batches admin-panel"><header><h2>我的最近批次</h2><button onClick={workspace.reload}>刷新批次</button></header>{workspace.data?.recent.length?<ul>{workspace.data.recent.map(batch=><li key={batch.id}><Link href={`/admin/uploads?batch=${batch.id}`}>{batch.label||`批次 ${batch.created_at.slice(0,10)}`}</Link> · {batch.expected_count} 个预留文件位 · {batch.completed_count} 项处理完成 · {batch.failed_count} 项失败</li>)}</ul>:<p>尚无上传批次。</p>}</section>}/>;
}
