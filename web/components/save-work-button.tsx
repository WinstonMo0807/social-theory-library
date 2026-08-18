"use client";

import { Bookmark } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

export function SaveWorkButton({
  workId,
  compact = false,
}: {
  workId?: string;
  compact?: boolean;
}) {
  const [savedId, setSavedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
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
  }, [workId]);

  async function toggle() {
    const token = getServerSessionCredential();
    if (!token) {
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
      return;
    }
    if (!workId || busy) return;
    setBusy(true);
    try {
      if (savedId) {
        await apiRequest(`/reading/saved/${savedId}/`, { method: "DELETE" }, token);
        setSavedId(null);
      } else {
        const created = await apiRequest<{ id: string }>(
          "/reading/saved/",
          { method: "POST", body: JSON.stringify({ work: workId }) },
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
      className={savedId ? "saved" : ""}
      type="button"
      onClick={toggle}
      disabled={!workId || busy}
      aria-pressed={Boolean(savedId)}
      aria-label={savedId ? "取消收藏" : "收藏"}
    >
      <Bookmark size={15} fill={savedId ? "currentColor" : "none"} />
      {!compact ? (savedId ? "已收藏" : "收藏") : null}
    </button>
  );
}
