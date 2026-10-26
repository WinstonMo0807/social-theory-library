import { createRequestKey } from "./request-key";

const KEY = "stl:guest-records:v1";
export const GUEST_RECORDS_CHANGED = "stl:guest-records-changed";
type Source = { kind: "reading"; asset_id: string; revision_id: string; pdf_page: number }
  | { kind: "article"; issue_id: string; revision_id: string }
  | { kind: "search"; query: string; filters: Record<string, string | string[]> };
export type GuestRecord = Source & { id: string; at: string };
export type GuestRecords = { records: GuestRecord[]; available: boolean };
const uuid = (value: unknown) => typeof value === "string" && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value);
function valid(value: unknown): value is GuestRecord {
  if (!value || typeof value !== "object") return false;
  const row = value as GuestRecord;
  if (!uuid(row.id) || typeof row.at !== "string" || !Number.isFinite(Date.parse(row.at))) return false;
  if (row.kind === "reading") return uuid(row.asset_id) && uuid(row.revision_id) && Number.isInteger(row.pdf_page) && row.pdf_page > 0;
  if (row.kind === "article") return uuid(row.issue_id) && uuid(row.revision_id);
  return row.kind === "search" && typeof row.query === "string" && row.query.length <= 500 && !!row.filters && typeof row.filters === "object" && !Array.isArray(row.filters);
}
export function readGuestRecords(): GuestRecords {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { records: [], available: true };
    const value = JSON.parse(raw);
    if (value.version !== 1 || !Array.isArray(value.records) || !value.records.every(valid)) return { records: [], available: false };
    return { records: value.records, available: true };
  } catch { return { records: [], available: false }; }
}
function identity(row: Source) {
  return row.kind === "reading" ? `reading:${row.asset_id}:${row.revision_id}` : row.kind === "article" ? `article:${row.issue_id}:${row.revision_id}` : `search:${row.query}:${JSON.stringify(row.filters)}`;
}
// Call only after the public session has positively identified a guest.
// Account drafts, annotations and private research never enter this store.
export function saveGuestRecord(source: Source): boolean {
  const current = readGuestRecords();
  if (!current.available) return false;
  try {
    const row: GuestRecord = { ...source, id: createRequestKey(), at: new Date().toISOString() };
    if (!valid(row)) return false;
    const records = [...current.records.filter(item => identity(item) !== identity(row)), row].slice(-200);
    localStorage.setItem(KEY, JSON.stringify({ version: 1, records }));
    window.dispatchEvent(new Event(GUEST_RECORDS_CHANGED));
    return true;
  } catch { return false; }
}
