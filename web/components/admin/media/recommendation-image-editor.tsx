"use client";

import { useEffect, useRef, useState } from "react";
import { LoaderCircle, RefreshCw } from "lucide-react";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import type { components } from "@/lib/api/generated/schema";

type Preview = components["schemas"]["RecommendationImagePreview"];
type Props = {
  workId: string;
  editionId?: string;
  documentType: string;
  onMessage: (message: string) => void;
  beforeAction?: () => Promise<boolean>;
  onUpdated?: () => void | Promise<void>;
  mediaLibraryUrl?: string;
  disabled?: boolean;
};

export function RecommendationImageEditor(props: Props) {
  return <ImageEditor key={`${props.workId}:${props.editionId ?? ""}:${props.mediaLibraryUrl ?? ""}`} {...props} />;
}

function ImageEditor({ workId, editionId, documentType, onMessage, beforeAction, onUpdated, mediaLibraryUrl, disabled = false }: Props) {
  const token = getServerSessionCredential();
  const editionQuery = editionId ? `?edition_id=${encodeURIComponent(editionId)}` : "";
  const metadata = useApiResource<Preview>(workId ? `/catalog/admin/works/${workId}/recommendation-image/metadata/${editionQuery}` : "", token);
  const [image, setImage] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [failedPreview, setFailedPreview] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  const available = metadata.data?.available === true;
  const preview = available ? `${normalizePublicResourceUrl(metadata.data!.preview_url)}?v=${encodeURIComponent(metadata.data!.updated_at)}` : "";
  const mediaHref = mediaLibraryUrl || metadata.data?.media_library_url;

  async function act(action: "upload" | "clear" | "regenerate" | "choose") {
    if (request.current || disabled || !token) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    let saved = false;
    try {
      if (beforeAction && !await beforeAction()) return;
      if (controller.signal.aborted) return;
      if (action === "choose") {
        if (mediaHref) window.location.assign(mediaHref);
        return;
      }
      let body: FormData | string | undefined;
      if (action === "upload") {
        if (!image) return;
        const form = new FormData();
        form.append("image", image);
        body = form;
      } else if (action === "regenerate") {
        body = JSON.stringify({ action: "regenerate" });
      }
      const result = await apiRequest<Preview>(`/catalog/admin/works/${workId}/recommendation-image/${editionQuery}`, {
        method: action === "clear" ? "DELETE" : "POST", body, signal: controller.signal,
      }, token);
      if (controller.signal.aborted) return;
      saved = true;
      setImage(null);
      setFailedPreview("");
      metadata.retry();
      onMessage(result.detail);
      await onUpdated?.();
    } catch (reason) {
      if (!controller.signal.aborted) onMessage(`${saved ? "图例已保存，但刷新失败。" : ""}${reason instanceof Error ? reason.message : "推荐图例处理失败，请重试。"}`);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
      request.current = null;
    }
  }

  return <section className="recommendation-image-review" aria-label="推荐图例编辑">
    <header><div><h3>推荐卡片图例</h3><p>{["book", "journal_issue"].includes(documentType) ? "未另选图例时使用书封。" : "可以使用 PDF 页面或媒体库图片。"} 修改先保存到草稿，发布后才影响读者。</p></div>
      <div><button type="button" disabled={busy || disabled || !mediaHref} onClick={() => void act("choose")}>从媒体库选择图例</button><button type="button" disabled={busy || disabled} onClick={() => void act("regenerate")}><RefreshCw size={14} />恢复自动图例</button><button type="button" disabled={busy || disabled} onClick={() => void act("clear")}>移除图例选择</button></div>
    </header>
    {metadata.error ? <p role="alert">{metadata.error}<button type="button" onClick={metadata.retry}>重试读取图例</button></p> : null}
    <div className="recommendation-image-body">
      <div className={`recommendation-image-preview${metadata.data && !available ? " missing" : ""}`}>
        {preview && failedPreview !== preview ? <picture><source srcSet={preview} /><img src={preview} alt="当前草稿推荐图例" width={320} height={180} onError={() => setFailedPreview(preview)} style={{ width: "100%", height: "100%", objectFit: "contain" }} /></picture> : <span>{metadata.loading ? "正在读取图例…" : metadata.error ? "图例状态未能读取" : failedPreview === preview && preview ? "图例加载失败，请重试" : "尚无图例"}</span>}
      </div>
      <div><label className="knowledge-image-upload"><span>{image?.name || "选择图例图片"}</span><input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy || disabled} onChange={(event) => setImage(event.target.files?.[0] ?? null)} /></label>
        <button className="button secondary" type="button" disabled={!image || busy || disabled} onClick={() => void act("upload")}>{busy ? <LoaderCircle className="spin" size={15} /> : null}上传并保存到草稿</button>
        <small>支持 JPEG、PNG、WebP，最多 12 MB。移除选择不会删除原件或历史图片。</small>
        {metadata.data?.canonical_write_deferred ? <p role="status">当前预览为待发布图例，公开页面仍使用原版本。</p> : null}
        {failedPreview === preview && preview ? <button type="button" onClick={() => { setFailedPreview(""); metadata.retry(); }}>重试图例图片</button> : null}
      </div>
    </div>
  </section>;
}
