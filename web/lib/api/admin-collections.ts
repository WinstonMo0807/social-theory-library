import { safeAdminHref } from "../admin-route-context";

export type CatalogPublication = {
  editorial_state?: string;
  public_state?: string;
  publicly_visible?: boolean;
  listed_publicly?: boolean;
  catalog_revision_active?: boolean;
  active_revision_id?: string | null;
  public_url?: string;
  fulltext_ready?: boolean;
  detail?: string;
};

export type WorkflowQueueItem = {
  id: string;
  item_id: string | null;
  work_id: string | null;
  edition_id: string | null;
  session_id?: string | null;
  source_type: string;
  title: string;
  source_filename?: string;
  document_type?: string;
  workbench_url: string;
  return_href?: string;
  publication?: CatalogPublication;
  health?: Record<string, string>;
  current_step: string;
  current_step_label?: string;
  overall_status: string;
  unresolved_count: number;
  warnings_count: number;
  blockers_count: number;
  updated_at: string;
};

export type CollectionPage<T> = {
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  next: string | null;
  previous: string | null;
  ordering: string;
  results: T[];
};

export type EditionFile = {
  id: string;
  kind: string;
  version: number;
  status: string;
  validation_status: string;
  is_current: boolean;
  original_filename: string;
  updated_at: string;
  page_count: number;
  source_asset_id?: string | null;
};

export type WorkLibraryRow = {
  row_type: "work" | "edition";
  id: string;
  work_id?: string;
  edition_id?: string;
  title: string;
  document_type: string;
  language: string;
  contributors: string[];
  edition_count?: number;
  primary_edition?: { id?: string; label?: string; version_label?: string };
  is_primary?: boolean;
  label?: string;
  publication?: CatalogPublication;
  health?: Record<string, string>;
  asset_state?: string;
  knowledge_status?: string;
  curation_status?: string;
  assets?: EditionFile[];
  current_reader_asset?: EditionFile | null;
  workbench_url?: string;
  updated_at: string;
};

export type WorkflowQueuePage = CollectionPage<WorkflowQueueItem> & {
  counts: Record<"all" | "continue" | "attention" | "exception" | "publication_ready", number>;
  continue_items: WorkflowQueueItem[];
  attention_items: WorkflowQueueItem[];
  exception_items: WorkflowQueueItem[];
  publication_ready: WorkflowQueueItem[];
  recent_items: WorkflowQueueItem[];
  candidate_review_count: number;
};

export const sourceLabels: Record<string, string> = { upload: "上传", manual: "手工书目", import: "导入编目", existing: "馆藏维护" };
export const documentLabels: Record<string, string> = { book: "图书", journal_article: "期刊论文", journal_issue: "整期期刊", thesis: "学位论文", report: "报告" };

/** Present the server's publication result, never infer it from Edition.state. */
export function publicationPresentation(publication?: CatalogPublication) {
  if (publication?.public_state === "published" && publication.catalog_revision_active !== true) return { label: "公开状态待核实", tone: "neutral" as const };
  switch (publication?.public_state) {
    case "published": return { label: publication.listed_publicly === true ? "已公开" : publication.listed_publicly === false ? "已公开，作品列表显示其他版本" : "已公开，列表显示情况待核对", tone: "success" as const };
    case "publishing": return { label: "发布处理中", tone: "info" as const };
    case "withdrawn": return { label: "已撤回", tone: "warning" as const };
    case "unpublished": return { label: "尚未公开", tone: "neutral" as const };
    default: return { label: "公开状态待核实", tone: "neutral" as const };
  }
}

export function publicationDescription(publication?: CatalogPublication) {
  if (publication?.public_state === "published" && publication.catalog_revision_active === true) return publication.listed_publicly === false ? "这个出版版本已公开，作品列表中显示的是另一个版本。" : "读者现在可以看到已发布的内容。修改资料后，需要再次发布才会更新。";
  if (publication?.public_state === "publishing") return "正在更新读者页面。请稍后刷新，确认更新是否完成。";
  if (publication?.public_state === "withdrawn") return "已经下架，读者不再看到这个版本。文件和修改记录仍保留。";
  if (publication?.public_state === "unpublished") return "读者还看不到这个版本。请核对资料、预览，再点击发布。";
  return "暂时无法确认公开状态，请刷新后再看。";
}

export function publicationPublicHref(publication?: CatalogPublication) {
  if (publication?.public_state !== "published" || publication.catalog_revision_active !== true || publication.listed_publicly !== true || !publication.public_url) return "";
  if (!/^\/works\//.test(publication.public_url) || /[\\\u0000-\u001f\u007f]/.test(publication.public_url)) return "";
  const target = new URL(publication.public_url, "https://library.invalid");
  return target.origin === "https://library.invalid" && target.pathname.startsWith("/works/") ? `${target.pathname}${target.search}${target.hash}` : "";
}

export function pdfValidationPresentation(value: string | undefined) {
  if (value === "valid") return { label: "PDF校验通过", tone: "success" as const };
  if (value === "invalid") return { label: "PDF校验失败", tone: "danger" as const };
  if (value === "pending") return { label: "PDF等待校验", tone: "warning" as const };
  return { label: "PDF校验待核实", tone: "neutral" as const };
}

export function queueWorkbenchHref(item: WorkflowQueueItem) {
  // A malformed/absent destination cannot silently select another catalogue.
  return item.workbench_url ? safeAdminHref(item.workbench_url, "") : "";
}

export function queueWorkspaceApi(item: WorkflowQueueItem) {
  if (item.work_id && item.edition_id) return `/catalog/admin/library/works/${encodeURIComponent(item.work_id)}/?edition=${encodeURIComponent(item.edition_id)}`;
  if (item.item_id) return `/catalog/admin/intake/${encodeURIComponent(item.item_id)}/`;
  return "";
}

export function selectedQueueItem(items: WorkflowQueueItem[], selectedId: string) {
  // Selection is explicit. Do not use results[0] when a requested ID is missing.
  return selectedId ? items.find((item) => item.id === selectedId) ?? null : null;
}
