"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getServerSessionCredential } from "@/lib/api";
import { readAllPages } from "@/lib/api/read-all-pages";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { changeResearchSelection, readResearchProjectForOwner, type ProjectData, type ResearchRecord, type ResolvedEvidence } from "@/lib/api/research.client";
import { createRequestKey } from "@/lib/request-key";
import { confirmAction } from "@/lib/ui-dialog";

export function bookResearchSelections(projects: ResearchRecord<ProjectData>[], assetId: string) {
  return projects.flatMap(project => project.data.selections.filter(reference =>
    [reference, ...(reference.anchors || [])].some(anchor => anchor.asset_id === assetId),
  ).map(reference => ({ project, reference })));
}

/** Reuse project selections and their reversible removal; never delete the project. */
export function useReaderMaterials({ owner, assetId, active, refreshKey }: { owner: string; assetId: string; active: boolean; refreshKey: number }) {
  const identity = `${owner}:${assetId}`;
  const current = useRef(identity); current.current = identity;
  const locked = useRef(false);
  const [state, setState] = useState<{ identity: string; projects: ResearchRecord<ProjectData>[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [undo, setUndo] = useState<{ identity: string; project: ResearchRecord<ProjectData>; reference: ResolvedEvidence } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt(value => value + 1), []);
  useEffect(() => {
    if (!active || !owner || locked.current) return;
    const credential = getServerSessionCredential();
    if (!credential) return;
    const request = new AbortController();
    setLoading(true); setError("");
    void withPrivateOwner(owner, () => readAllPages<ResearchRecord<ProjectData>>(
      "/reading/research-projects/", credential, request.signal, owner,
    ), request.signal).then(projects => {
      if (!request.signal.aborted) setState({ identity, projects });
    }).catch(reason => {
      if (!request.signal.aborted) setError(reason instanceof Error ? reason.message : "研究选材读取失败。");
    }).finally(() => { if (!request.signal.aborted) setLoading(false); });
    return () => request.abort();
  }, [active, owner, identity, refreshKey, attempt]);
  const projects = state?.identity === identity ? state.projects : [];
  const accept = (project: ResearchRecord<ProjectData>) => {
    if (current.current !== identity) return;
    setState(value => value?.identity === identity ? { identity, projects: value.projects.map(row => row.id === project.id ? project : row) } : value);
  };
  async function change(project: ResearchRecord<ProjectData>, reference: ResolvedEvidence, action: "remove" | "undo") {
    if (locked.current || !owner || !reference.reference_id || current.current !== identity) return;
    locked.current = true;
    try {
      if (action === "remove" && !(await confirmAction(`从“${project.data.title || "未命名研究"}”移除这段选材？研究项目和其他材料会保留，可撤销本次移除。`))) return;
      if (current.current !== identity) return;
      setBusy(true); setError(""); setNotice("");
      const latest = await readResearchProjectForOwner(project.id, owner);
      if (current.current !== identity) return;
      const saved = await withPrivateOwner(owner, () => changeResearchSelection(project.id, {
        action, expected_revision: latest.revision, expected_owner_id: Number(owner),
        reference_id: reference.reference_id, request_id: createRequestKey(),
      }));
      if (current.current !== identity) return;
      accept(saved);
      setUndo(action === "remove" ? { identity, project: saved, reference } : null);
      setNotice(action === "remove" ? "已从这项研究移除选材。" : "已恢复选材及原顺序。");
    } catch (reason) {
      if (current.current !== identity) return;
      // A lost response is not a failed write. Read the saved membership before reporting it.
      try {
        const latest = await readResearchProjectForOwner(project.id, owner);
        if (current.current !== identity) return;
        accept(latest);
        const present = latest.data.selections.some(row => row.reference_id === reference.reference_id);
        if (present === (action === "undo")) {
          setUndo(action === "remove" ? { identity, project: latest, reference } : null);
          setNotice(present ? "已核对：选材已恢复。" : "已核对：这项研究中已移除此选材。");
          return;
        }
      } catch { /* Keep the last verified rows and offer an explicit reload. */ }
      if (current.current === identity) setError(reason instanceof Error ? reason.message : "未能确认选材变更，请重新读取后核对。");
    } finally { locked.current = false; if (current.current === identity) setBusy(false); }
  }
  return { rows: bookResearchSelections(projects, assetId), loading, ready: state?.identity === identity, error, notice, busy,
    undo: undo?.identity === identity ? undo : null, reload, change };
}
