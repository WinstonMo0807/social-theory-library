"use client";

import { useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import styles from "./intelligence-workspace.module.css";

type Identity = string | { change_item: string };
type Participant = { role: string; entity_id?: Identity; work_id?: string; edition_id?: string };
export type AssertionFieldsValue = {
  text?: string; predicate?: string; expression?: string; direction?: string; category?: string;
  conditions?: Record<string, string>; participants?: Participant[]; attribution_id?: Identity | null;
  unresolved_names?: string[]; unresolved_participants?: { role: string; label: string }[];
};
type Option = { id: string; label: string; kind?: string; definition?: string; pending?: boolean };
const roles: Record<string, string> = { subject: "主体", object: "客体", claimant: "主张者", quoted: "被引述者", criticized: "被批评者", context: "语境参与者" };
const expressions = { author_claim: "作者主张", direct_quote: "直接引述", paraphrase: "转述", criticized_claim: "被批评主张", editorial_judgment: "编辑判断" };
export const assertionPredicateLabels: Record<string, string> = { teaching: "师承", cooperation: "合作", comparative_reading: "比较阅读", criticism: "批评", influence: "影响", other: "其他关系", uses: "使用", criticizes: "批评", inherits: "继承", develops: "发展", cites: "引用", responds_to: "回应", mentions: "提及", proposes: "提出", defines: "定义", interprets: "解释", explains: "阐释", influences: "影响", general_mention: "一般提及", critique: "批判", introduction: "介绍", foundational: "奠基", application: "应用", development: "发展" };
const conditions = { time: "时间", region: "地区", population: "人群", research_object: "研究对象", concept_usage: "概念用法", other: "其他限定" };
const identityKey = (id?: Identity) => typeof id === "string" ? id : id ? `proposal:${id.change_item}` : "";
const identityValue = (id: string): Identity => id.startsWith("proposal:") ? { change_item: id.slice(9) } : id;

export function AssertionFields({ value, disabled, options, onChange }: {
  value: AssertionFieldsValue; disabled: boolean; options: Option[]; onChange: (value: AssertionFieldsValue) => void;
}) {
  const [query, setQuery] = useState(""), [found, setFound] = useState<Option[]>([]), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const choices = [...options, ...found.filter(row => !options.some(v => v.id === row.id))];
  const participants = value.participants || [];
  const unresolved = value.unresolved_participants || (value.unresolved_names || []).map(label => ({ label, role: "context" }));
  function setParticipants(next: Participant[]) {
    const claimants = next.filter(p => p.role === "claimant" && p.entity_id);
    onChange({ ...value, participants: next, attribution_id: claimants.length === 1 ? claimants[0].entity_id : null });
  }
  function identitySelect(selected: Identity | undefined, change: (id: Identity) => void) {
    const key = identityKey(selected);
    return <select aria-label="关联实体身份" disabled={disabled} value={key} onChange={e => { if (e.target.value) change(identityValue(e.target.value)); }}>
      <option value="">选择具体身份</option>{key && !choices.some(v => (v.pending ? `proposal:${v.id}` : v.id) === key) && <option value={key}>已关联身份 · {key}</option>}
      {choices.map(row => <option key={`${row.pending ? "proposal:" : ""}${row.id}`} value={row.pending ? `proposal:${row.id}` : row.id}>{row.label} · {row.kind || "实体"}{row.pending ? "（本次建议）" : ""}{row.definition ? ` · ${row.definition.slice(0, 60)}` : ""}</option>)}
    </select>;
  }
  return <>
    <label>陈述<textarea value={value.text || ""} disabled={disabled} onChange={e => onChange({ ...value, text: e.target.value })} /></label>
    <div className={styles.scope}>
      <label>关系类型<select value={value.predicate || ""} disabled={disabled} onChange={e => onChange({ ...value, predicate: e.target.value })}><option value="">仅保存论述</option>{value.predicate && !assertionPredicateLabels[value.predicate] && <option value={value.predicate}>{value.predicate}（原记录）</option>}{Object.entries(assertionPredicateLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>论述身份<select value={value.expression || "author_claim"} disabled={disabled} onChange={e => onChange({ ...value, expression: e.target.value })}>{Object.entries(expressions).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>关系方向<select value={value.direction || "directed"} disabled={disabled} onChange={e => onChange({ ...value, direction: e.target.value })}><option value="directed">主体指向客体</option><option value="bidirectional">双向关系</option><option value="undirected">无方向</option></select></label>
    </div>
    <h4>论述参与者</h4>
    {participants.map((p, index) => <div className={styles.scope} key={index}>
      <label>角色<select value={p.role} disabled={disabled} onChange={e => setParticipants(participants.map((v, i) => i === index ? { ...v, role: e.target.value } : v))}>{Object.entries(roles).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>身份{p.work_id || p.edition_id ? <span>{p.work_id ? "作品" : "出版版本"} · {p.work_id || p.edition_id}</span> : identitySelect(p.entity_id, id => setParticipants(participants.map((v, i) => i === index ? { ...v, entity_id: id } : v)))}</label>
      <button type="button" disabled={disabled} onClick={() => setParticipants(participants.filter((_, i) => i !== index))}>移除此参与者</button>
    </div>)}
    {unresolved.map((p, index) => <div key={`${p.role}:${p.label}`} className={styles.notice}>
      <label>{roles[p.role]} · {p.label}（待确认）{identitySelect(undefined, id => {
        const remaining = unresolved.filter((_, i) => i !== index);
        onChange({ ...value, participants: [...participants, { role: p.role, entity_id: id }],
          ...(p.role === "claimant" ? { attribution_id: id } : {}), unresolved_participants: remaining, unresolved_names: [...new Set(remaining.map(v => v.label))] });
      })}</label>
    </div>)}
    {!disabled && <><button type="button" onClick={() => setParticipants([...participants, { role: "context" }])}>添加参与者</button>
      <div className={styles.scope}><label>查找馆内身份<input value={query} onChange={e => setQuery(e.target.value)} placeholder="人物、组织或概念名称" /></label><button disabled={busy || !query.trim()} onClick={async () => {
        setBusy(true); setError(""); try {
          const result = await apiRequest<{ entities: Option[] }>(`/knowledge/entities/?preview=1&q=${encodeURIComponent(query)}`, { cache: "no-store" }, getServerSessionCredential());
          setFound(result.entities); if (!result.entities.length) setError("没有匹配身份。可在本次实体建议中保留独立身份，再关联到陈述。");
        } catch (e) { setError(e instanceof Error ? e.message : "身份查询失败，请重试。"); } finally { setBusy(false); }
      }}>{busy ? "查找中" : "查找身份"}</button></div>{error && <p role="status">{error}</p>}
      {!!found.length && <p className={styles.reason}>已找到 {found.length} 个身份，可在上方选择。名称相同仍须核对资料。</p>}</>}
    <details open={Object.values(value.conditions || {}).some(Boolean)}><summary>适用条件</summary><div className={styles.scope}>{Object.entries(conditions).map(([key, label]) => <label key={key}>{label}<input disabled={disabled} value={value.conditions?.[key] || ""} onChange={e => onChange({ ...value, conditions: { ...value.conditions, [key]: e.target.value } })} /></label>)}</div></details>
  </>;
}
