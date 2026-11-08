"use client";

import styles from "./concept-editor.module.css";

type Alias = { alias: string; language: string; alias_type: string };
/** Chips edit the original alias records, preserving language and alias type. */
export function NodeAliasFields({ value, onChange }: { value: Alias[]; onChange: (value: Alias[]) => void }) {
  function update(index: number, patch: Partial<Alias>) { onChange(value.map((row, at) => at === index ? { ...row, ...patch } : row)); }
  return <section className={styles.aliasFields} aria-label="异名"><span>异名</span><div className={styles.aliasChips}>{value.map((row, index) => <section data-content-section key={index}>
    <header data-section-heading>{row.alias || "新增异名"}</header><div className={styles.aliasPopover}>
      <label>名称<input required maxLength={240} value={row.alias} onChange={event => update(index, { alias: event.target.value })}/></label>
      <label>语言<input required maxLength={16} value={row.language} onChange={event => update(index, { language: event.target.value })}/></label>
      <label>类型<select data-stl-select value={row.alias_type} onChange={event => update(index, { alias_type: event.target.value })}>{Object.entries({alias:"别名",translation:"译名",abbreviation:"简称",former_name:"旧称"}).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <button type="button" onClick={() => onChange(value.filter((_, at) => at !== index))}>移除此异名</button>
    </div></section>)}<button type="button" onClick={() => onChange([...value, { alias:"",language:"und",alias_type:"alias" }])}>＋ 添加异名</button></div></section>;
}
