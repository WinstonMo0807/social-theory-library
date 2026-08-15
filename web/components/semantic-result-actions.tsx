"use client";

import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { apiRequest } from "@/lib/api";

export function SemanticResultActions({
  query,
  chunkId,
  rank,
}: {
  query: string;
  chunkId: string;
  rank: number;
}) {
  const [feedback, setFeedback] = useState<boolean | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  async function sendFeedback(relevant: boolean) {
    if (feedback !== null || sending) return;
    setSending(true);
    setError("");
    try {
      await apiRequest("/catalog/semantic-search/feedback/", {
        method: "POST",
        body: JSON.stringify({ query, chunk_id: chunkId, rank, relevant }),
      });
      setFeedback(relevant);
    } catch {
      setError("暂未保存，请稍后重试");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="semantic-result-actions">
      <span>{feedback === null ? "这条结果是否相关（可选）" : "感谢反馈"}</span>
      <button disabled={sending || feedback !== null} className={feedback === true ? "active" : ""} type="button" aria-label="相关" title="累计到足够样本后用于轻量校准排序" onClick={() => void sendFeedback(true)}><ThumbsUp size={15} /></button>
      <button disabled={sending || feedback !== null} className={feedback === false ? "active" : ""} type="button" aria-label="不相关" title="累计到足够样本后用于轻量校准排序" onClick={() => void sendFeedback(false)}><ThumbsDown size={15} /></button>
      {error ? <small role="status">{error}</small> : null}
    </div>
  );
}
