"use client";

import { AlertTriangle, X } from "lucide-react";
import { useId, useRef, useState } from "react";
import { Button, IconButton, Textarea } from "./ui/controls";
import { Dialog } from "./ui/dialog";

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
  const confirmRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const [reason, setReason] = useState(reasonDefault);

  return (
    <Dialog
      open={open}
      className={`confirm-dialog ${tone === "danger" ? "danger" : ""}`}
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      initialFocusRef={confirmRef}
      onOpen={() => setReason(reasonDefault)}
      onRequestClose={() => { if (!pending) onCancel(); }}
    >
      <div className="confirm-dialog-card">
        <header>
          <span aria-hidden="true"><AlertTriangle size={18} /></span>
          <div><h2 id={titleId}>{title}</h2><p id={descriptionId}>{description}</p></div>
          <IconButton aria-label="关闭确认框" onClick={onCancel} disabled={pending}><X size={18} /></IconButton>
        </header>
        {details.length ? <ul>{details.map((detail) => <li key={detail}>{detail}</li>)}</ul> : null}
        {reasonLabel ? (
          <label>
            <span>{reasonLabel}</span>
            <Textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={3} />
          </label>
        ) : null}
        <footer>
          <Button className="button secondary" onClick={onCancel} disabled={pending}>{cancelLabel}</Button>
          <Button className={`button ${tone === "danger" ? "danger" : ""}`} ref={confirmRef} onClick={() => void onConfirm(reason.trim())} disabled={pending || (reasonRequired && !reason.trim())}>{confirmLabel}</Button>
        </footer>
      </div>
    </Dialog>
  );
}
