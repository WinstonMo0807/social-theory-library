"use client";

import { confirmAction } from "@/lib/ui-dialog";

import { useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { normalizePublicResourceUrl } from "@/lib/api";
import { Dialog } from "@/components/ui/dialog";
import { InlineMediaPicker } from "../curation/inline-media-picker";
import styles from "./timeline-editor.module.css";

export const timelineEvidenceImageUrl = (identifier?: string | null) => identifier ? normalizePublicResourceUrl(`/api/catalog/admin/media/renditions/${encodeURIComponent(identifier)}/file/`) : "";

export function TimelineEvidenceImage({ owner, value, primary = false, onChange }: { owner: string; value?: string | null; primary?: boolean; onChange: (id: string | null) => void }) {
  const [open, setOpen] = useState(false), [dirty, setDirty] = useState(false), [failed, setFailed] = useState("");
  const trigger = useRef<HTMLButtonElement>(null), titleId = useId();
  const close = async () => { if (!dirty || (await confirmAction("放弃尚未保存的图片出处资料吗？"))) setOpen(false); };
  return <section className={styles.evidenceImage} aria-label={primary ? "主要出处展示图片" : "补充出处图片"}>
    <div className={styles.evidenceImageRow}>
      {value && failed !== value ? <img key={value} src={timelineEvidenceImageUrl(value)} alt={primary ? "主要出处展示图片" : "补充出处图片"} onError={() => setFailed(value)} /> : <span className={styles.imagePlaceholder}>{value ? "图片暂不可读取" : "尚未选择图片"}</span>}
      <div className={styles.controls}><button ref={trigger} type="button" onClick={() => setOpen(true)}>{value ? "更换图片" : "选择图片"}</button>{value && failed === value ? <button type="button" onClick={() => setFailed("")}>重试读取</button> : null}{value ? <button type="button" onClick={async () => { if ((await confirmAction("移除此处图片关联？原图片和已保存的历史修订仍保留。"))) onChange(null); }}>移除图片</button> : null}</div>
    </div>
    <p>{primary ? "此图随事件发布展示；未选图时沿用原展示图片。" : "此图只用于编辑核对，不随事件公开。"}更换图片不改变出处文件。</p>
    {open ? createPortal(<Dialog open onRequestClose={close} aria-labelledby={titleId} className={styles.imageDialog} onSubmit={event => event.stopPropagation()} onChange={event => event.stopPropagation()} onKeyDown={event => { if (event.key === "Escape" && event.nativeEvent.isComposing) event.preventDefault(); }}>
      <header><h2 id={titleId}>选择出处图片</h2><button type="button" onClick={close}>关闭</button></header>
      <p>请选择与此处材料一致的图片，并核对出处、署名与使用许可。</p>
      <InlineMediaPicker key={owner} selectedRenditionId={value} onDirtyChange={setDirty} selectionMessage={primary ? "已填入事件草稿，确认发布后展示。" : "已填入编辑核对资料，不随事件公开。"} onSelect={id => {
        if (trigger.current?.closest("fieldset[disabled]")) return;
        onChange(id); setDirty(false); setOpen(false);
      }} />
    </Dialog>, document.body) : null}
  </section>;
}
