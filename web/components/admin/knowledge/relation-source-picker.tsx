"use client";
import { SourceText } from "@/components/source-text";


import { confirmAction } from "@/lib/ui-dialog";

import { useEffect, useEffectEvent, useRef, useState } from "react";
import type { components } from "@/lib/api/generated/schema";
import { PlacementSourcePicker, type PlacementChoice } from "./placement-source-picker";
import styles from "./concept-editor.module.css";

type Reference = components["schemas"]["RelationAnchorInput"];
type Material = components["schemas"]["RelationAnchorMaterial"];
const same = (a: Reference | null, b?: Reference | null) => Boolean(a && b && a.span_id === b.span_id && a.document_revision_id === b.document_revision_id);
export type RelationSourceRequest = { sourceRequest?: number; onSourceOpened?: () => void };

export function RelationSourcePicker({ owner, value, saved, material, onChange, sourceRequest = 0, onSourceOpened }: {
  owner: string; value: Reference | null; saved?: Reference | null; material?: Material | null; onChange: (reference: Reference | null) => void;
} & RelationSourceRequest) {
  const [open, setOpen] = useState(false), [picked, setPicked] = useState<PlacementChoice | null>(null), [error, setError] = useState("");
  const section = useRef<HTMLElement>(null), acknowledge = useEffectEvent(() => onSourceOpened?.());
  useEffect(() => {
    if (!sourceRequest) return;
    const frame = requestAnimationFrame(() => { setOpen(true); section.current?.focus(); section.current?.scrollIntoView({block:"nearest"}); acknowledge(); });
    return () => cancelAnimationFrame(frame);
  }, [sourceRequest]);
  const preview = value && picked?.target.id === value.span_id && picked.target.document_revision_id === value.document_revision_id ? picked.source : null;
  const details = same(value, saved) ? material : preview ? {
    available: true, public_eligible: preview.public_eligible, title: preview.title, edition_label: String(preview.edition_label || ""),
    pdf_page: typeof preview.page_start === "number" ? preview.page_start : null, quote: preview.text || "", reader_href: preview.reader_url || "",
    detail: "所选原文将在保存与确认时再次核对。",
  } : null;
  function choose(choice: PlacementChoice) {
    if (choice.target.type !== "span" || !choice.target.document_revision_id) { setError("没有收到准确文档版本，请重新选择。当前来源未改变。"); return; }
    onChange({ span_id: choice.target.id, document_revision_id: choice.target.document_revision_id });
    setPicked(choice); setOpen(false); setError("");
  }
  return <section ref={section} tabIndex={-1} className={`${styles.panel} ${styles.sourceAnchor}`} aria-label="关系的原文依据">
    <h3>依据来源与原文位置</h3>
    {value ? <>
      {details?.available ? <><strong>{details.title || "原题名待补"}</strong><p>{details.edition_label}{details.pdf_page ? ` · PDF 第 ${details.pdf_page} 页` : ""}</p><blockquote><SourceText text={(details.quote) || ""} /></blockquote>{details.reader_href ? <a href={details.reader_href} target="_blank" rel="noopener">查看准确版本与原文 ↗</a> : null}</> : <p>原引用仍保留，当前不能核对原文。请重新读取或选择准确材料。</p>}
      {details?.detail ? <p role="status">{details.detail}</p> : null}{details && !details.public_eligible ? <small>当前不能作为公开关系的原文依据。</small> : null}
      <button type="button" onClick={async () => { if ((await confirmAction("移除此原文引用吗？原材料和文字出处保留，关系修改仍需保存或明确确认。"))) { onChange(null); setPicked(null); setOpen(false); } }}>移除此原文引用</button>
    </> : <p>可从馆藏选择准确原文。已有的文字出处保留为书目信息，不冒充可定位引文。</p>}
    <button type="button" onClick={() => setOpen(current => !current)}>{open ? "收起选材" : value ? "更换原文材料" : "从材料选原文"}</button>
    {error ? <p role="alert">{error}</p> : null}{open ? <PlacementSourcePicker owner={owner} kind="span" onChoose={choose} /> : null}
  </section>;
}
