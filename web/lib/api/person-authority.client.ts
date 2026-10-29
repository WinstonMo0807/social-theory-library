import { apiRequest, getServerSessionCredential } from "../api";
import { withPrivateOwner } from "./private-owner";
import type { components } from "./generated/schema";
import type { PersonBusinessImpact } from "./person-resolution";

export type AuthorityValues = components["schemas"]["AuthorityValuesRequest"];
export type AuthorityVariant = components["schemas"]["AuthorityVariantRequest"] & { source_kind?: string };
export type AuthorityInput = components["schemas"]["AuthorityInputRequest"];
export type AuthorityCommand = components["schemas"]["AuthorityCommandRequest"];
export type AuthorityPreview = components["schemas"]["AuthorityPreview"];
export type AuthorityReceipt = components["schemas"]["AuthorityReceipt"];
export type AuthorityDirectory = components["schemas"]["AuthorityDirectory"];
export type AuthorityDetail = Omit<components["schemas"]["AuthorityDetail"], "values" | "variants" | "impact" | "history" | "identifiers"> & {
  values: AuthorityValues; variants: AuthorityVariant[]; impact: PersonBusinessImpact;
  history: Array<{ id: string; created_at: string; operation: string; reason: string; fields: string[]; decision: string; target_id: string | null; event_ids: string[] }>;
  identifiers: Array<{ scheme: string; display_value: string; uri: string | null; status: string }>;
};

export function authorityRequest<T extends { actor_id: string }>(actor: string, path: string, options: RequestInit = {}) {
  const signal = AbortSignal.any([AbortSignal.timeout(30000), ...(options.signal ? [options.signal] : [])]);
  return withPrivateOwner(actor, async () => {
    const value = await apiRequest<T>(`/catalog/admin/people/${path}`, { ...options, signal, cache: "no-store", headers: { ...Object.fromEntries(new Headers(options.headers)), "X-Editor-Owner": actor } }, getServerSessionCredential(), false);
    if (value.actor_id !== actor) throw Error("操作账户已变化，请重新读取人物资料。");
    return value;
  }, signal);
}
