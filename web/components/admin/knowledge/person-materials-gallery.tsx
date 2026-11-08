"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight, Pencil, Plus } from "lucide-react";
import { normalizePublicResourceUrl } from "@/lib/api";
import type { AuthorityValues } from "@/lib/api/person-authority.client";
import styles from "./person-authority.module.css";

type Material = NonNullable<AuthorityValues["biographical_materials"]>[number];

export function PersonMaterialsGallery({ items, onChange, onAdd }: {
  items: Material[]; onChange: (items: Material[]) => void; onAdd: () => void;
}) {
  const [selected, setSelected] = useState(0);
  const index = Math.min(selected, Math.max(0, items.length - 1)), current = items[index];
  const visible = Array.from({ length: Math.min(3, items.length) }, (_, offset) => (index + offset) % items.length);
  return <section className={`${styles.panel} ${styles.materials}`}>
    <header className={styles.row}><h2>3. 人物照片与生平资料</h2><button type="button" onClick={onAdd} disabled={items.length >= 100}><Plus size={13} />添加资料</button></header>
    {current ? <>
      <div className={styles.materialImages}>{visible.map(at => <button type="button" key={items[at].id} onClick={() => setSelected(at)} aria-pressed={at === index} aria-label={`查看资料 ${at + 1}：${items[at].caption || "未填写说明"}`}>
        <img src={normalizePublicResourceUrl(`/api/catalog/admin/media/renditions/${items[at].rendition_id}/file/`)} alt={items[at].caption || "人物照片与生平资料"} />
      </button>)}</div>
      <div className={styles.materialCaption}><p>{current.caption || "尚未填写资料说明"}</p><nav aria-label="人物资料翻页"><button type="button" aria-label="上一项资料" disabled={index === 0} onClick={() => setSelected(index - 1)}><ChevronLeft size={14} /></button><span>{index + 1} / {items.length}</span><button type="button" aria-label="下一项资料" disabled={index + 1 >= items.length} onClick={() => setSelected(index + 1)}><ChevronRight size={14} /></button></nav></div>
      <section data-content-section className={styles.materialEdit} key={current.id}><header data-section-heading><Pencil size={12} />编辑资料说明</header><label>资料说明<textarea rows={2} maxLength={500} value={current.caption} onChange={event => onChange(items.map(row => row.id === current.id ? { ...row, caption: event.target.value } : row))} /></label><button type="button" onClick={() => onChange(items.filter(row => row.id !== current.id))}>移除此项关联</button><small>保存后移除当前人物的关联，素材原件与历史版本保留。</small></section>
    </> : <p className={styles.muted}>尚未添加人物照片与生平资料。</p>}
  </section>;
}
