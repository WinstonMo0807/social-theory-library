"use client";

import { AlertTriangle, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

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
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const [reason, setReason] = useState(reasonDefault);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      setReason(reasonDefault);
      dialog.showModal();
      window.requestAnimationFrame(() => confirmRef.current?.focus());
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open, reasonDefault]);

  return (
    <dialog
      className={`confirm-dialog ${tone === "danger" ? "danger" : ""}`}
      ref={dialogRef}
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onCancel={(event) => {
        event.preventDefault();
        if (!pending) onCancel();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget && !pending) onCancel();
      }}
    >
      <div className="confirm-dialog-card">
        <header>
          <span aria-hidden="true"><AlertTriangle size={18} /></span>
          <div><h2 id={titleId}>{title}</h2><p id={descriptionId}>{description}</p></div>
          <button type="button" aria-label="关闭确认框" onClick={onCancel} disabled={pending}><X size={18} /></button>
        </header>
        {details.length ? <ul>{details.map((detail) => <li key={detail}>{detail}</li>)}</ul> : null}
        {reasonLabel ? (
          <label>
            <span>{reasonLabel}</span>
            <textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={3} />
          </label>
        ) : null}
        <footer>
          <button className="button secondary" type="button" onClick={onCancel} disabled={pending}>{cancelLabel}</button>
          <button className={`button ${tone === "danger" ? "danger" : ""}`} type="button" ref={confirmRef} onClick={() => void onConfirm(reason.trim())} disabled={pending || (reasonRequired && !reason.trim())}>{confirmLabel}</button>
        </footer>
      </div>
    </dialog>
  );
}
