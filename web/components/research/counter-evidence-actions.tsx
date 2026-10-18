"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Dialog } from "@/components/ui/dialog";
import { subscribeToSessionChanges } from "@/lib/api";
import { createReadingPlan, createResearchMemory, type ResearchRecord, type ResolvedEvidence, type Statement } from "@/lib/api/research.client";
import type { CounterTurnData } from "@/lib/api/counter-evidence.client";
import { counterAvailable } from "@/lib/api/counter-evidence.client";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { researchEvidenceKey, researchEvidenceReference } from "@/lib/api/research-evidence";

export function CounterSaveDialog({ ownerId, projectId, turnId, kind, statement, references, onClose, onDirty }: {
  ownerId: string; projectId: string; turnId?: string; kind: "note" | "plan"; statement: string; references: ResolvedEvidence[]; onClose: () => void; onDirty: (dirty: boolean) => void;
}) {
  const [body, setBody] = useState(kind === "plan" ? statement : `需要检验的判断：${statement}\n\n我的理解与待核对问题：`);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [saved, setSaved] = useState("");
  const [selected, setSelected] = useState(references.filter(counterAvailable).map(researchEvidenceKey));
  const [initial] = useState({ body, selected });
  const dirty = !saved && JSON.stringify({ body, selected }) !== JSON.stringify(initial);
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  function close() { if (!busy && (!dirty || window.confirm("当前内容尚未保存，确定放弃输入吗？"))) onClose(); }
  const alive = useRef(false), pending = useRef(false), request = useRef({ fingerprint: "", id: "" });
  useEffect(() => { alive.current = true; const off = subscribeToSessionChanges(() => { alive.current = false; setBody(""); setSelected([]); setSaved(""); request.current = { fingerprint: "", id: "" }; }); return () => { alive.current = false; off(); }; }, []);
  const selectedRefs = references.filter(ref => selected.includes(researchEvidenceKey(ref)) && counterAvailable(ref));
  const title = kind === "plan" ? "将选材加入阅读计划" : "保存到我的笔记";
  async function submit(event: FormEvent) {
    event.preventDefault(); if (pending.current || !alive.current || saved || !body.trim() || kind === "plan" && !selectedRefs.length) return;
    pending.current = true; setBusy(true); setError("");
    const common = { project_id: projectId, ...(turnId ? { turn_id: turnId } : {}) };
    const data = kind === "plan" ? { ...common, goal: body.trim(), references: selectedRefs.map(researchEvidenceReference) } : { ...common, body: body.trim(), kind: "understanding" as const, sources: selectedRefs.map(researchEvidenceReference) };
    const fingerprint = JSON.stringify({ kind, data });
    if (request.current.fingerprint !== fingerprint) request.current = { fingerprint, id: crypto.randomUUID() };
    try {
      const result = await withPrivateOwner(ownerId, async () => kind === "plan" ? (await createReadingPlan({ ...common, goal: body.trim(), references: selectedRefs.map(researchEvidenceReference), request_id: request.current.id })).id : (await createResearchMemory({ ...common, body: body.trim(), kind: "understanding", sources: selectedRefs.map(researchEvidenceReference), request_id: request.current.id })).id);
      if (alive.current) setSaved(result);
    } catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : "保存未完成，输入保留。"); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  }
  return <Dialog className="stl4-counter-dialog" open aria-labelledby="counter-save-title" onRequestClose={close}><form onSubmit={event => void submit(event)}><h2 id="counter-save-title">{title}</h2>{saved ? <><p role="status">{kind === "plan" ? "阅读计划已创建，可继续配置时间与阅读安排。" : "已保存为待确认笔记，未自动授权其他研究使用。"}</p><Link href={kind === "plan" ? `/account/plans/${saved}` : "/account/confirmed-notes"}>{kind === "plan" ? "打开阅读计划" : "查看我的笔记"}</Link></> : <><label>{kind === "plan" ? "阅读目标" : "本人笔记"}<textarea required maxLength={kind === "plan" ? 4000 : 20000} rows={6} disabled={busy} value={body} onChange={event => setBody(event.target.value)} /></label><fieldset disabled={busy}><legend>明确带入的原文材料</legend>{references.length ? references.map(ref => { const key = researchEvidenceKey(ref); return <label key={key}><input type="checkbox" checked={selected.includes(key)} disabled={!counterAvailable(ref)} onChange={event => setSelected(event.target.checked ? [...selected, key] : selected.filter(id => id !== key))} />{counterAvailable(ref) ? ref.title || "原文材料" : "来源不可用，不带入"}{ref.pdf_page ? ` · PDF ${ref.pdf_page}` : ""}</label>; }) : <p>当前没有选定原文。笔记仍可单独保存，不能据此视为已核实的学术结论。</p>}</fieldset>{error ? <p role="alert">{error}</p> : null}</>}<footer><button type="button" disabled={busy} onClick={close}>{saved ? "关闭" : "取消"}</button>{!saved ? <button className="is-primary" type="submit" disabled={busy || !body.trim() || kind === "plan" && !selectedRefs.length}>{busy ? "正在保存…" : title}</button> : null}</footer></form></Dialog>;
}

export function CounterSubclaims({ record, busy, error, onClose, onSave, onStart, onDirty }: {
  record: ResearchRecord<CounterTurnData>; busy: boolean; error: string; onClose: () => void;
  onDirty: (dirty: boolean) => void;
  onSave: (values: Array<Statement & { id: string }>, revision: number) => Promise<boolean>;
  onStart: (claim: Statement & { id: string }) => Promise<void>;
}) {
  const [values, setValues] = useState(record.data.subclaims || []), [revision, setRevision] = useState(record.revision);
  const [saved, setSaved] = useState(JSON.stringify(record.data.subclaims || []));
  const dirty = JSON.stringify(values) !== saved, stale = revision !== record.revision;
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  function close() { if (!busy && (!dirty || window.confirm("子命题拆分尚未保存，确定放弃修改吗？"))) onClose(); }
  return <Dialog className="stl4-counter-dialog" open aria-labelledby="counter-subclaim-title" onRequestClose={close}><h2 id="counter-subclaim-title">拆分与检验子命题</h2><p>把复杂判断拆成可单独核对的命题。保存后用于新分支，前次分析所用命题保持原样。</p>{values.map((claim, index) => <div className="stl4-counter-subclaim" key={claim.id}><label>子命题 {index + 1}<textarea maxLength={1200} required value={claim.proposition} disabled={busy} onChange={event => setValues(values.map(row => row.id === claim.id ? { ...row, proposition: event.target.value } : row))} /></label><button type="button" disabled={busy} onClick={() => setValues(values.filter(row => row.id !== claim.id))}>移除子命题</button><button type="button" disabled={busy || dirty || stale || claim.proposition.trim().length < 2} onClick={() => void onStart(claim)}>检验此子命题</button></div>)}<button type="button" disabled={busy || values.length >= 12} onClick={() => setValues([...values, { id: crypto.randomUUID(), proposition: "" }])}>添加子命题（{values.length} / 12）</button>{stale ? <p role="alert">本轮已更新，拆分内容保留。<button type="button" disabled={busy} onClick={() => setRevision(record.revision)}>核对最新轮次后沿用拆分</button></p> : null}{error ? <p role="alert">{error}</p> : null}<footer><button type="button" disabled={busy} onClick={close}>关闭</button><button type="button" className="is-primary" disabled={busy || stale || !dirty || values.some(row => row.proposition.trim().length < 2)} onClick={async () => { if (await onSave(values, revision)) { setSaved(JSON.stringify(values)); setRevision(revision + 1); } }}>保存子命题</button></footer></Dialog>;
}
