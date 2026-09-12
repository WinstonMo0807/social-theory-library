import { apiRequest, getServerSessionCredential } from "../api";
import type { components } from "./generated/schema";

export type KnowledgeImageState = components["schemas"]["KnowledgeImageState"];
export type KnowledgeImageType = "knowledge_node" | "reading_path";
export const knowledgeImageEndpoint = (type: KnowledgeImageType, id: string) => `/catalog/admin/knowledge-media/${type}/${encodeURIComponent(id)}/`;

export function selectKnowledgeImage(type: KnowledgeImageType, id: string, mediaId: string | null, fingerprint: string) {
  return apiRequest<KnowledgeImageState>(knowledgeImageEndpoint(type, id), { method: "POST", body: JSON.stringify({ media_id: mediaId, fingerprint }) }, getServerSessionCredential());
}
