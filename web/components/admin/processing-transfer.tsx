"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { X } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import type { components } from "@/lib/api/generated/schema";
import styles from "./processing-workspace.module.css";

type Transfer = components["schemas"]["ProcessingOCRTransfer"];
type Choice = { target: "nas" | "remote"; target_version: string; acknowledge_remote: boolean };

export function ProcessingTransfer({ value, title, disabled, onTransfer }: {
  value: Transfer; title: string; disabled: boolean; onTransfer: (choice: Choice) => Promise<void>;
}) {
  const [open, setOpen] = useState(false), [targetId, setTargetId] = useState(""), [acknowledged, setAcknowledged] = useState(false);
  const titleId = useId(), descriptionId = useId();
  const target = value.targets.find(row => row.id === targetId);
  const ready = target?.configured && (!target.external || acknowledged);
  return <section className={styles.transfer} aria-label="任务使用的 OCR 服务">
    <h3>处理节点</h3><p>{value.current_label}</p>
    {value.configuration_changed ? <p className={styles.notice}>原指定服务的配置已经变化。已保存页保留，请核对新配置后重新选择。</p> : null}
    <div className={styles.actions}>{value.can_transfer ? <button type="button" disabled={disabled} onClick={() => setOpen(true)}>迁移到其他节点</button> : null}<Link href="/admin/processing/status">查看服务状态 →</Link></div>
    <Dialog open={open && value.can_transfer} onRequestClose={() => setOpen(false)} aria-labelledby={titleId} aria-describedby={descriptionId} className={`${styles.dialog} ${styles.recoveryDialog}`}>
      <header><h2 id={titleId}>选择接续处理节点</h2><button type="button" aria-label="关闭节点选择" onClick={() => setOpen(false)}><X size={18}/></button></header>
      <p className={styles.recoveryTitle}>{title}</p>
      <p id={descriptionId}>从此任务尚未完成的页面继续，保留已保存页面、人工核验与当前重试范围。原执行轮次随后返回的结果不能覆盖接续任务。</p>
      <fieldset className={styles.serviceChoices}><legend>已配置的 OCR 服务</legend>{value.targets.map(row => <label key={row.id}>
        <input type="radio" name={titleId} value={row.id} checked={targetId === row.id} disabled={!row.configured || disabled} onChange={() => { setTargetId(row.id); setAcknowledged(false); }}/>
        <span><strong>{row.label}</strong><small>{row.configured ? "配置完整 · 在线状态请查看服务状态页" : "配置不完整，暂不能选择"}</small></span>
      </label>)}</fieldset>
      {target?.external ? <label className={styles.remoteAcknowledgement}><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)}/>我确认将尚需识别的 PDF 页面发送到系统已配置的远程 OCR 服务。</label> : null}
      <p className={styles.note}>本次只更改此任务。目标配置变化时暂停发送并保留结果；指定节点不可用时不会自动改投另一节点。</p>
      <div className={styles.actions}><button type="button" onClick={() => setOpen(false)}>继续等待</button><button type="button" className={styles.primary} disabled={disabled || !ready} onClick={() => {
        if (!target || !ready) return;
        setOpen(false); void onTransfer({ target: target.id, target_version: target.version, acknowledge_remote: target.external && acknowledged });
      }}>确认并继续处理</button></div>
    </Dialog>
  </section>;
}
