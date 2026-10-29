export type ReaderFailureKind = "authentication" | "forbidden" | "unavailable" | "waiting" | "rate_limited" | "service_unavailable";
export type ReaderFailure = { kind: ReaderFailureKind; title: string; detail: string; retryable: boolean; canSignIn: boolean };

// Public explanations deliberately omit internal URLs, response bodies and
// diagnostics. A masked 404 cannot establish whether a private file exists.
export function readerFailure(status?: number): ReaderFailure {
  if (status === 401) return { kind: "authentication", title: "请先登录后再打开", detail: "这次阅读请求需要有效登录。登录后会返回原来的文献和阅读位置。", retryable: true, canSignIn: true };
  if (status === 403) return { kind: "forbidden", title: "当前没有阅读权限", detail: "当前账户无权访问此文件。请核对登录账户或联系管理员。", retryable: false, canSignIn: true };
  if (status === 404 || status === 410) return { kind: "unavailable", title: "这份文件当前不可访问", detail: "文件暂不可访问。链接、发布状态或权限可能已变化，请从馆藏详情重新打开。", retryable: true, canSignIn: false };
  if (status === 429) return { kind: "rate_limited", title: "阅读请求暂时过于频繁", detail: "请求过于频繁，请稍后重试。阅读位置和私人记录保留。", retryable: true, canSignIn: false };
  if (status === 409 || status === 423 || status === 425) return { kind: "waiting", title: "阅读文件暂时尚不可用", detail: "暂时无法加载原文，请稍后重试。", retryable: true, canSignIn: false };
  return { kind: "service_unavailable", title: "暂时未能连接阅读服务", detail: "读取文献信息时发生网络或服务异常，暂时不能判断文件状态。请重试；这不表示文献未上架。", retryable: true, canSignIn: false };
}

export function readerReturnPath(assetId: string, query: Record<string, string | undefined>) {
  const search = new URLSearchParams();
  for (const key of ["mode", "alignment", "page", "q", "focus", "passage", "evidence", "research_project", "research_turn", "reference", "revision", "return_to"]) {
    if (query[key] !== undefined) search.set(key, query[key]!);
  }
  return `/reader/${encodeURIComponent(assetId)}${search.size ? `?${search}` : ""}`;
}
