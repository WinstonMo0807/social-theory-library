"use client";

import { X } from "lucide-react";
import { useId, useRef, useState } from "react";
import { Button, IconButton, Textarea } from "./ui/controls";
import { Dialog } from "./ui/dialog";
import { BrandImage } from "./brand-image";
import styles from "./confirm-dialog.module.css";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel?: string;
  tone?: "default" | "danger";
  pending?: boolean;
  details?: string[];
  reasonLabel?: string;
  reasonDefault?: string;
  reasonRequired?: boolean;
  notice?: boolean;
  onCancel: () => void;
  onConfirm: (reason: string) => void | Promise<void>;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "取消",
  tone = "default",
  pending = false,
  details = [],
  reasonLabel,
  reasonDefault = "",
  reasonRequired = false,
  notice = false,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const [reason, setReason] = useState(reasonDefault);

  return (
    <Dialog
      open={open}
      className={styles.dialog}
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      initialFocusRef={notice ? titleRef : cancelRef}
      onOpen={() => setReason(reasonDefault)}
      onRequestClose={() => { if (!pending) onCancel(); }}
    >
      <div className={styles.card}>
        <header className={styles.brand}>
          <BrandImage />
          <IconButton aria-label="关闭确认框" onClick={onCancel} disabled={pending}><X size={18} /></IconButton>
        </header>
        <div className={styles.copy}><h2 id={titleId} ref={titleRef} tabIndex={-1}>{title}</h2><p id={descriptionId}>{description}</p></div>
        {details.length ? <ul>{details.map((detail) => <li key={detail}>{detail}</li>)}</ul> : null}
        {reasonLabel ? (
          <label>
            <span>{reasonLabel}</span>
            <Textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={3} />
          </label>
        ) : null}
        <footer>
          {!notice ? <Button className={styles.cancel} ref={cancelRef} onClick={onCancel} disabled={pending}>{cancelLabel}</Button> : null}
          <Button className={`${styles.confirm} ${tone === "danger" ? styles.danger : ""}`} onClick={() => void onConfirm(reason.trim())} disabled={pending || (reasonRequired && !reason.trim())}>{confirmLabel}</Button>
        </footer>
      </div>
    </Dialog>
  );
}
