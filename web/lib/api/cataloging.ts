import { apiRequest, getServerSessionCredential } from "../api";

export type CatalogingSession = {
  id: string;
  source_type: "manual" | "upload" | "import" | "existing";
  status: "drafting" | "reviewing" | "ready" | "publishing" | "published" | "abandoned";
  work_id: string | null;
  edition_id: string | null;
  upload_item_id: string | null;
  base_public_revision_id: string | null;
  workbench_url: string;
};

export function createManualCatalog(input: { title: string; document_type: string; language: string; request_key: string }) {
  return apiRequest<CatalogingSession>("/catalog/admin/cataloging-sessions/", {
    method: "POST", body: JSON.stringify({ ...input, source_type: "manual" }),
  }, getServerSessionCredential());
}
