"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { ActionButton } from "@/components/action-feedback";
import { apiRequest } from "@/lib/api";

type PublicationStatus = {
  event_id: string | null;
  state: "not_started" | "processing" | "ready" | "failed";
  label: string;
  can_retry: boolean;
  failures: string[];
  withdrawal?: boolean;
};

export function PublicationRetryControl({ editionId, objectTarget, token, disabled = false, refreshKey = "", onCompleted }: {
  editionId?: string;
  objectTarget?: { objectType: string; objectId: string };
  token: string | null;
  disabled?: boolean;
  refreshKey?: string;
  onCompleted: () => void | Promise<void>;
}) {
  const [current, setCurrent] = useState<PublicationStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const statusUrl = editionId
    ? `/catalog/admin/editions/${encodeURIComponent(editionId)}/knowledge-status/`
    : objectTarget
      ? `/catalog/admin/knowledge-publications/status/?${new URLSearchParams({ object_type: objectTarget.objectType, object_id: objectTarget.objectId })}`
      : "";

  useEffect(() => {
    if (!statusUrl) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    apiRequest<PublicationStatus>(statusUrl, { signal: controller.signal }, token)
      .then((result) => {
        if (controller.signal.aborted) return;
        setCurrent(result);
        setError("");
        if (result.state === "processing") timer = setTimeout(() => setRefresh((value) => value + 1), 10000);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "暂时无法读取智能内容状态。");
      });
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [statusUrl, token, refresh, refreshKey]);

  const retry = async () => {
    if (!current?.event_id || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await apiRequest<PublicationStatus>(`/catalog/admin/knowledge-publications/${current.event_id}/retry/`, { method: "POST", body: "{}" }, token);
      setCurrent(result);
      setRefresh((value) => value + 1);
      await onCompleted();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重新处理未提交成功，请重试。");
    } finally {
      setBusy(false);
    }
  };

  if (!error && (!current || current.state === "not_started")) return null;
  return <section className="workflow-editorial-revision" aria-live="polite">
    <div><strong>{current?.label || "智能内容状态"}</strong>
      {current?.state === "failed" ? <p>{current.withdrawal ? "内容退出检索尚未完成，请重新处理。" : "智能内容更新遇到异常。已经就绪的作品仍可正常阅读。"}{current.failures.length ? `需要重新处理的内容包括${current.failures.join("、")}。` : ""}</p> : null}
      {error ? <p role="alert">{error}</p> : null}
    </div>
    {current?.can_retry ? <ActionButton className="button secondary" disabled={disabled || busy} state={busy ? "pending" : "idle"} pendingLabel="正在提交" onClick={() => void retry()}><RefreshCw size={14} />重新处理</ActionButton> : null}
  </section>;
}
