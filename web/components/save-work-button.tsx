"use client";

import { Bookmark } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useActionGuard } from "@/lib/use-action-guard";
import { ActionButton } from "./action-feedback";
import { usePublicSession } from "./public-session-provider";

export function SaveWorkButton({
  workId,
  compact = false,
}: {
  workId?: string;
  compact?: boolean;
}) {
  const [savedId, setSavedId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const { pendingAction, startAction, finishAction } = useActionGuard();
  const { state: session } = usePublicSession();
  const effectiveSavedId = session.status === "authenticated" ? savedId : null;

  useEffect(() => {
    if (session.status !== "authenticated") return;
    const token = getServerSessionCredential();
    if (!token || !workId) return;
    let cancelled = false;
    apiRequest<{ results: { id: string }[] }>(
      `/reading/saved/?work=${encodeURIComponent(workId)}`,
      {},
      token,
    )
      .then((payload) => {
        if (!cancelled) setSavedId(payload.results[0]?.id ?? null);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [session.status, workId]);

  async function toggle() {
    if (session.status !== "authenticated") {
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
      return;
    }
    const token = getServerSessionCredential();
    if (!token) {
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
      return;
    }
    if (!workId || !startAction("toggle-save-work")) return;
    setError("");
    try {
      if (effectiveSavedId) {
        await apiRequest(`/reading/saved/${effectiveSavedId}/`, { method: "DELETE" }, token);
        setSavedId(null);
      } else {
        const created = await apiRequest<{ id: string }>(
          "/reading/saved/",
          { method: "POST", body: JSON.stringify({ work: workId }) },
          token,
        );
        setSavedId(created.id);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "收藏操作失败，请重试。");
    } finally {
      finishAction("toggle-save-work");
    }
  }

  return (
    <ActionButton
      className={effectiveSavedId ? "saved" : ""}
      type="button"
      onClick={() => void toggle()}
      disabled={!workId || session.status === "loading"}
      state={pendingAction ? "pending" : error ? "error" : "idle"}
      pendingLabel={compact ? "处理中" : effectiveSavedId ? "正在取消" : "正在收藏"}
      errorLabel={compact ? "失败" : "操作失败，重试"}
      pressed={Boolean(effectiveSavedId)}
      aria-label={effectiveSavedId ? "取消收藏" : "收藏"}
      title={error || undefined}
    >
      <Bookmark size={15} fill={effectiveSavedId ? "currentColor" : "none"} />
      {!compact ? (effectiveSavedId ? "已收藏" : "收藏") : null}
    </ActionButton>
  );
}
