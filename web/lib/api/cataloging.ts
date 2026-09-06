import { apiRequest, getServerSessionCredential } from "../api";
import type { components } from "./generated/schema";

export type CatalogingSession = components["schemas"]["CatalogingSession"];
export type ManualCatalogInput = Omit<components["schemas"]["CatalogingSessionCreateRequest"], "source_type" | "edition_id" | "upload_item_id">;

export function createManualCatalog(input: ManualCatalogInput) {
  return apiRequest<CatalogingSession>("/catalog/admin/cataloging-sessions/", {
    method: "POST", body: JSON.stringify({ ...input, source_type: "manual" }),
  }, getServerSessionCredential());
}
