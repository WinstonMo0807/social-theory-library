"use client";

import { useState } from "react";
import type { components } from "@/lib/api/generated/schema";

export type PublicationPreparation = components["schemas"]["PublicationPreparation"];

const labels = { unchanged: "未变化", added: "新增", removed: "移除", changed: "修改" };

export function PublicationDiff({ value, showChecks = true, title = "本次发布将改变什么", afterLabel = "准备发布", compact = false }: { value: PublicationPreparation; showChecks?: boolean; title?: string; afterLabel?: string; compact?: boolean }) {
  const [showAll, setShowAll] = useState(false);
  const [kind, setKind] = useState("changed");
  const rows = value.changes.filter((row) => showAll || row.change !== "unchanged");
  if (compact) return <section className="publication-diff-compact" aria-label="版本差异摘要">
    <nav aria-label="变化类型">{[["changed","内容变更"],["added","新增内容"],["removed","删除内容"]].map(([key,label])=><button type="button" key={key} aria-pressed={kind===key} onClick={()=>setKind(key)}>{label} <span>{value.changes.filter(row=>row.change===key).length}</span></button>)}</nav>
    <ul>{value.changes.filter(row=>row.change===kind).map(row=><li key={row.field}><span>{row.label}</span><small data-change={row.change}>{labels[row.change]}</small><details><summary>{row.after_display||row.before_display||"未填写"}<span>查看 ›</span></summary><dl><dt>当前公开</dt><dd>{row.before_display||"未填写"}</dd><dt>{afterLabel}</dt><dd>{row.after_display||"未填写"}</dd></dl></details></li>)}</ul>
    {!value.changes.some(row=>row.change===kind)?<p>没有此类变化。</p>:null}
  </section>;
  return <section className="admin-panel publication-diff" aria-label="发布内容差异">
    <header><h2>{title}</h2><label><input type="checkbox" checked={showAll} onChange={(event) => setShowAll(event.target.checked)} />显示未变化字段</label></header>
    <div style={{ overflowX: "auto" }}><table><caption>当前公开内容与{afterLabel}</caption><thead><tr><th scope="col">字段</th><th scope="col">当前公开</th><th scope="col">{afterLabel}</th><th scope="col">变化</th></tr></thead>
      <tbody>{rows.map((row) => <tr key={row.field}><th scope="row">{row.label}</th><td data-label="当前公开">{row.before_display || "未填写"}</td><td data-label={afterLabel}>{row.after_display || "未填写"}</td><td data-label="变化">{labels[row.change]}</td></tr>)}</tbody></table></div>
    {!rows.length ? <p>没有字段变化。</p> : null}
    {showChecks && value.blocking.length ? <div role="alert"><h3>必须处理</h3><ul>{value.blocking.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
    {showChecks && value.warnings.length ? <details open><summary>发布前建议核对</summary><ul>{value.warnings.map((item) => <li key={item}>{item}</li>)}</ul></details> : null}
    {showChecks && value.background_processing.length ? <details><summary>发布后后台处理</summary><ul>{value.background_processing.map((item) => <li key={item}>{item}</li>)}</ul></details> : null}
  </section>;
}
