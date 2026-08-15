"use client";

import { Download } from "lucide-react";
import { useState } from "react";
import { apiRequest, normalizePublicResourceUrl } from "@/lib/api";

export function AssetDownloadButton({ assetId }: { assetId: string }) {
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function download() {
    setBusy(true);
    setStatus("");
    try {
      const access = await apiRequest<{ url: string; download_filename: string }>(
        `/distribution/assets/${encodeURIComponent(assetId)}/access/?download=1`,
      );
      const anchor = document.createElement("a");
      anchor.href = normalizePublicResourceUrl(access.url);
      anchor.download = access.download_filename;
      anchor.rel = "noopener";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setStatus("下载已开始");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "暂时无法取得下载地址。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className="button secondary" type="button" disabled={busy} onClick={download}>
        <Download size={16} /> {busy ? "正在准备……" : "下载 PDF"}
      </button>
      {status ? <small className="download-status" aria-live="polite">{status}</small> : null}
    </>
  );
}
