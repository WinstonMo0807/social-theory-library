"use client";

import { useContext } from "react";
import { IssueTextEditor } from "../curation/issue-text-editor";
import { KnowledgePublicationContext } from "./knowledge-publish-control";
import { scholarProseBlock, type ScholarProse } from "@/lib/api/scholar-prose";

export function ScholarProseEditor({ label, value, format, disabled, recommendedLength, maxLength, onChange }: {
  label: string; value: string; format: ScholarProse["biography"]; disabled: boolean; recommendedLength: number; maxLength: number;
  onChange: (text: string, format: NonNullable<ScholarProse["biography"]>) => void;
}) {
  const publication = useContext(KnowledgePublicationContext);
  const locked = disabled || Boolean(publication?.locked);
  const block = scholarProseBlock(value, format);
  // Preserve unusually long legacy biographies without silently truncating them.
  if (value.length > maxLength) return <label>{label}<textarea rows={8} value={value} disabled={locked} onChange={event => onChange(event.target.value, {text:event.target.value,text_style:"paragraph",text_marks:[]})}/><small>原文超过格式编辑范围，已保留完整纯文本；可继续编辑，缩短后可使用格式工具。</small></label>;
  return <IssueTextEditor compact label={label} block={block} disabled={locked} maxLength={maxLength} recommendedLength={recommendedLength} onChange={patch => {
    const next = {...block,...patch};
    onChange(next.text, {text:next.text,text_style:next.text_style,text_marks:next.text_marks});
  }}/>;
}
