"use client";

import { Bookmark } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useActionGuard } from "@/lib/use-action-guard";
import { ActionButton } from "./action-feedback";
import { usePublicSession } from "./public-session-provider";

export function SaveTopicButton({ topicId }: { topicId: string }) {
  const [savedId, setSavedId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const { pendingAction, startAction, finishAction } = useActionGuard();
  const { state: session } = usePublicSession();
  const effectiveSavedId = session.status === "authenticated" ? savedId : null;

  useEffect(() => {
    if (session.status !== "authenticated") return;
    const token = getServerSessionCredential();
    if (!token || !topicId) return;
    let cancelled = false;
    apiRequest<{ results: { id: string }[] }>(
      `/reading/saved-topics/?topic=${encodeURIComponent(topicId)}`,
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
  }, [session.status, topicId]);

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
    if (!startAction("toggle-save-topic")) return;
    setError("");
    try {
      if (effectiveSavedId) {
        await apiRequest(`/reading/saved-topics/${effectiveSavedId}/`, { method: "DELETE" }, token);
        setSavedId(null);
      } else {
        const created = await apiRequest<{ id: string }>(
          "/reading/saved-topics/",
          { method: "POST", body: JSON.stringify({ topic: topicId }) },
          token,
        );
        setSavedId(created.id);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "主题收藏失败，请重试。");
    } finally {
      finishAction("toggle-save-topic");
    }
  }

  return (
    <ActionButton
      className={`button secondary ${effectiveSavedId ? "saved" : ""}`}
      type="button"
      pressed={Boolean(effectiveSavedId)}
      disabled={session.status === "loading"}
      state={pendingAction ? "pending" : error ? "error" : "idle"}
      pendingLabel={effectiveSavedId ? "正在取消收藏" : "正在收藏主题"}
      errorLabel="收藏失败，重试"
      title={error || undefined}
      onClick={() => void toggle()}
    >
      {effectiveSavedId ? "已收藏主题" : "收藏主题"}
      <Bookmark size={16} fill={effectiveSavedId ? "currentColor" : "none"} />
    </ActionButton>
  );
}
