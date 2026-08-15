"use client";

import { Bookmark } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest, getStoredAccessToken } from "@/lib/api";

export function SaveTopicButton({ topicId }: { topicId: string }) {
  const [savedId, setSavedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const token = getStoredAccessToken();
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
  }, [topicId]);

  async function toggle() {
    const token = getStoredAccessToken();
    if (!token) {
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
      return;
    }
    if (busy) return;
    setBusy(true);
    try {
      if (savedId) {
        await apiRequest(`/reading/saved-topics/${savedId}/`, { method: "DELETE" }, token);
        setSavedId(null);
      } else {
        const created = await apiRequest<{ id: string }>(
          "/reading/saved-topics/",
          { method: "POST", body: JSON.stringify({ topic: topicId }) },
          token,
        );
        setSavedId(created.id);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      className={`button secondary ${savedId ? "saved" : ""}`}
      type="button"
      aria-pressed={Boolean(savedId)}
      disabled={busy}
      onClick={toggle}
    >
      {savedId ? "已收藏主题" : "收藏主题"}
      <Bookmark size={16} fill={savedId ? "currentColor" : "none"} />
    </button>
  );
}
