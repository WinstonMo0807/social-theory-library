"use client";

import Link from "next/link";
import { ArrowRight, Bookmark, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest, normalizePublicResourceUrl } from "@/lib/api";
import { safeAuthDestination } from "@/lib/auth-navigation";
import { safeFeedbackPath } from "@/lib/api/feedback.client";
import type { components } from "@/lib/api/generated/schema";
import { MediaPlacement } from "./media-placement";

type Context = components["schemas"]["ReturnContextOutput"];

export function AuthReturnCard({ destination }: { destination: string }) {
  const path = safeAuthDestination(destination), publicPath = safeFeedbackPath(path);
  const label = path.startsWith("/reader/") ? "原来的阅读位置" : path.startsWith("/account/research/") ? "原来的研究会话" : path.startsWith("/account") ? "你的读者中心" : path.startsWith("/admin") ? "原来的管理工作台" : "刚才浏览的页面";
  const [failedCover, setFailedCover] = useState("");
  const [loaded, setLoaded] = useState<{ path: string; value: Context | null; error: string } | null>(null), [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!publicPath) return;
    const request = new AbortController(), signal = AbortSignal.any([request.signal, AbortSignal.timeout(15000)]);
    apiRequest<Context>(`/auth/return-context/?${new URLSearchParams({ path: publicPath })}`, { cache: "no-store", signal }, null, false)
      .then(value => { if (!request.signal.aborted) { if (value.path !== publicPath) throw new Error("返回资料与原页面不一致。"); setLoaded({ path: publicPath, value, error: "" }); } })
      .catch(error => { if (!request.signal.aborted) setLoaded({ path: publicPath, value: null, error: error instanceof Error ? error.message : "公开资料暂不可读取。" }); });
    return () => request.abort();
  }, [publicPath, attempt]);
  const source = loaded?.path === publicPath ? loaded : null, data = source?.value;
  return <><Link className="auth-return-card" href={path}>
    {data?.cover_url && failedCover !== data.cover_url ? <MediaPlacement uses={data.display_uses} fallback={<Bookmark size={30} />}><img className="auth-return-cover" src={normalizePublicResourceUrl(data.cover_url)} alt="" onError={() => setFailedCover(data.cover_url)} width={124} height={150} /></MediaPlacement> : <Bookmark size={30} />}
    <span>{data?.source_type ? <small className="auth-return-kind">{data.source_type}{data.version_label ? ` · ${data.version_label}` : ""}</small> : null}<strong>{data?.title || label}</strong>{data?.authors.length ? <small>{data.authors.join(" / ")}</small> : null}<small>{data?.location || (data?.state === "replaced" ? "原文件已有新版本，原页码需重新核对。" : "登录后返回刚才的页面。")}</small></span><ArrowRight size={17} />
  </Link>{publicPath ? <p className="auth-return-status" role="status">{source?.error ? <>{source.error}<button type="button" onClick={() => { setLoaded(null); setAttempt(value => value + 1); }}><RefreshCw size={13} />重新读取公开资料</button></> : data ? data.notice : "正在核对原页面的公开资料…"}</p> : <p className="auth-return-status">登录前不读取或显示私人研究、笔记与管理资料。</p>}</>;
}
