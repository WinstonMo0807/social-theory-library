import { apiRequest, getServerSessionCredential } from "../api";
import type { components } from "./generated/schema";

export type ScholarPortraitState = components["schemas"]["ScholarPortraitState"];
type Selection = components["schemas"]["ScholarPortraitRequestRequest"];

export const scholarPortraitEndpoint = (id: string) => `/catalog/admin/scholars/${encodeURIComponent(id)}/portrait/`;

export function selectScholarPortrait(id: string, input: Selection) {
  return apiRequest<ScholarPortraitState>(scholarPortraitEndpoint(id), { method: "POST", body: JSON.stringify(input) }, getServerSessionCredential());
}
