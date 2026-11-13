"use client";
import { SourceText } from "@/components/source-text";


import { confirmAction } from "@/lib/ui-dialog";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { counterAttributions, counterAvailable, counterRelation, counterRelations, type CounterAnalysis, type CounterAttribution, type CounterDecisionInput, type CounterRelation } from "@/lib/api/counter-evidence.client";
import { researchReaderHref } from "@/lib/api/research-evidence";
import { ResearchEvidenceCover } from "./research-evidence-card";

export function CounterEvidenceEditor({ row, revision, busy, running, error, onSave, onClose, onDirty }: {
  row: CounterAnalysis; revision: number; busy: boolean; running: boolean; error: string;
  onSave: (body: Omit<CounterDecisionInput, "request_id">) => Promise<boolean>; onClose: () => void; onDirty: (dirty: boolean) => void;
}) {
  const [expected, setExpected] = useState(revision);
  const [relation, setRelation] = useState<CounterRelation>(counterRelation(row));
  const [note, setNote] = useState(row.decision?.note || "");
  const [attribution, setAttribution] = useState<CounterAttribution>(row.decision?.attribution || row.candidate_statement?.attribution || "uncertain");
  const [scopeNote, setScopeNote] = useState(row.decision?.scope_note || "");
  const [saveNote, setSaveNote] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [initial] = useState({ relation, note, attribution, scopeNote, saveNote });
  const dirty = JSON.stringify({ relation, note, attribution, scopeNote, saveNote }) !== JSON.stringify(initial);
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  async function close() { if (!busy && (!dirty || (await confirmAction("分类输入尚未保存，确定放弃当前更正吗？")))) onClose(); }
  const available = counterAvailable(row.reference), stale = expected !== revision;
  const reviewable = available && !running && row.status !== "awaiting_analysis";
  const suggestion = row.model_suggestion, href = researchReaderHref(row.reference);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || stale || !reviewable || !note.trim()) return;
    if (await onSave({ id: row.id, action: "confirm", expected_revision: expected, relation, note: note.trim(), attribution, scope_note: scopeNote.trim(), save_as_note: saveNote })) onClose();
  }
  return <section className="stl4-counter-editor" aria-label="纠正证据分类"><header><h2>选中的证据</h2><button type="button" disabled={busy} onClick={close}>返回结果列表</button></header>
    {available ? <><div className="stl4-counter-editor-source"><ResearchEvidenceCover reference={row.reference}/><div><h3>{row.reference.title || "原文材料"}</h3><p>{row.reference.citation || row.reference.authors?.join("、")}</p><CounterLocation row={row} />{href ? <Link className="stl4-counter-button" href={href} target="_blank" rel="noreferrer">查看原文</Link> : <small>当前未提供完整原文入口，请重新读取来源。</small>}</div></div><h3>原文内容（节选）</h3><blockquote><SourceText text={(row.reference.quote || row.reference.text || "尚未提供原文文字，请打开原文核对。") || ""} /></blockquote>
      <section className="stl4-counter-initial"><h3>系统初步结果</h3><p>候选分类：<strong>{counterRelations[suggestion?.relation || "insufficient_evidence"] || "待复核"}</strong></p><p>{suggestion?.reason || row.reason || "尚未取得关系建议，需要本人回到原文判断。"}</p>{suggestion?.scope_difference ? <p>范围差异提示：{suggestion.scope_difference}</p> : null}<p>归属线索：{counterAttributions[row.candidate_statement?.attribution || "uncertain"]}</p><small>初步结果保留。人工纠正只影响本人的分类记录。</small></section></> : <p className="stl4-counter-warning" role="alert">原文已变化、撤回或不可访问，旧片段与系统分析不再显示。前次人工记录保留，需重新取得原文后核对。</p>}
    {row.status === "awaiting_analysis" ? <p role="status">已找到原文，正在分析关系。请等待完成；若处理失败，可重试。</p> : null}<form onSubmit={event => void submit(event)}><fieldset disabled={busy || !reviewable}><legend>人工更正分类</legend>{Object.entries(counterRelations).map(([key, label]) => <label key={key}><input type="radio" name={`counter-relation-${row.id}`} checked={relation === key} onChange={() => setRelation(key as CounterRelation)} />{label}</label>)}</fieldset>
      <label>观点归属<select data-stl-select value={attribution} disabled={busy || !reviewable} onChange={event => setAttribution(event.target.value as CounterAttribution)}>{Object.entries(counterAttributions).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>更正原因（必填）<textarea required maxLength={4000} rows={4} disabled={busy || !reviewable} value={note} onChange={event => setNote(event.target.value)} placeholder="说明这段原文与命题的关系，以及判断依据" /></label>
      <label>对象、时间、地区或条件差异（可选）<textarea maxLength={4000} rows={2} disabled={busy || !reviewable} value={scopeNote} onChange={event => setScopeNote(event.target.value)} /></label>
      <label className="stl4-counter-note-choice"><input type="checkbox" checked={saveNote} disabled={busy || !reviewable} onChange={event => setSaveNote(event.target.checked)} /><span>同时保存到我的笔记<small>新增待确认笔记，不自动用于其他研究。</small></span></label>
      {stale ? <p role="alert">本轮记录已更新，当前输入保留。<button type="button" disabled={busy} onClick={() => setExpected(revision)}>核对最新结果后沿用输入</button></p> : null}{error ? <p role="alert">{error}</p> : null}
      <footer><button type="button" disabled={busy} onClick={close}>取消</button><button className="is-primary" type="submit" disabled={busy || stale || !reviewable || !note.trim()}>确认并保存</button></footer>
    </form>
    {row.decision ? <section className="stl4-counter-previous"><h3>本人已保存判断</h3><p>{counterRelations[row.relation]} · {row.decision.note}</p>{row.decision.scope_note ? <p>{row.decision.scope_note}</p> : null}<time dateTime={row.decision.at}>{new Date(row.decision.at).toLocaleString("zh-CN")}</time>{clearing ? <div><p>撤回后恢复为待本人复核，原文和系统候选保留；已经保存的独立笔记不删除。</p><button type="button" disabled={busy || stale || running} onClick={async () => { if (await onSave({ id: row.id, expected_revision: expected, action: "clear" })) onClose(); }}>确认撤回本人判断</button><button type="button" disabled={busy} onClick={() => setClearing(false)}>保留判断</button></div> : <button type="button" disabled={busy} onClick={() => setClearing(true)}>撤回本人判断</button>}</section> : null}
    {row.decision_history?.length ? <details data-disclosure="collection"><summary>前次人工记录（{row.decision_history.length}）</summary>{row.decision_history.map((item, index) => <section key={index}><time dateTime={item.at}>{new Date(item.at).toLocaleString("zh-CN")}</time><p>{counterRelations[item.relation]} · {item.decision?.note || "未填写说明"}</p>{item.decision?.scope_note ? <p>{item.decision.scope_note}</p> : null}</section>)}</details> : null}
  </section>;
}

export function CounterLocation({ row }: { row: CounterAnalysis }) {
  const ref = row.reference;
  const anchors = ref.anchors?.length ? ref.anchors : [ref];
  const location = anchors.map(anchor => [anchor.printed_labels?.length ? `书内页码 ${anchor.printed_labels.join("、")}` : anchor.printed_label ? `书内页码 ${anchor.printed_label}` : "", anchor.pdf_page ? `PDF 第 ${anchor.pdf_page} 页` : "原文位置待核对"].filter(Boolean).join(" · ")).join("；");
  return <small>{counterAvailable(ref) ? <>{location}{anchors.some(anchor => anchor.printed_label_precision === "spread") ? " · 双页扫描，请核对具体印刷页" : ""}</> : "来源当前不可用"}</small>;
}
