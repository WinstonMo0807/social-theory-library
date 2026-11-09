"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { createRequestKey } from "@/lib/request-key";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { AssertionFields, type AssertionFieldsValue } from "./assertion-fields";
import { knowledgeCall, type SourceLocator } from "./knowledge-workbench";
import { KnowledgeAssertionContent, type KnowledgeAssertion } from "../public/knowledge-page-content";
import s from "./knowledge-workbench.module.css";

export type EditableAssertion = KnowledgeAssertion & Omit<AssertionFieldsValue, "participants"> & {
  predicate?: string; expression?: string; direction?: string;
  participants?: (NonNullable<AssertionFieldsValue["participants"]>[number] & { entity__label?: string })[];
};

export function KnowledgeAssertionEditor({ pageId, title, initial, baseHash, subjectEntity, subjectWork, anchor }: {
  pageId: string; title: string; initial?: EditableAssertion; baseHash?: string; subjectEntity?: string; subjectWork?: string; anchor?: SourceLocator;
}) {
  const [value, setValue] = useState<AssertionFieldsValue>(initial || { text: "", category: "relation", expression: "editorial_judgment", participants: subjectEntity ? [{ role: "subject", entity_id: subjectEntity }] : subjectWork ? [{ role: "subject", work_id: subjectWork }] : [], conditions: {}, direction: "directed" });
  const [citation, setCitation] = useState(initial?.sources.map(v => v.citation || v.work__title).filter(Boolean).join("；") || "");
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [reviewUrl, setReviewUrl] = useState("");
  const request = useRef<{ signature: string; id: string } | null>(null);
  useUnsavedForm(!reviewUrl && (value.text !== (initial?.text || "") || citation !== (initial?.sources.map(v => v.citation || v.work__title).filter(Boolean).join("；") || "")), false);
  async function submit() {
    setBusy(true); setError("");
    try {
      // Retain real multi-page sources when editing an existing statement.
      const evidence = (initial?.evidence || (anchor ? [{ stance: "context", anchor_id: anchor.anchor_id }] : [])).map(v => ({ stance: v.stance, anchor_id: v.anchor_id }));
      const assertion = { ...value, source_citation: citation, evidence, ...(initial ? { supersedes_id: initial.id, base_hash: baseHash } : {}) };
      const body = { assertion };
      const signature = JSON.stringify(body); if (request.current?.signature !== signature) request.current = { signature, id: createRequestKey() };
      const result = await knowledgeCall<{ review_url: string }>(`/knowledge/pages/${pageId}/assertions/draft/`, { ...body, request_id: request.current.id });
      setReviewUrl(result.review_url);
    } catch (e) { setError(e instanceof Error ? e.message : "提交失败，请重试。"); } finally { setBusy(false); }
  }
  const options = [...(subjectEntity ? [{ id: subjectEntity, label: title }] : []), ...(initial?.participants || []).filter(v => typeof v.entity_id === "string").map(v => ({ id: v.entity_id as string, label: v.entity__label || "已关联实体" }))];
  return <section className={s.preview} aria-label="学术陈述编辑">
    <h2>{initial ? "修订学术陈述" : "新增学术陈述"}</h2>
    <AssertionFields value={value} disabled={busy || !!reviewUrl} options={options} onChange={setValue} />
    <label>文献出处<textarea value={citation} onChange={e => setCitation(e.target.value)} disabled={busy || !!reviewUrl} rows={3} placeholder="作者、题名、出版信息及页码；保留可核对的来源说明" /></label>
    {!initial?.evidence.length && !anchor && <p className={s.muted}>此处保存人工提供的出处，尚未核实精确原文。需要原文定位时，可从原文与检索工作区选取证据。</p>}
    <h3>页面呈现</h3>
    <KnowledgeAssertionContent assertion={{ id: initial?.id || "draft", text: value.text || "陈述内容将显示在这里", conditions: value.conditions, sources: [{ work__title: title, attribution__label: null, expression: value.expression || "editorial_judgment", citation }], evidence: initial?.evidence || (anchor ? [{ anchor_id: anchor.anchor_id, stance: "context", locator: anchor }] : []) }} />
    {error && <p className={s.error} role="alert">{error}</p>}
    {reviewUrl ? <p role="status">草稿已保存，公开内容尚未改变。<Link href={reviewUrl}>继续审核 →</Link></p> : <button className={s.primary} disabled={busy || !value.text?.trim() || (!citation.trim() && !initial?.evidence.length && !anchor)} onClick={() => void submit()}>提交审核草稿</button>}
  </section>;
}
