"use client";

import { useState } from "react";
import type { components } from "@/lib/api/generated/schema";

export type PublicationPreparation = components["schemas"]["PublicationPreparation"];

const labels = { unchanged: "未变化", added: "新增", removed: "移除", changed: "修改" };

export function PublicationDiff({ value, showChecks = true }: { value: PublicationPreparation; showChecks?: boolean }) {
  const [showAll, setShowAll] = useState(false);
  const rows = value.changes.filter((row) => showAll || row.change !== "unchanged");
  return <section className="admin-panel publication-diff" aria-label="发布内容差异">
    <header><h2>本次发布将改变什么</h2><label><input type="checkbox" checked={showAll} onChange={(event) => setShowAll(event.target.checked)} />显示未变化字段</label></header>
    <div style={{ overflowX: "auto" }}><table><caption>当前公开内容与已保存草稿</caption><thead><tr><th scope="col">字段</th><th scope="col">当前公开</th><th scope="col">准备发布</th><th scope="col">变化</th></tr></thead>
      <tbody>{rows.map((row) => <tr key={row.field}><th scope="row">{row.label}</th><td data-label="当前公开">{row.before_display || "未填写"}</td><td data-label="准备发布">{row.after_display || "未填写"}</td><td data-label="变化">{labels[row.change]}</td></tr>)}</tbody></table></div>
    {!rows.length ? <p>没有字段变化。</p> : null}
    {showChecks && value.blocking.length ? <div role="alert"><h3>必须处理</h3><ul>{value.blocking.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
    {showChecks && value.warnings.length ? <details open><summary>发布前建议核对</summary><ul>{value.warnings.map((item) => <li key={item}>{item}</li>)}</ul></details> : null}
    {showChecks && value.background_processing.length ? <details><summary>发布后后台处理</summary><ul>{value.background_processing.map((item) => <li key={item}>{item}</li>)}</ul></details> : null}
  </section>;
}
