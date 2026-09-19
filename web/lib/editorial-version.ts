import { ApiRequestError } from "./api";

export function isEditorialConflict(reason: unknown): boolean {
  return reason instanceof ApiRequestError && reason.status === 409;
}

/** Use the version read into this form, never a newer background list response. */
export function editorialHeaders(record: unknown): Record<string, string> {
  const version = record && typeof record === "object" && "edit_version" in record ? record.edit_version : "";
  if (typeof version !== "string" || !/^[a-f0-9]{64}$/.test(version)) {
    throw new Error("请重新打开这条资料后再保存。当前页面缺少修改版本，你的输入尚未提交。");
  }
  return { "If-Match": version };
}
