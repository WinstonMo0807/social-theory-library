export type AdminSearchParams = Record<string, string | string[] | undefined>;

export function firstParam(value: string | string[] | undefined, fallback = "") {
  return (Array.isArray(value) ? value[0] : value) ?? fallback;
}

/** Return destinations are same-origin admin paths, never caller-provided origins. */
export function safeAdminHref(value: string | null | undefined, fallback = "/admin/library") {
  if (!value || !/^\/admin(?:\/|\?|#|$)/.test(value) || /[\\\u0000-\u001f\u007f]/.test(value)) return fallback;
  const parsed = new URL(value, "https://admin.invalid");
  if (parsed.origin !== "https://admin.invalid" || !/^\/admin(?:\/|$)/.test(parsed.pathname)) return fallback;
  return `${parsed.pathname}${parsed.search}${parsed.hash}`;
}

export function preservingAdminRedirect(path: string, params: AdminSearchParams, hash = "", omit: string[] = []) {
  const url = new URL(safeAdminHref(path), "https://admin.invalid");
  for (const [key, raw] of Object.entries(params)) {
    if (omit.includes(key) || raw === undefined) continue;
    url.searchParams.delete(key);
    for (const value of Array.isArray(raw) ? raw : [raw]) url.searchParams.append(key, value);
  }
  if (hash) url.hash = hash;
  return `${url.pathname}${url.search}${url.hash}`;
}

export function withAdminReturn(target: string, returnTo: string, hash?: string) {
  const url = new URL(safeAdminHref(target), "https://admin.invalid");
  url.searchParams.set("return_to", safeAdminHref(returnTo));
  if (hash) url.hash = hash;
  return `${url.pathname}${url.search}${url.hash}`;
}

export function adminPageNumber(value: string | null | undefined) {
  const number = Number(value);
  return Number.isSafeInteger(number) && number > 0 ? number : 1;
}

/** Preserve all object/filter fields while changing only explicitly supplied keys. */
export function adminListHref(path: string, search: string, updates: Record<string, string | number | null>, clearSelection = false) {
  const params = new URLSearchParams(search);
  for (const [key, value] of Object.entries(updates)) {
    if (value === null || value === "") params.delete(key); else params.set(key, String(value));
  }
  if (clearSelection) params.delete("selection");
  return `${path}${params.size ? `?${params}` : ""}`;
}

export function adminLoginHref(pathname: string, search: string, hash = "") {
  const next = safeAdminHref(`${pathname}${search ? `?${search.replace(/^\?/, "")}` : ""}${hash}`);
  return `/login?next=${encodeURIComponent(next)}`;
}

export function adminTaskScope(pathname: string) {
  if (/^\/admin\/(uploads|review|publication|cataloging|intake)(?:\/|$)/.test(pathname) || pathname === "/admin") return { title: "待办与上架", detail: "上传来源、作品与出版版本分别保留。保存草稿、确认发布和公开结果各自核验；不会仅凭任务已接收显示完成。" };
  if (/^\/admin\/(library|media)(?:\/|$)/.test(pathname)) return { title: "馆藏", detail: "文件和阅读操作以当前出版版本为准。原件、历史文件、人工确认和读者私人记录保留；媒体上传不自动公开。" };
  if (/^\/admin\/(reading-paths|recommendations|about)(?:\/|$)/.test(pathname)) return { title: "公开展示", detail: "这里管理人工编排及公开内容。按各模块真实来源说明保存、预览与生效规则；推荐选择和统计汇总不等同于普通文本编辑。" };
  if (/^\/admin\/(processing|status|system-health|query-lexicon|semantic-index)(?:\/|$)/.test(pathname)) return { title: "处理与服务", detail: "检测结果有自己的检查时间与适用范围。重试和恢复以接口权限及原任务记录为准，服务可连接不等于当前对象已处理正确。" };
  if (/^\/admin\/(settings|distribution|users|analytics)(?:\/|$)/.test(pathname)) return { title: "系统管理", detail: "设置、备份、用户和审计各有权限与作用范围。敏感操作仍限Owner；任务完成不替代结果核验，备份存在不替代恢复演练。" };
  return { title: "知识与关联", detail: "规范对象、原始署名、候选和人工关系分别管理。编辑范围与公开页面来源从对象信息读取，草稿修改不自动成为公开事实。" };
}
