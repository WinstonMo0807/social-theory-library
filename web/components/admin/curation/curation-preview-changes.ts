import type { KnowledgePreviewPayload } from "../preview/knowledge-page-preview";

export type CurationPreviewModule = {
  module_id: string;
  preview_anchor?: string;
  display_name: string;
  serializer_fields?: string[];
  canonical_fields?: string[];
  curated_fields?: string[];
  has_draft?: boolean;
};
export type CurationPreviewChange = CurationPreviewModule & { pageId: string };
type PreviewControl = { page_tree?: Array<{ page_id: string; modules: CurationPreviewModule[]; preview?: { supported?: boolean } }> };
const valueAt = (data: unknown, path: string): unknown => path.split(".").reduce<unknown>((value, key) => value && typeof value === "object" ? (value as Record<string, unknown>)[key] : undefined, data);
const overlaps = (left: string, right: string) => left === right || left.startsWith(`${right}.`) || right.startsWith(`${left}.`);

/** Match saved edits to the existing public serializer contract, never to guessed fields. */
export function curationPreviewChanges(payload: KnowledgePreviewPayload, changedFields: string[]): CurationPreviewChange[] {
  const control = payload.public_control as PreviewControl | undefined;
  const draft = payload.perspectives.draft;
  const published = payload.perspectives.published;
  if (!draft.available) return [];
  const seen = new Set<string>();
  return (control?.page_tree || []).filter(page => page.preview?.supported !== false).flatMap(page => page.modules.flatMap(module => {
    const fields = module.serializer_fields || [];
    const declared = [...fields, ...(module.canonical_fields || []), ...(module.curated_fields || [])];
    const unsupported = draft.unsupported_preview_fields || [];
    if (declared.some(field => unsupported.some(missing => overlaps(field, missing)))) return [];
    const edited = module.has_draft || declared.some(field => changedFields.some(changed => overlaps(field, changed)));
    const differs = fields.some(field => JSON.stringify(valueAt(draft.data, field)) !== JSON.stringify(valueAt(published.available ? published.data : null, field)));
    if (seen.has(module.module_id) || !edited || !differs) return [];
    seen.add(module.module_id);
    return [{ ...module, pageId: page.page_id }];
  }));
}
