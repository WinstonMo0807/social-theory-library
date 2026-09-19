"use client";

import { useEffect, useEffectEvent, useRef, type ComponentPropsWithoutRef, type RefObject } from "react";

export type DialogProps = Omit<ComponentPropsWithoutRef<"dialog">, "open" | "onCancel" | "onClick"> & {
  open: boolean;
  onRequestClose?: () => void;
  initialFocusRef?: RefObject<HTMLElement | null>;
  onOpen?: () => void;
};

/** Native modal behavior supplies focus containment and background inertness. */
export function Dialog({ open, onRequestClose, initialFocusRef, onOpen, onKeyDown, children, ...props }: DialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const enter = useEffectEvent(() => {
    onOpen?.();
    initialFocusRef?.current?.focus();
  });

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    let frame = 0;
    if (open && !dialog.open) {
      openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      dialog.showModal();
      frame = window.requestAnimationFrame(() => enter());
    } else if (!open && dialog.open) {
      dialog.close();
      if (openerRef.current?.isConnected) openerRef.current.focus();
      openerRef.current = null;
    }
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  useEffect(() => {
    const dialog = dialogRef.current;
    return () => {
      if (dialog?.open) dialog.close();
      if (openerRef.current?.isConnected) openerRef.current.focus();
    };
  }, []);

  return <dialog {...props} ref={dialogRef} onKeyDown={(event) => {
    onKeyDown?.(event);
    if (event.defaultPrevented || event.key !== "Tab") return;
    // Native modal inertness protects the page, but Tab at an edge may move
    // into browser chrome. Keep keyboard navigation within the open task.
    const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(
      'button,input,select,textarea,a[href],summary,[tabindex]',
    )).filter((element) => element.tabIndex >= 0 && !element.matches(":disabled") && !element.closest("[inert],[hidden]") && element.checkVisibility());
    const first = controls[0];
    const last = controls.at(-1);
    if (!first) { event.preventDefault(); return; }
    if (event.shiftKey ? document.activeElement === first : document.activeElement === last) {
      event.preventDefault();
      (event.shiftKey ? last : first)?.focus();
    }
  }} onCancel={(event) => {
    event.preventDefault();
    onRequestClose?.();
  }} onClick={(event) => {
    if (event.target === event.currentTarget) onRequestClose?.();
  }}>{children}</dialog>;
}

/** Explicit right-hand modal variant; persistent inspection uses Inspector. */
export function Drawer({ className = "", ...props }: DialogProps) {
  return <Dialog {...props} className={`ui-drawer ${className}`.trim()} />;
}
