"use client";

import { createRequestKey } from "../../lib/request-key";
import { useEffect, useRef, useState } from "react";
import { ApiRequestError } from "@/lib/api";
import { compactParallelReference, parallelRequest, type ParallelData, type ParallelRecord } from "@/lib/api/parallel-reader.client";

export function compactParallelData(data: ParallelData) {
  return {
    ...data,
    alignments: data.alignments.map(row => ({ ...row, note: row.note.trim(), left: compactParallelReference(row.left), right: compactParallelReference(row.right) })),
    terms: data.terms.map(row => ({ ...row, original: row.original.trim(), translation: row.translation.trim(), note: row.note.trim(),
      left: compactParallelReference(row.left), right: compactParallelReference(row.right) })),
  };
}
type Operation = { path: string; body: string; method: "POST" | "PATCH"; requestId: string; taskId?: string };
type Receipt = ParallelRecord & { applied_revision?: number };

export function useParallelSave(ownerId: number | undefined, onSaved: (record: ParallelRecord) => void) {
  const operation = useRef<Operation | null>(null);
  const pending = useRef(false);
  const lifetime = useRef<AbortController | null>(null);
  const [state, setState] = useState({ pending: false, unknown: false, error: "", conflict: false, conflictTaskId: "" });
  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => controller.abort();
  }, []);

  async function send(op: Operation, recover: boolean) {
    if (!ownerId || pending.current || lifetime.current?.signal.aborted) return;
    pending.current = true;
    setState(previous => ({ ...previous, pending: true, error: "" }));
    try {
      let receipt: Receipt | null = null;
      if (recover) {
        try {
          receipt = await parallelRequest<Receipt>(`/reading/parallel-tasks/by-request/?request_id=${op.requestId}`, { signal: lifetime.current?.signal }, ownerId);
        } catch (error) {
          if (!(error instanceof ApiRequestError) || error.status !== 404) throw error;
        }
      }
      receipt ??= await parallelRequest<Receipt>(op.path, { method: op.method, body: op.body, signal: lifetime.current?.signal }, ownerId);
      if (lifetime.current?.signal.aborted) return;
      if (!receipt?.id || op.taskId && receipt.id !== op.taskId) throw new ApiRequestError("保存回执不属于当前对齐任务，请保留输入并再次核对。", 0);
      operation.current = null;
      if (receipt.applied_revision && receipt.applied_revision !== receipt.revision) {
        setState({ pending: false, unknown: false, conflict: true, conflictTaskId: receipt.id, error: "本次保存已完成，但任务随后又有修改。当前输入仍保留，请读取最新版本后继续。" });
        return;
      }
      onSaved(receipt);
      setState({ pending: false, unknown: false, error: "", conflict: false, conflictTaskId: "" });
    } catch (error) {
      if (lifetime.current?.signal.aborted) return;
      const unknown = recover || !(error instanceof ApiRequestError) || [0, 408, 429].includes(error.status) || error.status >= 500;
      if (!unknown) operation.current = null;
      setState({ pending: false, unknown, conflict: error instanceof ApiRequestError && error.status === 409,
        conflictTaskId: error instanceof ApiRequestError && error.status === 409 ? op.taskId || "" : "",
        error: error instanceof Error ? error.message : "保存未完成，输入仍保留。" });
    } finally {
      pending.current = false;
    }
  }
  function save(data: ParallelData, record: ParallelRecord | null) {
    if (!ownerId || pending.current || operation.current || state.conflictTaskId) return;
    const requestId = createRequestKey();
    const op: Operation = {
      path: `/reading/parallel-tasks/${record ? `${record.id}/` : ""}`, method: record ? "PATCH" : "POST", requestId, taskId: record?.id,
      body: JSON.stringify({ request_id: requestId, ...(record ? { expected_revision: record.revision } : {}), data: compactParallelData(data) }),
    };
    operation.current = op;
    void send(op, false);
  }
  return { ...state, save, retry: () => { if (operation.current) void send(operation.current, true); },
    clearConflict: () => { if (!pending.current && !operation.current) setState({ pending: false, unknown: false, error: "", conflict: false, conflictTaskId: "" }); } };
}
