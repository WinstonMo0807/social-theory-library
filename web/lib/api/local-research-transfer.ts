import { importLocalResearch, passageReference, type LocalResearchImport, type QueryScope } from "./research.client";
import type { DiscoveryPassage } from "./discovery.types";

const previewStoreKey = "social-theory-library:c-preview:v1";
type PreviewTurn = { id: string; parent?: string; query: string; scope: string; selectedIds: string[]; results: DiscoveryPassage[]; created: string; status: string; notice: string };
type PreviewResearch = { id: string; title: string; selected: DiscoveryPassage[]; turns: PreviewTurn[]; active: string };
type PreviewStore = { version: 1; research: PreviewResearch[]; comparison?: Record<string, string>; workspace?: { history: boolean; materials: boolean } };

/** Called only by an explicit transfer action. Reading never modifies or removes the old store. */
export function readLocalResearchSnapshot(storage: Pick<Storage, "getItem"> = localStorage) {
  const raw = storage.getItem(previewStoreKey);
  if (!raw) return null;
  if (raw.length > 5_000_000) throw new Error("本机研究记录超过本页读取范围，请先保留原始导出，不能自动截断转存。");
  const parsed: unknown = JSON.parse(raw);
  if (!parsed || typeof parsed !== "object" || !("version" in parsed) || parsed.version !== 1 ||
      !("research" in parsed) || !Array.isArray(parsed.research)) throw new Error("本机研究资料格式不受支持，原记录已保留。");
  if (parsed.research.length > 100 || parsed.research.some(row => !row || typeof row.id !== "string" || typeof row.title !== "string") || new Set(parsed.research.map(row => row.id)).size !== parsed.research.length) throw new Error("本机研究记录身份不完整、重复或超过100项，请保留原始记录后整理。");
  return { raw, store: parsed as PreviewStore };
}

export function prepareLocalResearchTransfer(store: PreviewStore, localId: string, requestId: string): LocalResearchImport {
  const research = store.research.find(row => row.id === localId);
  if (!research || !Array.isArray(research.turns) || !Array.isArray(research.selected)) throw new Error("未找到完整的本机研究记录，原记录已保留。");
  const evidence = new Map<string, DiscoveryPassage>();
  for (const row of [...research.selected, ...research.turns.flatMap(turn => turn.results)]) {
    if (!row || typeof row !== "object" || !row.id || !row.asset_id || !row.document_revision_id || !Number.isInteger(row.pdf_page)) {
      throw new Error("这项研究含未具备正式文件及文字修订身份的本机材料，请先保留导出并完成馆藏入库，不能自动替换为其他来源。");
    }
    evidence.set(row.id, row);
  }
  function selectedRows(ids: string[]) {
    return ids.map(id => { const row = evidence.get(id); if (!row) throw new Error("某轮已选材料的来源记录缺失，请先保留本机导出。"); return row; });
  }
  function scope(value: string, selected: DiscoveryPassage[]): QueryScope {
    if (value === "all" || !value) return { kind: "library" };
    const works = value === "selected" ? [...new Set(selected.map(row => row.work.id))] : [value];
    if (!works.length || works.some(id => id.startsWith("local-"))) throw new Error("本机限定范围尚未对应正式馆藏，转存不会擅自扩大到全库。");
    return { kind: "works", filters: { work_ids: works } };
  }
  const active = research.turns.find(turn => turn.id === research.active);
  const body: LocalResearchImport = {
    schema_version: 1, request_id: requestId, local_id: research.id, title: research.title, question: research.title,
    selections: research.selected.map(passageReference), scope: active ? scope(active.scope, selectedRows(active.selectedIds)) : { kind: "library" },
    layout: store.workspace ? { ...store.workspace } : {},
    turns: research.turns.map(turn => ({ local_id: turn.id, ...(turn.parent ? { parent_local_id: turn.parent } : {}),
      question: turn.query, scope: scope(turn.scope, selectedRows(turn.selectedIds)),
      references: turn.results.map(passageReference), selected_references: selectedRows(turn.selectedIds).map(passageReference),
      notes: turn.notice || "", created_at: turn.created, status: turn.status })),
  };
  // Freeform comparison notes have no verified author/dimension/source mapping in the prototype.
  // Preserve their full text as notes, rather than inventing structured comparison cells.
  if (store.comparison && Object.keys(store.comparison).length) body.notes = JSON.stringify({ legacy_comparison: store.comparison });
  if (research.turns.length > 100 || research.selected.length > 400 || JSON.stringify(body).length > 250000) {
    throw new Error("本机研究超出一次转存限额，原记录完整保留；请先导出后拆分转存。");
  }
  return body;
}

export function transferLocalResearch(store: PreviewStore, localId: string, requestId: string) {
  // The caller keeps requestId until success or explicit abandonment. A retry never creates another project.
  return importLocalResearch(prepareLocalResearchTransfer(store, localId, requestId));
}
