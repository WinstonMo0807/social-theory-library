import type { EvidenceReference, ResolvedEvidence } from "./api/research.client";
import { researchEvidenceReference } from "./api/research-evidence";

const key = "stl.public-materials.v1";
export const localMaterialEvent = "stl-public-materials-changed";
export type LocalCitationMaterial = { id: string; reference: EvidenceReference; note: string; createdAt: string };
type StorageLike = Pick<Storage, "getItem" | "setItem">;
const uuid = /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i;
function validAnchor(value: unknown): value is EvidenceReference {
  if (!value || typeof value !== "object") return false;
  const row = value as EvidenceReference;
  return typeof row.asset_id === "string" && uuid.test(row.asset_id) && typeof row.document_revision_id === "string"
    && uuid.test(row.document_revision_id) && Number.isInteger(row.pdf_page) && (row.pdf_page || 0) > 0
    && typeof row.content_hash === "string" && /^[\da-f]{64}$/i.test(row.content_hash)
    && (row.evidence_span_id === undefined || row.evidence_span_id === null || uuid.test(row.evidence_span_id))
    && (row.selection_start === undefined && row.selection_end === undefined || Number.isInteger(row.selection_start)
      && Number.isInteger(row.selection_end) && (row.selection_start ?? -1) >= 0 && (row.selection_end || 0) > (row.selection_start ?? -1));
}
/** Persist identities only. Every title, quotation and citation is re-read publicly. */
export function readLocalCitationMaterials(storage: StorageLike = localStorage): LocalCitationMaterial[] {
  const raw = storage.getItem(key);
  if (!raw) return [];
  if (raw.length > 200000) throw new Error("本机选材记录过大，原数据已保留。");
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed) || parsed.length > 100 || parsed.some(row => !row || typeof row.id !== "string" || row.id.length > 180
    || typeof row.note !== "string" || row.note.length > 200 || typeof row.createdAt !== "string"
    || (!validAnchor(row.reference) && !(Array.isArray(row.reference?.anchors) && row.reference.anchors.length > 0
      && row.reference.anchors.length <= 20 && row.reference.anchors.every(validAnchor))))) throw new Error("本机选材格式无效，原数据未改动。");
  return parsed.map(row => ({ id: row.id, note: row.note, createdAt: row.createdAt,
    reference: researchEvidenceReference(row.reference) }));
}
export function writeLocalCitationMaterials(rows: LocalCitationMaterial[], storage: StorageLike = localStorage) {
  if (rows.length > 100) throw new Error("本机最多保存 100 条选材，请先转存或移除。");
  storage.setItem(key, JSON.stringify(rows));
  if (typeof window !== "undefined") window.dispatchEvent(new Event(localMaterialEvent));
}
export function saveLocalCitationMaterial(reference: ResolvedEvidence, note: string) {
  if (reference.source_status !== "available" || !reference.reference_id) throw new Error("来源尚未核对，暂不能本机保存。");
  const rows = readLocalCitationMaterials();
  const existing = rows.find(row => row.id === reference.reference_id);
  if (existing) return { duplicate: true, row: existing };
  const row = { id: reference.reference_id, reference: researchEvidenceReference(reference), note: note.trim().slice(0, 200), createdAt: new Date().toISOString() };
  writeLocalCitationMaterials([...rows, row]);
  return { duplicate: false, row };
}
