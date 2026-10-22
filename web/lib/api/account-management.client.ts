import { apiRequest, getServerSessionCredential } from "../api";
import type { components } from "./generated/schema";

export type ManagedUser = components["schemas"]["UserOutput"];
export type AccountDirectory = components["schemas"]["ManagementDirectory"];
export type AccountRoles = components["schemas"]["RoleMatrix"];
export type AccountPreview = components["schemas"]["ManagementPreview"];
export type AccountInput = components["schemas"]["ManagementInputRequest"];
export type AccountCommand = components["schemas"]["ManagementCommandRequest"];
export type AccountReceipt = components["schemas"]["ManagementReceipt"];
export type AccountHistory = components["schemas"]["ManagementHistory"];

export function accountRequest<T extends { actor_id: string }>(actor: string, path: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers); headers.set("X-Editor-Owner", actor);
  const signal = AbortSignal.any([AbortSignal.timeout(30000), ...(options.signal ? [options.signal] : [])]);
  return apiRequest<T>(`/auth/users/${path}`, { ...options, headers, signal, cache: "no-store" }, getServerSessionCredential(), false).then(value => {
    if (value.actor_id !== actor) throw Error("操作账户已变化，请重新读取账户管理。");
    return value;
  });
}
