"use client";
import { useEvidenceLanguage } from "./evidence-language";

import { Bookmark, Star } from "lucide-react";
import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { readAllPages } from "@/lib/api/read-all-pages";
import { useActionGuard } from "@/lib/use-action-guard";
import { ActionButton } from "./action-feedback";
import { usePublicSession } from "./public-session-provider";

type SavedBatch = { owner: string; ids: string[]; values: Record<string, string | null> | null; error: string; retry: () => void; update: (work: string, id: string | null) => void };
const SavedBatchContext = createContext<SavedBatch | null>(null);

/** One owner-verified collection read for a result page, rather than three requests per card. */
export function SavedWorkStatusProvider({ workIds, children }: { workIds: string[]; children: ReactNode }) {
  const { state: session } = usePublicSession();
  const owner = session.status === "authenticated" && session.user ? String(session.user.id) : "";
  const idsKey = [...new Set(workIds)].sort().join(",");
  const key = `${owner}:${idsKey}`;
  const [batch, setBatch] = useState<{ key: string; values?: Record<string, string | null>; error?: string } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const epoch = useRef(0);
  useEffect(() => subscribeToSessionChanges(() => { epoch.current += 1; setBatch(null); }), []);
  useEffect(() => {
    const controller = new AbortController();
    const generation = ++epoch.current;
    if (owner && idsKey) withPrivateOwner(owner, async () => {
      const ids = idsKey.split(",");
      const rows: { id: string; work: string }[] = [];
      // The server accepts 50 identities per batch; long discovery lists keep the same bound.
      for (let offset = 0; offset < ids.length; offset += 50) rows.push(...await readAllPages<{ id: string; work: string }>(`/reading/saved/?work_ids=${encodeURIComponent(ids.slice(offset, offset + 50).join(","))}`, getServerSessionCredential()!, controller.signal, owner));
      return rows;
    }, controller.signal).then(rows => {
      if (!controller.signal.aborted && generation === epoch.current) setBatch({ key, values: Object.fromEntries(rows.map(row => [row.work, row.id])) });
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted && generation === epoch.current) setBatch({ key, error: reason instanceof Error ? reason.message : "收藏状态暂时无法读取。" });
    });
    return () => { controller.abort(); epoch.current += 1; };
  }, [owner, idsKey, key, attempt]);
  const current = batch?.key === key ? batch : null;
  return <SavedBatchContext.Provider value={{ owner, ids: idsKey.split(","), values: current?.values ?? null, error: current?.error ?? "", retry: () => { setBatch(null); setAttempt(value => value + 1); }, update: (work, id) => setBatch(value => value?.key === key && value.values ? { key, values: { ...value.values, [work]: id } } : value) }}>{children}</SavedBatchContext.Provider>;
}

export function SaveWorkButton({
  workId,
  compact = false,
  icon = "bookmark",
}: {
  workId?: string;
  compact?: boolean;
  icon?: "bookmark" | "star";
}) {
  const { t } = useEvidenceLanguage();
  const router = useRouter();
  const [snapshot, setSnapshot] = useState<{ key: string; id: string | null } | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const epoch = useRef(0);
  const desired = useRef<{ key: string; saved: boolean } | null>(null);
  const { pendingAction, startAction, finishAction } = useActionGuard();
  const { state: session } = usePublicSession();
  const batch = useContext(SavedBatchContext);
  const owner = session.status === "authenticated" && session.user ? String(session.user.id) : "";
  const key = `${owner}:${workId}`;
  const batched = Boolean(batch && batch.owner === owner && batch.ids.includes(workId ?? ""));
  const current = batched ? (batch?.values ? { key, id: batch.values[workId ?? ""] ?? null } : null) : snapshot?.key === key ? snapshot : null;
  const readError = error || (batched ? batch?.error : "");
  const effectiveSavedId = owner ? current?.id : null;

  useEffect(() => subscribeToSessionChanges(() => {
    epoch.current += 1; desired.current = null; setSnapshot(null); setError("");
  }), []);

  useEffect(() => {
    const controller = new AbortController();
    const generation = ++epoch.current;
    if (!owner || batched) return () => { controller.abort(); epoch.current += 1; };
    const token = getServerSessionCredential();
    if (!token || !workId) return;
    withPrivateOwner(owner, () => apiRequest<{ results: { id: string }[] }>(
      `/reading/saved/?work=${encodeURIComponent(workId)}`,
      { headers: { "X-Reader-Owner": owner }, cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]) },
      token,
      false,
    ), controller.signal)
      .then((payload) => {
        if (!controller.signal.aborted && epoch.current === generation) { setSnapshot({ key, id: payload.results[0]?.id ?? null }); setError(""); }
      })
      .catch((reason: unknown) => { if (!controller.signal.aborted && epoch.current === generation) setError(reason instanceof Error ? reason.message : "收藏状态暂时无法读取。"); });
    return () => {
      controller.abort(); epoch.current += 1;
    };
  }, [owner, workId, key, attempt, batched]);

  async function toggle() {
    if (session.status !== "authenticated") {
      router.push(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
      return;
    }
    const token = getServerSessionCredential();
    if (!token) {
      router.push(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
      return;
    }
    if (!current) { if (batched) batch?.retry(); else setAttempt(value => value + 1); return; }
    if (!workId || !startAction("toggle-save-work")) return;
    const generation = epoch.current;
    const target = desired.current?.key === key ? desired.current.saved : !effectiveSavedId;
    desired.current = { key, saved: target };
    setError("");
    try {
      const headers = { "X-Reader-Owner": owner };
      const result = await withPrivateOwner(owner, async () => {
        const latest = await apiRequest<{ results: { id: string }[] }>(`/reading/saved/?work=${encodeURIComponent(workId)}`, { headers, cache: "no-store", signal: AbortSignal.timeout(30000) }, token, false);
        const latestId = latest.results[0]?.id ?? null;
        if (!target && latestId) {
          await apiRequest(`/reading/saved/${latestId}/`, { method: "DELETE", headers, signal: AbortSignal.timeout(30000) }, token, false);
          return null;
        }
        if (target && !latestId) {
          const created = await apiRequest<{ id: string }>("/reading/saved/", { method: "POST", headers, body: JSON.stringify({ work: workId }), signal: AbortSignal.timeout(30000) }, token, false);
          return created.id;
        }
        return latestId;
      });
      if (generation === epoch.current) {
        setSnapshot({ key, id: result }); if (batched) batch?.update(workId, result); desired.current = null;
      }
    } catch (reason) {
      if (generation === epoch.current) setError(reason instanceof Error ? reason.message : "收藏操作结果待确认，请重试同一操作。");
    } finally {
      finishAction("toggle-save-work");
    }
  }

  return (
    <ActionButton
      className={effectiveSavedId ? "saved" : ""}
      type="button"
      onClick={() => void toggle()}
      disabled={!workId || session.status === "loading" || (Boolean(owner) && !current && !readError)}
      state={pendingAction ? "pending" : readError ? "error" : "idle"}
      pendingLabel={compact ? t("处理中") : effectiveSavedId ? t("正在取消") : t("正在收藏")}
      errorLabel={compact ? t("失败") : t("操作失败，重试")}
      pressed={Boolean(effectiveSavedId)}
      aria-label={effectiveSavedId ? t("取消收藏") : t("收藏")}
      title={readError ? t(readError) : undefined}
    >
      {icon === "star" ? <Star size={15} fill={effectiveSavedId ? "currentColor" : "none"} /> : <Bookmark size={15} fill={effectiveSavedId ? "currentColor" : "none"} />}
      {!compact ? (effectiveSavedId ? t("已收藏") : t("收藏")) : null}
    </ActionButton>
  );
}
