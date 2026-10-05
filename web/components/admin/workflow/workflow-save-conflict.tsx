"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { WORKFLOW_STEP_LABELS, type WorkflowFieldConflict } from "./workflow-state";
import { FILL_FIELD_LABELS } from "./field-assistant-control";
import styles from "./catalog-reference.module.css";

const labels: Record<string, string> = {
  ...FILL_FIELD_LABELS, document_type: "文献类型", publication_mode: "公开内容", items: "作者与译者", display_name: "姓名", person_id: "人物记录", role: "职责", order: "顺序",
  primary_disciplines: "主要学科", related_disciplines: "相关学科", subdisciplines: "子学科", theories: "理论", topics: "主题", nodes: "知识条目", relations: "关系",
  reader_rendition_policy: "阅读文件策略", journal_contents: "本期目录", author_display: "作者", article_work_id: "馆内论文", publisher_authority_id: "出版社记录",
  id: "记录编号", name: "名称", status: "状态", confirmed: "已确认", skipped: "暂不策展", note: "备注", label: "名称", type: "类型", evidence_asset: "依据文件",
};
function fieldLabel(path: string) { return path.split(".").map((part) => /^\d+$/.test(part) ? `第 ${Number(part) + 1} 项` : labels[part] || part).join(" · "); }
function displayValue(value: unknown): ReactNode {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value)) return value.length ? <ol>{value.map((item, index) => <li key={index}>{displayValue(item)}</li>)}</ol> : "—";
  if (typeof value === "object") return <dl>{Object.entries(value).map(([key, item]) => <div key={key}><dt>{fieldLabel(key)}</dt><dd>{displayValue(item)}</dd></div>)}</dl>;
  return String(value);
}

export function WorkflowSaveConflict({ title, savedAt, fields, onResolve, onCancel }: {
  title: string; savedAt: string; fields: WorkflowFieldConflict[];
  onResolve: (choices: Record<string, "local" | "remote">) => void; onCancel: () => void;
}) {
  const [choices, setChoices] = useState<Record<string, "local" | "remote">>({});
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  return <section className={styles.conflict} aria-labelledby="workflow-conflict-title">
    <h2 ref={heading} tabIndex={-1} id="workflow-conflict-title">发现保存冲突</h2>
    <p>这本书已有更新。为避免覆盖已保存的内容，请核对双方差异。</p>
    <h3>{title}</h3>
    {fields.map(({ step, path, local, remote }) => {
      const key = `${step}.${path}`;
      return <fieldset key={key}><legend>内容对比：{WORKFLOW_STEP_LABELS[step]} · {fieldLabel(path)}</legend>
        <div className={styles.conflictColumns}>{(["local", "remote"] as const).map((side) => <label key={side} data-side={side} data-selected={choices[key] === side}>
          <strong>{side === "local" ? "我的输入（尚未保存）" : "已保存的最新版本"}</strong>
          <small>{side === "local" ? "当前输入" : savedAt && !Number.isNaN(Date.parse(savedAt)) ? `保存于 ${new Date(savedAt).toLocaleString("zh-CN", { hour12: false })}` : "保存时间 —"}</small>
          <div className={styles.conflictValue}>{displayValue(side === "local" ? local : remote)}</div>
          <span><input type="radio" name={key} checked={choices[key] === side} onChange={() => setChoices((current) => ({ ...current, [key]: side }))}/>{side === "local" ? "保留我的输入" : "载入最新版"}</span>
        </label>)}</div>
      </fieldset>;
    })}
    {!fields.length ? <p>字段内容没有冲突，但版本或锁定状态已更新。确认后将载入最新状态，并保留未保存输入。</p> : null}
    <p className={styles.conflictNotice}>请选择如何处理当前输入。选择后不会自动保存，仍可继续编辑并再次保存。</p>
    <footer><button type="button" className="button" disabled={fields.some(({ step, path }) => !choices[`${step}.${path}`])} onClick={() => onResolve(choices)}>确认选择，继续编辑</button><button type="button" className="button secondary" onClick={onCancel}>取消，继续编辑</button></footer>
  </section>;
}
